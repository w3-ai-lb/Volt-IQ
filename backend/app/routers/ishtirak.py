"""
The owner's view of his own network.

    GET /ishtirak/dashboard          everything the briefing lists for Phase 2a
    GET /ishtirak/zones              loss per zone, worst first
    GET /ishtirak/zones/{id}         one zone, month by month

WHO THIS IS FOR
---------------
Not a customer. The briefing is explicit that the owner is not an engineer and
that if a number needs explaining, the screen explains it. So every zone row
carries a sentence saying what its figure means and what, if anything, to do
about it, and the payload carries a summary written in the shape the briefing
calls the good outcome.

WHERE THE NUMBERS COME FROM
---------------------------
zone_loss_monthly, which is computed once by app/analytics/loss.py and stored.
Nothing here recalculates a loss figure, so the dashboard and any answer the
question interface gives are the same number by construction rather than by
coincidence. That is also what makes the briefing's rule enforceable: every
figure traces to a row somebody can go and look at.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics import loss as loss_engine
from app.core.deps import require_admin
from app.core.i18n import join_sentences, localize, localize_all, request_language
from app.database import get_db
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoicePayment
from app.models.generator_metrics import GeneratorMonthMetrics
from app.models.loss import ZoneLossMonthly
from app.models.network import Generator, GeneratorAlarm, Zone, ZoneEnergyDaily
from app.schemas.ishtirak import (
    AlarmRow,
    Collections,
    DashboardOut,
    GeneratorToday,
    ZoneLossRow,
)

router = APIRouter(prefix="/ishtirak", tags=["Ishtirak"])

IMBALANCE_FLAG_PCT = 15.0


# ---------------------------------------------------------------------------
def _latest_date(db: Session) -> date | None:
    """
    The newest day the generator data covers.

    The dashboard anchors to this rather than to the wall clock. A historical
    export legitimately stops before today, and a screen that says "produced
    today: 0 kWh" is reporting a silent night rather than an absent file. The
    same decision was taken for the platform's own consumption charts.
    """
    return db.query(func.max(ZoneEnergyDaily.date)).scalar()


def _month_bounds(anchor: date) -> tuple[date, date]:
    start = anchor.replace(day=1)
    return start, anchor


def _explain(acc: dict, zone: Zone | None) -> str:
    """
    One sentence a non-engineer can act on, about the period being shown.

    It takes the SAME aggregate the row shows rather than the most recent
    month, because a sentence quoting 15.7% beside a figure of 10.9% is the
    defect the briefing warns about most: a number on the screen that does not
    trace to the query that produced the number beside it.

    Ordered by what the owner can do about it, not by size: a large normal
    technical loss is not news, and a small unexplained one is.
    """
    delivered = acc["delivered"]
    if not delivered:
        return "No energy was delivered to this zone in the period shown."
    loss_pct = 100.0 * acc["loss"] / delivered
    unexplained_pct = 100.0 * acc["unexplained"] / delivered

    if unexplained_pct >= 2.0:
        return (
            f"Loses {loss_pct:.1f}%, of which {unexplained_pct:.1f}% is not explained by "
            f"distance, load, the reading process or your own connections. Worth a visit."
        )
    if acc["excess"] > 0:
        return (
            f"Loses {loss_pct:.1f}%. The feeding generator is running unbalanced, which is "
            f"heat in the cable serving nobody. A technician can fix this."
        )
    if acc["measurement"] > acc["unexplained"]:
        return (
            f"Loses {loss_pct:.1f}%, and most of what is unaccounted for comes from how the "
            f"meters were read rather than from where the electricity went."
        )
    distance = (
        f" at {zone.avg_distance_m:.0f} m from the generator"
        if zone is not None and zone.avg_distance_m
        else ""
    )
    return f"Loses {loss_pct:.1f}%, which is what physics costs for a zone{distance}. Nothing to do."


# ---------------------------------------------------------------------------
@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    months: int = Query(1, ge=1, le=18, description="How many months back to summarise"),
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    anchor = _latest_date(db)
    if anchor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No generator data has been loaded. Run: python -m app.pipeline.ishtirak",
        )

    month_start, period_end = _month_bounds(anchor)
    period_start = month_start
    for _ in range(months - 1):
        period_start = (period_start - timedelta(days=1)).replace(day=1)

    # --- FR-2.1 / FR-2.2 / FR-2.3, straight from the stored account ---------
    rows = (
        db.query(ZoneLossMonthly)
        .filter(ZoneLossMonthly.month >= period_start, ZoneLossMonthly.month <= period_end)
        .all()
    )
    zones = {z.zone_id: z for z in db.query(Zone).all()}

    produced = sum(r.energy_delivered_kwh or 0.0 for r in rows)
    billed = sum(r.units_billed_kwh or 0.0 for r in rows)
    gap = produced - billed
    loss_pct = 100.0 * gap / produced if produced else None

    # --- FR-2.9: one row per zone over the window, worst first --------------
    by_zone: dict[str, dict] = {}
    for r in rows:
        acc = by_zone.setdefault(
            r.zone_id,
            dict(
                delivered=0.0, billed=0.0, loss=0.0, normal=0.0, excess=0.0,
                measurement=0.0, unbilled=0.0, unexplained=0.0, conf=[], last=r,
            ),
        )
        acc["delivered"] += r.energy_delivered_kwh or 0.0
        acc["billed"] += r.units_billed_kwh or 0.0
        acc["loss"] += r.loss_kwh or 0.0
        acc["normal"] += r.normal_technical_kwh or 0.0
        acc["excess"] += r.excess_technical_kwh or 0.0
        acc["measurement"] += r.measurement_kwh or 0.0
        acc["unbilled"] += r.unbilled_kwh or 0.0
        acc["unexplained"] += r.unexplained_kwh or 0.0
        if r.confidence is not None:
            acc["conf"].append(r.confidence)
        if r.month >= acc["last"].month:
            acc["last"] = r

    zone_rows: list[ZoneLossRow] = []
    for zone_id, acc in by_zone.items():
        zone = zones.get(zone_id)
        delivered = acc["delivered"]
        zone_rows.append(
            ZoneLossRow(
                zone_id=zone_id,
                name=zone.name if zone else zone_id,
                area_type=zone.area_type if zone else None,
                avg_distance_m=zone.avg_distance_m if zone else None,
                delivered_kwh=round(delivered, 1),
                billed_kwh=round(acc["billed"], 1),
                loss_kwh=round(acc["loss"], 1),
                loss_pct=round(100.0 * acc["loss"] / delivered, 1) if delivered else None,
                normal_technical_kwh=round(acc["normal"], 1),
                excess_technical_kwh=round(acc["excess"], 1),
                measurement_kwh=round(acc["measurement"], 1),
                unbilled_kwh=round(acc["unbilled"], 1),
                unexplained_kwh=round(acc["unexplained"], 1),
                unexplained_pct=round(100.0 * acc["unexplained"] / delivered, 1) if delivered else None,
                confidence=round(sum(acc["conf"]) / len(acc["conf"]), 2) if acc["conf"] else None,
                explanation=localize(_explain(acc, zone), lang),
            )
        )
    # Ranked by the part the owner can act on, not by the total. A zone losing
    # 14% of which all is cable length needs nothing; one losing 8% of which
    # half is unexplained needs a visit this week.
    zone_rows.sort(key=lambda z: (z.unexplained_pct or 0.0, z.loss_pct or 0.0), reverse=True)

    # --- FR-2.1 / 2.4 / 2.5 / 2.6 / 2.7: per generator ----------------------
    # Read from generator_month_metrics, not recomputed here. Phase imbalance
    # in particular CANNOT be computed correctly in one SQL pass: it is the
    # mean of each hour's imbalance, and averaging the three currents first
    # cancels out every set whose heavy phase moves around. Computing it that
    # way gave five of the seven sets 0.1% when the real figure is 5%.
    metric_rows = (
        db.query(GeneratorMonthMetrics)
        .filter(
            GeneratorMonthMetrics.month >= period_start,
            GeneratorMonthMetrics.month <= period_end,
        )
        .all()
    )
    by_gen: dict[str, dict] = {}
    for m in metric_rows:
        acc = by_gen.setdefault(
            m.generator_id,
            dict(produced=0.0, hours=0.0, fuel=None, imb=[], flagged=[], alarms=0),
        )
        acc["produced"] += m.produced_kwh or 0.0
        acc["hours"] += m.supply_hours or 0.0
        if m.fuel_litres is not None:
            acc["fuel"] = (acc["fuel"] or 0.0) + m.fuel_litres
        if m.phase_imbalance_pct is not None:
            acc["imb"].append(m.phase_imbalance_pct)
        if m.hours_above_flag_pct is not None:
            acc["flagged"].append(m.hours_above_flag_pct)
        acc["alarms"] += m.alarm_count or 0

    generators: list[GeneratorToday] = []
    for gen in db.query(Generator).order_by(Generator.priority).all():
        acc = by_gen.get(gen.generator_id)
        if acc is None:
            continue
        imbalance = round(sum(acc["imb"]) / len(acc["imb"]), 1) if acc["imb"] else None
        litres = acc["fuel"] if gen.ecu_connected else None
        generators.append(
            GeneratorToday(
                generator_id=gen.generator_id,
                name=gen.name,
                capacity_kw=gen.capacity_kw,
                produced_kwh_period=round(acc["produced"], 1),
                run_hours_period=round(acc["hours"], 1),
                fuel_litres_period=round(litres, 1) if litres else None,
                litres_per_kwh=round(litres / acc["produced"], 3)
                if litres and acc["produced"]
                else None,
                ecu_connected=bool(gen.ecu_connected),
                phase_imbalance_pct=imbalance,
                imbalance_flagged=bool(imbalance and imbalance > IMBALANCE_FLAG_PCT),
                active_alarms=int(acc["alarms"]),
            )
        )

    # --- FR-2.8: collections ------------------------------------------------
    invoiced = (
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0.0))
        .filter(Invoice.billing_period >= period_start, Invoice.billing_period <= period_end)
        .scalar()
    )
    collected = (
        db.query(func.coalesce(func.sum(InvoicePayment.amount), 0.0))
        .join(Invoice, Invoice.invoice_id == InvoicePayment.invoice_id)
        .filter(Invoice.billing_period >= period_start, Invoice.billing_period <= period_end)
        .scalar()
    )
    unpaid = (
        db.query(func.count(Invoice.invoice_id))
        .outerjoin(InvoicePayment, InvoicePayment.invoice_id == Invoice.invoice_id)
        .filter(
            Invoice.billing_period >= period_start,
            Invoice.billing_period <= period_end,
            InvoicePayment.payment_id.is_(None),
        )
        .scalar()
    )

    # --- FR-2.7: what is shouting right now ---------------------------------
    alarm_rows = (
        db.query(GeneratorAlarm)
        .filter(GeneratorAlarm.timestamp >= datetime.combine(period_start, datetime.min.time()))
        .order_by(GeneratorAlarm.timestamp.desc())
        .limit(20)
        .all()
    )

    # --- FR-2.10 / NFR-1: the good-outcome sentence -------------------------
    worst = zone_rows[0] if zone_rows else None
    flagged = [g for g in generators if g.imbalance_flagged]
    parts = [f"Total loss is {loss_pct:.1f}%." if loss_pct is not None else "Loss is not measurable."]
    if produced:
        normal = sum(z.normal_technical_kwh for z in zone_rows)
        measurement = sum(z.measurement_kwh for z in zone_rows)
        unexplained = sum(z.unexplained_kwh for z in zone_rows)
        parts.append(f"About {100 * normal / produced:.1f}% is normal technical loss, nothing to do.")
        if measurement:
            parts.append(
                f"About {100 * measurement / produced:.1f}% comes from the reading process, which is fixable."
            )
        if flagged:
            names = ", ".join(g.name for g in flagged)
            parts.append(f"{names} {'is' if len(flagged) == 1 else 'are'} running unbalanced; send a technician.")
        if unexplained and worst:
            parts.append(
                f"About {100 * unexplained / produced:.1f}% is unexplained and concentrates in "
                f"{worst.name}. That is where a visit is worth making."
            )

    return DashboardOut(
        as_of=anchor,
        period_start=period_start,
        period_end=period_end,
        is_live=anchor >= date.today(),
        produced_kwh=round(produced, 1),
        billed_kwh=round(billed, 1),
        gap_kwh=round(gap, 1),
        loss_pct=round(loss_pct, 1) if loss_pct is not None else None,
        generators=generators,
        zones=zone_rows,
        collections=Collections(
            invoiced=round(float(invoiced), 2),
            collected=round(float(collected), 2),
            outstanding=round(float(invoiced) - float(collected), 2),
            unpaid_invoices=int(unpaid or 0),
        ),
        alarms=[
            AlarmRow(
                generator_id=a.generator_id,
                generator_name=a.generator_name,
                timestamp=a.timestamp.isoformat(),
                severity=a.severity,
                message=a.message,
            )
            for a in alarm_rows
        ],
        summary=join_sentences(localize_all(parts, lang), lang),
    )


@router.get("/zones", response_model=list[ZoneLossRow])
def zones_by_loss(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """Every zone over the whole period, worst unexplained share first."""
    return dashboard(months=18, db=db, _=_, lang=lang).zones


@router.get("/zones/{zone_id}")
def zone_detail(
    zone_id: str,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """
    One zone, month by month.

    This is what answers "why is Al-Wadi worse than Yassine": the shape over
    time separates a cable that is ageing from a step that started in a
    particular month, which is the briefing's Test 3.
    """
    zone = db.get(Zone, zone_id)
    if zone is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")

    rows = (
        db.query(ZoneLossMonthly)
        .filter(ZoneLossMonthly.zone_id == zone_id)
        .order_by(ZoneLossMonthly.month)
        .all()
    )
    return {
        "zoneId": zone.zone_id,
        "name": zone.name,
        "areaType": zone.area_type,
        "altitudeBand": zone.altitude_band,
        "avgDistanceM": zone.avg_distance_m,
        "generatorId": zone.generator_id,
        "months": [
            {
                "month": r.month.isoformat(),
                "deliveredKwh": round(r.energy_delivered_kwh or 0.0, 1),
                "billedKwh": round(r.units_billed_kwh or 0.0, 1),
                "lossKwh": round(r.loss_kwh or 0.0, 1),
                "lossPct": round(r.loss_pct, 1) if r.loss_pct is not None else None,
                "normalTechnicalKwh": round(r.normal_technical_kwh or 0.0, 1),
                "excessTechnicalKwh": round(r.excess_technical_kwh or 0.0, 1),
                "measurementKwh": round(r.measurement_kwh or 0.0, 1),
                "unbilledKwh": round(r.unbilled_kwh or 0.0, 1),
                "unexplainedKwh": round(r.unexplained_kwh or 0.0, 1),
                "confidence": r.confidence,
                "methodNote": r.method_note,
            }
            for r in rows
        ],
    }


@router.get("/rules")
def simple_rules(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """
    Phase 3 Step 1: the rules, and the shortlist they produce.

    Capped at twenty, per the briefing: nobody can inspect two hundred, and a
    list that long is the same as no list. Every entry carries its evidence
    AND the innocent explanations for it, because the person reading this is
    deciding whether to knock on somebody's door.
    """
    from app.analytics import rules as rule_engine

    result = rule_engine.run_all(db)
    result["paymentDefaulters"] = rule_engine.payment_defaulters(db)
    result["note"] = localize(
        "A flag is a hypothesis for a field visit, not a verdict. This system cannot "
        "prove that anyone has taken anything: it reports that a pattern does not match "
        "what the data predicts and that the usual explanations do not account for it.",
        lang,
    )
    # The rules write in English and compare their own wording (SAME_CAUSE,
    # SAME_CHECK in app/analytics/rules.py), so the sentences are translated
    # here, after the engine has finished with them. Rule names stay as they
    # are: the page uses them as keys.
    for entry in result["shortlist"]:
        entry["evidence"] = localize_all(entry["evidence"], lang)
        entry["innocentExplanations"] = localize_all(entry["innocentExplanations"], lang)
        entry["visitChecks"] = localize_all(entry["visitChecks"], lang)
    for finding in result["gridFindings"]:
        finding["evidence"] = localize(finding["evidence"], lang)
        finding["action"] = localize(finding["action"], lang)
    return result


@router.get("/peak")
def peak_profile(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """
    Phase 4: the network's load by hour, and the ceiling on what shifting it saves.

    The ceiling is returned alongside the advice on purpose. Advice with no
    measure of its own size is how a helper gets presented as a solution.
    """
    from app.ai import peak_advice

    result = peak_advice.analyse(db)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No telemetry has been loaded, so the load profile cannot be measured.",
        )
    result["customerAdvice"] = peak_advice.advice_for_customer(db)
    return result


@router.post("/loss/refresh")
def refresh_loss(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """
    Rebuild the stored loss account.

    Needed after new readings arrive. The pipeline already does this at the end
    of a load; this is for the case where the data changed some other way.
    """
    written = loss_engine.refresh(db)
    return {"rebuilt": written}
