"""
The numeric half of the question interface (FR-2.12, FR-2.14, FR-2.15).

THE RULE THIS FILE EXISTS TO ENFORCE
------------------------------------
    "The absolute rule: the LLM must NEVER invent a number. Every figure in an
     answer must come from a query result."

That is a promise about structure, not about prompting, so it is kept
structurally. Each intent below does two things and they are separate: `run()`
executes a query and returns a dictionary of facts, and `phrase()` writes a
sentence using only keys from that dictionary. Nothing else in the system is
allowed to put a digit into an answer. When a language model is added it is
given the facts and the sentence; it may rewrite the wording and may not touch
the arithmetic.

WHY THE PERIOD IS ANCHORED TO THE DATA, NOT TO TODAY
----------------------------------------------------
The dataset in hand ends in June 2026. Answering about August because that is
what the calendar says would report an empty month as a quiet one, so every
period is measured against the newest month the database actually holds, and
every answer states which month produced its figures.

While data is still arriving, "this month" is the month in progress and "last
month" is the one before it. Once it stops, the newest month on record is the
most recent month there is anything to say about, and both phrases resolve to
it. See `resolve_period`.

FR-2.16 asks for a documented list of what is supported and what is not. That
list is generated from this registry rather than written beside it, so the two
cannot drift apart. See `catalogue()`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.generator_metrics import GeneratorMonthMetrics
from app.models.invoice import Invoice, InvoicePayment
from app.models.loss import ZoneLossMonthly
from app.models.network import Generator, Zone
from app.models.subscription import Meter, MeterReading, Subscription

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def latest_month(db: Session) -> date | None:
    return db.query(func.max(ZoneLossMonthly.month)).scalar()


def _previous(month: date) -> date:
    return (month.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)


def _month_name(month: date) -> str:
    return month.strftime("%B %Y")


def resolve_period(db: Session, question: str) -> tuple[date, date, str]:
    """
    Work out which months a question is about.

    Returns (start, end, how it was described). The description is put in the
    answer, because "last month" is ambiguous the moment the data stops before
    today, and an owner reading a figure needs to know which month produced it.
    """
    newest = latest_month(db)
    if newest is None:
        return date.today(), date.today(), "no data"

    q = question.lower()

    named = re.search(r"\b(" + "|".join(MONTHS) + r")\b", q)
    year = re.search(r"\b(20\d{2})\b", q)
    if named:
        m = MONTHS[named.group(1)]
        y = int(year.group(1)) if year else newest.year
        target = date(y, m, 1)
        if target > newest:                       # asked about a month we do not have
            target = date(newest.year - 1, m, 1)
        return target, target, _month_name(target)

    # Is the newest month on record the month the calendar is actually in?
    #
    # WHY THIS TEST EXISTS
    # --------------------
    # It did not, and "last month" was answered as the month before the newest
    # one on record. The readings stop at June 2026, so the owner asking about
    # last month was given MAY, while the dashboard on the same screen was
    # showing June and calling it the latest month. Two answers to the same
    # question, a screen apart.
    #
    # The step back only makes sense while data is arriving: then the newest
    # month is the one in progress and last month is the one before it. Once the
    # data stops, the newest month on record IS the most recent month there is
    # anything to say about, and both phrases have to land on it. The answer
    # then says which month it used, because the owner did not ask for June and
    # should not have to work out that he got it.
    live = newest >= date.today().replace(day=1)

    if "last month" in q or "previous month" in q or "الشهر الماضي" in q:
        if live:
            prev = _previous(newest)
            return prev, prev, _month_name(prev)
        return newest, newest, f"{_month_name(newest)} (the newest month on record)"

    if "this month" in q or "current month" in q or "هالشهر" in q:
        if live:
            return newest, newest, _month_name(newest)
        return newest, newest, f"{_month_name(newest)} (the newest month on record)"

    if "this year" in q or "year" in q:
        start = date(newest.year, 1, 1)
        return start, newest, f"{newest.year}"

    if "all" in q or "total" in q or "overall" in q or "ever" in q:
        oldest = db.query(func.min(ZoneLossMonthly.month)).scalar() or newest
        return oldest, newest, f"{_month_name(oldest)} to {_month_name(newest)}"

    # Default: the newest month on record, and say so, for the same reason as
    # above. A question with no period in it gets the most recent figures there
    # are, labelled with the month that produced them.
    if live:
        return newest, newest, _month_name(newest)
    return newest, newest, f"{_month_name(newest)} (the newest month on record)"


def _find_zone(db: Session, question: str) -> Zone | None:
    q = question.lower()
    for zone in db.query(Zone).all():
        if zone.name.lower() in q or zone.zone_id.lower() in q:
            return zone
    return None


def _find_zones(db: Session, question: str) -> list[Zone]:
    q = question.lower()
    found = [(q.index(z.name.lower()), z) for z in db.query(Zone).all() if z.name.lower() in q]
    return [z for _, z in sorted(found)]


def _find_generator(db: Session, question: str) -> Generator | None:
    q = question.lower()
    for gen in db.query(Generator).all():
        if gen.name.lower() in q or gen.generator_id.lower() in q:
            return gen
    return None


def _sum_loss(db: Session, start: date, end: date, zone_id: str | None = None) -> dict:
    query = db.query(
        func.sum(ZoneLossMonthly.energy_delivered_kwh),
        func.sum(ZoneLossMonthly.units_billed_kwh),
        func.sum(ZoneLossMonthly.loss_kwh),
        func.sum(ZoneLossMonthly.normal_technical_kwh),
        func.sum(ZoneLossMonthly.excess_technical_kwh),
        func.sum(ZoneLossMonthly.measurement_kwh),
        func.sum(ZoneLossMonthly.unbilled_kwh),
        func.sum(ZoneLossMonthly.unexplained_kwh),
    ).filter(ZoneLossMonthly.month >= start, ZoneLossMonthly.month <= end)
    if zone_id:
        query = query.filter(ZoneLossMonthly.zone_id == zone_id)
    d, b, loss, normal, excess, meas, unb, unexp = query.one()
    delivered = float(d or 0.0)
    return {
        "delivered_kwh": round(delivered, 1),
        "billed_kwh": round(float(b or 0.0), 1),
        "loss_kwh": round(float(loss or 0.0), 1),
        "loss_pct": round(100.0 * float(loss or 0.0) / delivered, 1) if delivered else None,
        "normal_technical_kwh": round(float(normal or 0.0), 1),
        "excess_technical_kwh": round(float(excess or 0.0), 1),
        "measurement_kwh": round(float(meas or 0.0), 1),
        "unbilled_kwh": round(float(unb or 0.0), 1),
        "unexplained_kwh": round(float(unexp or 0.0), 1),
        "unexplained_pct": round(100.0 * float(unexp or 0.0) / delivered, 1) if delivered else None,
    }


# ---------------------------------------------------------------------------
@dataclass
class Intent:
    name: str
    description: str
    examples: list[str]
    patterns: list[str]
    run: Callable[[Session, str], dict | None]
    phrase: Callable[[dict], str]
    tables: list[str] = field(default_factory=list)

    def matches(self, question: str) -> bool:
        q = question.lower()
        return any(re.search(p, q) for p in self.patterns)


# --- 1. total loss ---------------------------------------------------------
def _run_total_loss(db: Session, question: str) -> dict | None:
    start, end, described = resolve_period(db, question)
    facts = _sum_loss(db, start, end)
    if not facts["delivered_kwh"]:
        return None
    facts["period"] = described
    return facts


def _phrase_total_loss(f: dict) -> str:
    parts = [
        f"In {f['period']} the generators delivered {f['delivered_kwh']:,.0f} kWh and the meters "
        f"accounted for {f['billed_kwh']:,.0f} kWh, a difference of {f['loss_kwh']:,.0f} kWh "
        f"({f['loss_pct']}%)."
    ]
    if f["delivered_kwh"]:
        def pct(value: float) -> float:
            return 100.0 * value / f["delivered_kwh"]

        parts.append(
            f"Of that, about {pct(f['normal_technical_kwh']):.1f}% is normal technical loss with "
            f"nothing to be done, {pct(f['measurement_kwh']):.1f}% comes from the reading process, "
            f"{pct(f['unbilled_kwh']):.1f}% is your own unbilled supply, and "
            f"{f['unexplained_pct']}% is unexplained."
        )
    return " ".join(parts)


# --- 2. worst zone ---------------------------------------------------------
def _run_worst_zone(db: Session, question: str) -> dict | None:
    start, end, described = resolve_period(db, question)
    rows = (
        db.query(
            ZoneLossMonthly.zone_id,
            func.sum(ZoneLossMonthly.energy_delivered_kwh),
            func.sum(ZoneLossMonthly.loss_kwh),
            func.sum(ZoneLossMonthly.unexplained_kwh),
        )
        .filter(ZoneLossMonthly.month >= start, ZoneLossMonthly.month <= end)
        .group_by(ZoneLossMonthly.zone_id)
        .all()
    )
    if not rows:
        return None
    names = {z.zone_id: z.name for z in db.query(Zone).all()}
    ranked = sorted(
        (
            {
                "zone": names.get(zid, zid),
                "delivered_kwh": round(float(d or 0), 1),
                "loss_pct": round(100.0 * float(lost or 0) / float(d), 1) if d else None,
                "unexplained_pct": round(100.0 * float(u or 0) / float(d), 1) if d else None,
            }
            for zid, d, lost, u in rows
        ),
        key=lambda r: r["loss_pct"] or 0.0,
        reverse=True,
    )
    return {"period": described, "ranked": ranked[:5], "worst": ranked[0]}


def _phrase_worst_zone(f: dict) -> str:
    w = f["worst"]
    by_unexplained = sorted(f["ranked"], key=lambda r: r["unexplained_pct"] or 0.0, reverse=True)[0]
    line = (
        f"In {f['period']} the highest total loss is {w['zone']} at {w['loss_pct']}%. "
        f"Next: " + ", ".join(f"{r['zone']} {r['loss_pct']}%" for r in f["ranked"][1:4]) + "."
    )
    if by_unexplained["zone"] != w["zone"]:
        line += (
            f" Worth knowing: the largest UNEXPLAINED share is {by_unexplained['zone']} at "
            f"{by_unexplained['unexplained_pct']}%, and that is the one worth visiting, a high "
            f"total loss is often just cable length."
        )
    return line


# --- 3. one zone -----------------------------------------------------------
def _run_zone_loss(db: Session, question: str) -> dict | None:
    zone = _find_zone(db, question)
    if zone is None:
        return None
    start, end, described = resolve_period(db, question)
    facts = _sum_loss(db, start, end, zone.zone_id)
    if not facts["delivered_kwh"]:
        return None
    facts.update(
        {"period": described, "zone": zone.name, "distance_m": zone.avg_distance_m,
         "area_type": zone.area_type}
    )
    return facts


def _phrase_zone_loss(f: dict) -> str:
    where = f" It sits {f['distance_m']:.0f} m from its generator." if f.get("distance_m") else ""
    return (
        f"{f['zone']} was sent {f['delivered_kwh']:,.0f} kWh in {f['period']} and was billed for "
        f"{f['billed_kwh']:,.0f} kWh, losing {f['loss_kwh']:,.0f} kWh ({f['loss_pct']}%). "
        f"{f['unexplained_pct']}% of what it was sent is unexplained.{where}"
    )


# --- 4. compare two zones --------------------------------------------------
def _run_compare_zones(db: Session, question: str) -> dict | None:
    zones = _find_zones(db, question)
    if len(zones) < 2:
        return None
    start, end, described = resolve_period(db, question)
    out = []
    for zone in zones[:2]:
        facts = _sum_loss(db, start, end, zone.zone_id)
        facts.update(
            {"zone": zone.name, "distance_m": zone.avg_distance_m, "area_type": zone.area_type}
        )
        out.append(facts)
    if not all(z["delivered_kwh"] for z in out):
        return None
    return {"period": described, "a": out[0], "b": out[1]}


def _phrase_compare_zones(f: dict) -> str:
    a, b = f["a"], f["b"]
    line = (
        f"In {f['period']}, {a['zone']} lost {a['loss_pct']}% and {b['zone']} lost {b['loss_pct']}%."
    )
    reasons = []
    if a.get("distance_m") and b.get("distance_m") and a["distance_m"] != b["distance_m"]:
        further, nearer = (a, b) if a["distance_m"] > b["distance_m"] else (b, a)
        reasons.append(
            f"{further['zone']} is {further['distance_m']:.0f} m from its generator against "
            f"{nearer['distance_m']:.0f} m, and loss rises with cable length"
        )
    if (a["unexplained_pct"] or 0) != (b["unexplained_pct"] or 0):
        higher = a if (a["unexplained_pct"] or 0) > (b["unexplained_pct"] or 0) else b
        reasons.append(
            f"the unexplained share is {higher['unexplained_pct']}% in {higher['zone']} against "
            f"{(b if higher is a else a)['unexplained_pct']}% in {(b if higher is a else a)['zone']}"
        )
    if reasons:
        joined = "; ".join(reasons)
        line += " " + joined[0].upper() + joined[1:] + "."
    line += (
        " Distance and load are the first things to rule out; what is left after them is what "
        "justifies a visit."
    )
    return line


# --- 5. generator run hours ------------------------------------------------
def _run_generator_hours(db: Session, question: str) -> dict | None:
    gen = _find_generator(db, question)
    if gen is None:
        return None
    start, end, described = resolve_period(db, question)
    hours, produced = (
        db.query(
            func.sum(GeneratorMonthMetrics.supply_hours),
            func.sum(GeneratorMonthMetrics.produced_kwh),
        )
        .filter(
            GeneratorMonthMetrics.generator_id == gen.generator_id,
            GeneratorMonthMetrics.month >= start,
            GeneratorMonthMetrics.month <= end,
        )
        .one()
    )
    if hours is None and produced is None:
        return None
    return {
        "generator": gen.name,
        "period": described,
        "hours": round(float(hours or 0.0), 1),
        "produced_kwh": round(float(produced or 0.0), 1),
    }


def _phrase_generator_hours(f: dict) -> str:
    return (
        f"{f['generator']} supplied for {f['hours']:,.0f} hours in {f['period']} and produced "
        f"{f['produced_kwh']:,.0f} kWh."
    )


# --- 6. fuel per kWh, this month against last ------------------------------
def _run_fuel_per_kwh(db: Session, question: str) -> dict | None:
    newest = latest_month(db)
    if newest is None:
        return None
    prev = _previous(newest)

    def for_month(month: date) -> list[dict]:
        rows = (
            db.query(GeneratorMonthMetrics, Generator.name)
            .join(Generator, Generator.generator_id == GeneratorMonthMetrics.generator_id)
            .filter(GeneratorMonthMetrics.month == month)
            .all()
        )
        return [
            {"generator": name, "litres_per_kwh": m.litres_per_kwh, "ecu": m.ecu_connected}
            for m, name in rows
        ]

    now, before = for_month(newest), for_month(prev)
    measured = [r for r in now if r["litres_per_kwh"] is not None]
    if not measured:
        return None
    prev_by_name = {r["generator"]: r["litres_per_kwh"] for r in before}
    return {
        "this_month": _month_name(newest),
        "last_month": _month_name(prev),
        "measured": [
            {**r, "previous": prev_by_name.get(r["generator"])} for r in measured
        ],
        "not_measured": [r["generator"] for r in now if r["litres_per_kwh"] is None],
    }


def _phrase_fuel_per_kwh(f: dict) -> str:
    lines = []
    for r in f["measured"]:
        if r["previous"]:
            change = r["litres_per_kwh"] - r["previous"]
            direction = "up" if change > 0 else "down" if change < 0 else "unchanged"
            lines.append(
                f"{r['generator']} burned {r['litres_per_kwh']} litres per kWh in "
                f"{f['this_month']} against {r['previous']} in {f['last_month']}, {direction}"
            )
        else:
            lines.append(
                f"{r['generator']} burned {r['litres_per_kwh']} litres per kWh in {f['this_month']}"
            )
    out = ". ".join(lines) + "."
    if f["not_measured"]:
        out += (
            f" No fuel figure exists for {', '.join(f['not_measured'])}: their engine control "
            f"units are not connected, so the controller reports nothing to measure."
        )
    return out


# --- 7. is loss getting better or worse ------------------------------------
def _run_loss_trend(db: Session, question: str) -> dict | None:
    rows = (
        db.query(
            ZoneLossMonthly.month,
            func.sum(ZoneLossMonthly.energy_delivered_kwh),
            func.sum(ZoneLossMonthly.loss_kwh),
        )
        .group_by(ZoneLossMonthly.month)
        .order_by(ZoneLossMonthly.month)
        .all()
    )
    series = [
        {"month": _month_name(m), "loss_pct": round(100.0 * float(lost or 0) / float(d), 1)}
        for m, d, lost in rows
        if d
    ]
    if len(series) < 3:
        return None
    half = len(series) // 2
    early = sum(s["loss_pct"] for s in series[:half]) / half
    late = sum(s["loss_pct"] for s in series[half:]) / (len(series) - half)
    return {
        "months": len(series),
        "first": series[0],
        "last": series[-1],
        "early_avg": round(early, 1),
        "late_avg": round(late, 1),
        "change": round(late - early, 1),
        "series": series,
    }


def _phrase_loss_trend(f: dict) -> str:
    direction = (
        "getting worse" if f["change"] > 0.3
        else "improving" if f["change"] < -0.3
        else "steady"
    )
    return (
        f"Across {f['months']} months, loss averaged {f['early_avg']}% in the first half and "
        f"{f['late_avg']}% in the second, so it is {direction} by {abs(f['change'])} points. "
        f"It was {f['first']['loss_pct']}% in {f['first']['month']} and "
        f"{f['last']['loss_pct']}% in {f['last']['month']}."
    )


# --- 8. who has not paid ---------------------------------------------------
def _run_unpaid(db: Session, question: str) -> dict | None:
    m = re.search(r"(\d+)\s*(month|شهر)", question.lower())
    months = int(m.group(1)) if m else 3

    rows = (
        db.query(Invoice.subscriber_id, func.count(Invoice.invoice_id))
        .outerjoin(InvoicePayment, InvoicePayment.invoice_id == Invoice.invoice_id)
        .filter(InvoicePayment.payment_id.is_(None))
        .group_by(Invoice.subscriber_id)
        .having(func.count(Invoice.invoice_id) >= months)
        .all()
    )
    if not rows:
        return {"months": months, "count": 0, "subscribers": []}

    zone_of = {
        s: z
        for s, z in db.query(Subscription.subscriber_id, Subscription.zone_id).all()
    }
    names = {z.zone_id: z.name for z in db.query(Zone).all()}
    listed = sorted(
        (
            {"subscriber_id": sid, "unpaid_invoices": int(n),
             "zone": names.get(zone_of.get(sid), "unknown")}
            for sid, n in rows
        ),
        key=lambda r: r["unpaid_invoices"],
        reverse=True,
    )
    return {"months": months, "count": len(listed), "subscribers": listed[:20]}


def _phrase_unpaid(f: dict) -> str:
    if not f["count"]:
        return f"No subscriber has {f['months']} or more unpaid invoices."
    top = ", ".join(
        f"{s['subscriber_id']} ({s['unpaid_invoices']} in {s['zone']})" for s in f["subscribers"][:5]
    )
    more = " The top 20 are listed." if f["count"] > 5 else ""
    return (
        f"{f['count']} subscribers have {f['months']} or more unpaid invoices. "
        f"The largest are {top}.{more}"
    )


# --- 9. consumption that dropped -------------------------------------------
def _run_consumption_drop(db: Session, question: str) -> dict | None:
    m = re.search(r"(\d+)\s*%", question)
    threshold = float(m.group(1)) if m else 40.0

    rows = (
        db.query(
            MeterReading.subscription_id,
            MeterReading.billing_period,
            MeterReading.reading_value,
        )
        .order_by(MeterReading.subscription_id, MeterReading.billing_period)
        .all()
    )
    if not rows:
        return None

    # Seeded from the dial at installation, so the first month of each meter is
    # a month of evidence like any other rather than one silently discarded.
    consumption: dict[str, list[float]] = {}
    previous: dict[str, float] = {
        subscription_id: float(value)
        for subscription_id, value in db.query(Meter.subscription_id, Meter.initial_reading).all()
        if value is not None
    }
    for sub, _period, value in rows:
        if sub in previous:
            consumption.setdefault(sub, []).append(float(value) - previous[sub])
        previous[sub] = float(value)

    zone_of = {s: z for s, z in db.query(Subscription.subscription_id, Subscription.zone_id).all()}
    sub_of = {s: b for s, b in db.query(Subscription.subscription_id, Subscription.subscriber_id).all()}
    names = {z.zone_id: z.name for z in db.query(Zone).all()}

    found = []
    for sub, values in consumption.items():
        # Compare a settled recent window with a settled earlier one, so a
        # single quiet month does not read as a drop.
        if len(values) < 8:
            continue
        half = len(values) // 2
        before = sum(values[:half]) / half
        after = sum(values[half:]) / (len(values) - half)
        if before <= 0:
            continue
        drop = 100.0 * (before - after) / before
        if drop >= threshold:
            found.append(
                {
                    "subscriber_id": sub_of.get(sub, sub),
                    "zone": names.get(zone_of.get(sub), "unknown"),
                    "before_kwh": round(before, 1),
                    "after_kwh": round(after, 1),
                    "drop_pct": round(drop, 1),
                }
            )
    found.sort(key=lambda r: r["drop_pct"], reverse=True)
    return {"threshold_pct": threshold, "count": len(found), "subscribers": found[:20]}


def _phrase_consumption_drop(f: dict) -> str:
    if not f["count"]:
        return f"No subscriber's consumption has fallen by {f['threshold_pct']:.0f}% or more."
    top = ", ".join(
        f"{s['subscriber_id']} in {s['zone']} ({s['before_kwh']:,.0f} kWh to {s['after_kwh']:,.0f}, "
        f"down {s['drop_pct']}%)"
        for s in f["subscribers"][:5]
    )
    return (
        f"{f['count']} subscribers show a sustained fall of {f['threshold_pct']:.0f}% or more. "
        f"The largest are {top}. A fall like this can be a bypass, but it can equally be a broken "
        f"appliance, an empty house or a short circuit; it is a reason to ask, not a finding."
    )


# --- 10. collections -------------------------------------------------------
def _run_collections(db: Session, question: str) -> dict | None:
    start, end, described = resolve_period(db, question)
    invoiced = (
        db.query(func.coalesce(func.sum(Invoice.total_amount), 0.0))
        .filter(Invoice.billing_period >= start, Invoice.billing_period <= end)
        .scalar()
    )
    collected = (
        db.query(func.coalesce(func.sum(InvoicePayment.amount), 0.0))
        .join(Invoice, Invoice.invoice_id == InvoicePayment.invoice_id)
        .filter(Invoice.billing_period >= start, Invoice.billing_period <= end)
        .scalar()
    )
    if not invoiced:
        return None
    return {
        "period": described,
        "invoiced": round(float(invoiced), 0),
        "collected": round(float(collected), 0),
        "outstanding": round(float(invoiced) - float(collected), 0),
        "collection_rate": round(100.0 * float(collected) / float(invoiced), 1),
    }


def _phrase_collections(f: dict) -> str:
    return (
        f"In {f['period']} you invoiced {f['invoiced']:,.0f} LBP and collected "
        f"{f['collected']:,.0f}, which is {f['collection_rate']}%. "
        f"{f['outstanding']:,.0f} LBP is outstanding."
    )


# --- 11. which generator is unbalanced -------------------------------------
def _run_imbalance(db: Session, question: str) -> dict | None:
    start, end, described = resolve_period(db, question)
    rows = (
        db.query(
            Generator.name,
            func.avg(GeneratorMonthMetrics.phase_imbalance_pct),
            func.avg(GeneratorMonthMetrics.hours_above_flag_pct),
        )
        .join(Generator, Generator.generator_id == GeneratorMonthMetrics.generator_id)
        .filter(GeneratorMonthMetrics.month >= start, GeneratorMonthMetrics.month <= end)
        .group_by(Generator.name)
        .all()
    )
    measured = [
        {"generator": n, "imbalance_pct": round(float(i), 1),
         "hours_above_flag_pct": round(float(h or 0), 1)}
        for n, i, h in rows
        if i is not None
    ]
    if not measured:
        return None
    measured.sort(key=lambda r: r["imbalance_pct"], reverse=True)
    return {"period": described, "generators": measured,
            "flagged": [g for g in measured if g["imbalance_pct"] > 15.0]}


def _phrase_imbalance(f: dict) -> str:
    if not f["flagged"]:
        worst = f["generators"][0]
        return (
            f"No generator is above the 15% imbalance threshold in {f['period']}. The highest is "
            f"{worst['generator']} at {worst['imbalance_pct']}%."
        )
    lines = ", ".join(
        f"{g['generator']} at {g['imbalance_pct']}% (above the threshold for "
        f"{g['hours_above_flag_pct']}% of hours)"
        for g in f["flagged"]
    )
    return (
        f"In {f['period']}, {lines}. Unequal phase currents return through the neutral, which "
        f"heats the cable and serves no customer. This is fixable by a technician."
    )


# ---------------------------------------------------------------------------
INTENTS: list[Intent] = [
    # ORDER IS SIGNIFICANT, and it is specificity, not importance.
    #
    # match() returns intents in this order and the first whose query
    # returns facts wins. An intent that needs a named zone or generator is
    # tried before one that answers from any question at all, because
    # "why is Al-Wadi worse than Yassine" contains the word "worse" and was
    # being answered with the overall loss trend until this was fixed.
    #
    # The generic ones sit at the bottom on purpose: they are the fallback
    # for a question that named nothing in particular.
    Intent(
        name="compare_zones",
        description="Compare two named zones and say what explains the difference",
        examples=["Why is Al-Wadi worse than Yassine?"],
        patterns=[r"\bwhy is\b.*\b(worse|better|higher|lower)\b", r"compare .* (and|with|to) ",
                  r"\bversus\b", r"\bvs\b"],
        run=_run_compare_zones, phrase=_phrase_compare_zones, tables=["zone_loss_monthly", "zones"],
    ),
    Intent(
        name="zone_loss",
        description="Loss for one named zone",
        examples=["How much does Al-Wadi lose?", "Al-Wadi loss in March"],
        patterns=[r"\b(loss|lose|lost)\b", r"كم .*منطقة"],
        run=_run_zone_loss, phrase=_phrase_zone_loss, tables=["zone_loss_monthly", "zones"],
    ),
    Intent(
        name="generator_hours",
        description="How long a named generator supplied, and what it produced",
        examples=["How many hours did Hasan-4 run in July?"],
        patterns=[r"how (many|long) .*(hour|run|ran)", r"\brun hours\b", r"كم ساعة"],
        run=_run_generator_hours, phrase=_phrase_generator_hours,
        tables=["generator_month_metrics", "generators"],
    ),
    Intent(
        name="phase_imbalance",
        description="Which generators are running unbalanced, and by how much",
        examples=["Which generator is unbalanced?", "Phase imbalance"],
        patterns=[r"imbalance|unbalanc", r"phase", r"اختلال"],
        run=_run_imbalance, phrase=_phrase_imbalance, tables=["generator_month_metrics"],
    ),
    Intent(
        name="fuel_per_kwh",
        description="Litres of diesel per kWh, this month against last, per generator",
        examples=["How much fuel did I burn per kWh this month compared to last month?"],
        patterns=[r"fuel (burn|consum|use|per|rate)", r"burn.*fuel", r"litre|liter",
                  r"(fuel|diesel).*(per|kwh)", r"مازوت|وقود"],
        run=_run_fuel_per_kwh, phrase=_phrase_fuel_per_kwh, tables=["generator_month_metrics"],
    ),
    Intent(
        name="unpaid",
        description="Subscribers with unpaid invoices, ranked",
        examples=["Which customers have not paid for three months?"],
        patterns=[r"(not|haven't|have not|hasn't) paid", r"unpaid", r"owe", r"outstanding .*customer",
                  r"ما دفع"],
        run=_run_unpaid, phrase=_phrase_unpaid, tables=["invoices", "invoice_payments"],
    ),
    Intent(
        name="consumption_drop",
        description="Subscribers whose consumption fell by more than a given percentage",
        examples=["Show me customers whose consumption dropped more than 40%"],
        patterns=[r"(drop|dropped|fell|fall|decrease).*(consumption|usage|%)",
                  r"consumption .*(drop|fell|down)", r"انخفض"],
        run=_run_consumption_drop, phrase=_phrase_consumption_drop,
        tables=["meter_readings", "subscriptions"],
    ),
    Intent(
        name="collections",
        description="Invoiced against collected, and what is outstanding",
        examples=["How much did I invoice and collect this month?", "What is outstanding?"],
        patterns=[r"(invoice|collect|revenue|income|outstanding|paid)", r"محصّل|فواتير"],
        run=_run_collections, phrase=_phrase_collections, tables=["invoices", "invoice_payments"],
    ),
    Intent(
        name="loss_trend",
        description="Whether loss is improving or worsening over the whole record",
        examples=["Is my loss getting better or worse?"],
        patterns=[r"(better|worse|improving|trend|going up|going down)", r"يتحسن|يسوء"],
        run=_run_loss_trend, phrase=_phrase_loss_trend, tables=["zone_loss_monthly"],
    ),
    Intent(
        name="worst_zone",
        description="Which neighbourhood loses most, and which has the largest unexplained share",
        examples=["Which neighbourhood has the highest loss?", "Worst zone?"],
        patterns=[r"which (neighbourhood|neighborhood|zone|area)", r"(highest|worst|most) loss",
                  r"\bworst zone\b", r"أي منطقة"],
        run=_run_worst_zone, phrase=_phrase_worst_zone, tables=["zone_loss_monthly", "zones"],
    ),
    Intent(
        name="total_loss",
        description="Total energy loss for a period, and the five-way split of it",
        examples=["How much did I lose last month?", "What is my loss this year?"],
        patterns=[r"how much .*(lose|lost|loss)", r"\bmy loss\b", r"total loss", r"كم .*خسر"],
        run=_run_total_loss, phrase=_phrase_total_loss, tables=["zone_loss_monthly"],
    ),
]

def catalogue() -> list[dict]:
    """
    FR-2.16: the documented list of what can be asked.

    Generated from the registry rather than written beside it, so a question
    type cannot be advertised and missing, or supported and undocumented.
    """
    return [
        {
            "name": i.name,
            "description": i.description,
            "examples": i.examples,
            "readsFrom": i.tables,
        }
        for i in INTENTS
    ]


def match(question: str) -> list[Intent]:
    """Every intent whose patterns fire, most specific first."""
    hits = [i for i in INTENTS if i.matches(question)]
    # compare_zones and zone_loss both fire on a question naming two zones;
    # the more specific one is listed first in INTENTS and wins.
    return hits
