"""
Phase 3, Step 1: the simple rules. No model anywhere in this file.

    "Build these before touching a model. Then count how many of the known
     anomalies these rules catch. Write the number down. That number is your
     baseline."

WHY THIS COMES FIRST, AND WHY IT MATTERS THAT IT DOES
-----------------------------------------------------
The briefing sets the bar the models have to clear: if the rules catch 60% and
a model catches 55%, the rules win, and reporting that honestly is a good
result. A baseline nobody measured is a bar nobody has to clear, and every
model then looks impressive.

So this is written to be beaten. Each rule is deliberately simple, states its
own evidence, and is scored separately, because "the rules caught 58%" is much
less useful than knowing which rule found what.

WHAT A FLAG IS
--------------
A hypothesis for a field visit. Never a verdict, and never the word theft. Two
of these rules describe a broken meter, one describes a cable, and the one
people reach for first, a sustained drop in consumption, has at least four
innocent explanations. The output is a ranked shortlist with the reason
attached, so somebody can go and look.

WHAT THESE RULES CANNOT REACH, BY CONSTRUCTION
----------------------------------------------
Two of the briefing's six are properties of a GENERATOR, not a subscriber:
phase imbalance and litres per kWh. They matter, they are reported, and they
can never appear in a per-subscriber score. Saying so is part of the result.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.generator_metrics import GeneratorMonthMetrics
from app.models.invoice import Invoice, InvoicePayment
from app.models.network import Generator
from app.models.subscription import Subscriber, Meter, MeterReading, Subscription

logger = logging.getLogger(__name__)

IMBALANCE_FLAG_PCT = 15.0

# A drop this deep, sustained rather than for one month, is what the briefing
# describes as the signature of a partial bypass. It is also what a broken air
# conditioner, an empty house or a change of tenant looks like.
SUSTAINED_DROP_PCT = 40.0

# Volts a single phase supplies at. Used only to turn an ampere limit into a
# kWh ceiling, which is why it is written down here rather than buried.
NOMINAL_VOLTAGE = 220.0

# See over_draw(). Set from measurement error, not from what makes the score
# look better.
OVER_DRAW_MARGIN = 0.20


# Two rules can offer the same explanation in different words. A subscriber who
# trips both the stuck meter and the sustained drop was being shown "the
# property is empty" and "the household travelled or the property emptied" one
# after the other, which is one reason printed twice and makes the list read
# like padding. Explanations that name the same cause share a key here and only
# the fullest wording survives the merge.
SAME_CAUSE = {
    "the property is empty": "empty property",
    "the household travelled or the property emptied": "empty property",
}


# What to look at on the visit, per rule.
#
# These are instructions about the METER AND THE SUPPLY, never about the
# person. The shortlist deliberately reaches no conclusion, and until now that
# left it with nothing actionable on it either: whoever was sent had the
# evidence and the innocent explanations and no idea what to do at the door.
# Each line below is something that can be checked in five minutes and that
# settles which explanation is the true one.
VISIT_CHECKS = {
    "stuck_meter": [
        "Read the dial on site and compare it with the last recorded reading.",
        "Switch on a known load and watch whether the meter advances.",
    ],
    "sustained_drop": [
        "Read the dial on site to confirm the meter is still recording.",
        "Ask what changed in the household around the month the drop began.",
    ],
    "disconnected_use": [
        "Confirm at the pole whether the supply is physically disconnected.",
        "Check the disconnection date on file against what the field team did.",
    ],
    "over_draw": [
        "Check the ampere limit on the contract against the breaker actually fitted.",
        "Check whether more than one property is fed from this meter.",
    ],
    "reading_went_backwards": [
        "Check whether the meter was replaced, and record the new serial and its "
        "starting reading.",
        "Re-read the dial and compare it with the figure on file.",
    ],
}


def merge_explanations(flags) -> list[str]:
    """Every innocent explanation across a subscriber's flags, each cause once."""
    best: dict[str, str] = {}
    for flag in flags:
        for text in flag.innocent_explanations:
            key = SAME_CAUSE.get(text, text)
            if key not in best or len(text) > len(best[key]):
                best[key] = text
    return sorted(best.values())


# The same collapsing as SAME_CAUSE, for the checks. A subscriber who trips both
# the stuck meter and the sustained drop was being told twice to read the dial.
SAME_CHECK = {
    "Read the dial on site and compare it with the last recorded reading.": "read the dial",
    "Read the dial on site to confirm the meter is still recording.": "read the dial",
    "Re-read the dial and compare it with the figure on file.": "read the dial",
}


def visit_checks(flags) -> list[str]:
    """
    What to check on site, for the rules this subscriber actually tripped.

    Order is kept: the first rule to ask for something is the one whose wording
    survives, so the check that comes from the strongest finding leads.
    """
    out: list[str] = []
    seen: set[str] = set()
    for flag in flags:
        for check in VISIT_CHECKS.get(flag.rule, []):
            key = SAME_CHECK.get(check, check)
            if key in seen:
                continue
            seen.add(key)
            out.append(check)
    return out


@dataclass
class Flag:
    """One subscriber, one rule, and the evidence for it."""

    subscriber_id: str
    rule: str
    # 0..1. Not a probability of guilt: a measure of how far past the rule's
    # threshold this case sits, used only to rank a shortlist.
    strength: float
    evidence: str
    zone_id: str | None = None
    innocent_explanations: list[str] = field(default_factory=list)


@dataclass
class GridFinding:
    """A finding about a generator rather than about a person."""

    generator_id: str
    generator_name: str
    rule: str
    evidence: str
    action: str


# ---------------------------------------------------------------------------
def _readings(db: Session) -> pd.DataFrame:
    """
    Every reading with its subscription and meter, sorted for differencing.

    THE FIRST MONTH IS NOT FREE
    ---------------------------
    Consumption is the difference between two readings, so a plain shift()
    leaves the earliest reading of every meter with nothing to subtract and
    drops it. That is one month of eighteen for all 300 subscribers: a fifth
    of a year of evidence, gone before any rule sees it, and gone silently.

    It is recoverable. `meters.initial_reading` is the dial when the meter was
    installed, it is present on every meter in this dataset, and seeding the
    difference with it reproduces the supervisor's own billed units exactly.
    Every rule below therefore judges eighteen months, not seventeen.
    """
    rows = (
        db.query(
            MeterReading.subscription_id,
            Subscription.subscriber_id,
            Subscription.zone_id,
            Subscription.ampere_capacity,
            Subscription.phase_type,
            MeterReading.billing_period,
            MeterReading.reading_value,
            MeterReading.subscription_status,
            MeterReading.ocr_confidence,
            Meter.digit_count,
            Meter.initial_reading,
        )
        .join(Subscription, Subscription.subscription_id == MeterReading.subscription_id)
        .outerjoin(Meter, Meter.meter_id == MeterReading.meter_id)
        .all()
    )
    df = pd.DataFrame(
        rows,
        columns=[
            "subscription_id", "subscriber_id", "zone_id", "ampere_capacity", "phase_type",
            "period", "reading", "status_at_reading", "ocr", "digit_count", "initial_reading",
        ],
    )
    if df.empty:
        return df
    df["period"] = pd.to_datetime(df.period)
    df = df.sort_values(["subscription_id", "period"])
    df["prev"] = df.groupby("subscription_id").reading.shift(1)
    # Only the first row of each meter is still empty; fill it from the dial at
    # installation. A meter without one keeps its NaN and its first month is
    # skipped, which is the honest outcome rather than a difference from zero.
    df["prev"] = df.prev.fillna(df.initial_reading)
    df["consumed"] = df.reading - df.prev
    return df


# --- rule 1 ----------------------------------------------------------------
def disconnected_but_consuming(df: pd.DataFrame) -> list[Flag]:
    """
    Status says disconnected, the dial still moved.

    The briefing calls this "one line of code, no AI at all", and it is, but
    only if the line reads the right column. `subscriptions.status` holds
    TODAY's status and says 'active' for every row in this dataset, so a rule
    written against it finds nothing and looks like a clean result. The status
    AT THE TIME OF READING is what matters, and it lives on the reading.
    """
    if df.empty:
        return []
    hits = df[(df.status_at_reading == "disconnected") & (df.consumed.fillna(0) > 0)]
    out = []
    for sub, group in hits.groupby("subscriber_id"):
        total = float(group.consumed.sum())
        out.append(
            Flag(
                subscriber_id=str(sub),
                rule="disconnected_use",
                strength=min(1.0, len(group) / 6.0),
                evidence=(
                    f"{len(group)} month(s) recorded consumption while the account was marked "
                    f"disconnected, {total:,.0f} kWh in total"
                ),
                zone_id=group.zone_id.iloc[0],
                innocent_explanations=[
                    "the disconnection was never carried out in the field",
                    "the status was recorded late or in error",
                ],
            )
        )
    return out


# --- rule 2 ----------------------------------------------------------------
def stuck_meter(df: pd.DataFrame) -> list[Flag]:
    """The same number three months running: the meter, not the customer."""
    if df.empty:
        return []
    out = []
    for sub, group in df.groupby("subscriber_id"):
        same = group.consumed.fillna(-1).eq(0)
        run = same.rolling(3).sum()
        if (run >= 3).any():
            longest = int(same.groupby((~same).cumsum()).cumsum().max())
            out.append(
                Flag(
                    subscriber_id=str(sub),
                    rule="stuck_meter",
                    strength=min(1.0, longest / 6.0),
                    evidence=f"identical reading for {longest} consecutive months",
                    zone_id=group.zone_id.iloc[0],
                    innocent_explanations=[
                        "the property is empty",
                        "the meter has failed and needs replacing",
                    ],
                )
            )
    return out


# --- rule 3 ----------------------------------------------------------------
def reading_went_backwards(df: pd.DataFrame) -> list[Flag]:
    """
    A reading lower than the one before it.

    Tested for dial rollover FIRST. A five-digit meter passing 99999 returns to
    zero and produces an apparently negative consumption that looks exactly
    like a reversed meter. Throwing away digit_count is how a rollover becomes
    an accusation.
    """
    if df.empty:
        return []
    drops = df[df.consumed.notna() & (df.consumed < 0)]
    out = []
    for sub, group in drops.groupby("subscriber_id"):
        for row in group.itertuples():
            digits = int(row.digit_count) if pd.notna(row.digit_count) else 5
            wrap = 10 ** digits
            # If adding one full turn of the dial gives a plausible month, it
            # was a rollover and there is nothing to report.
            if 0 < row.consumed + wrap < wrap * 0.2:
                continue
            out.append(
                Flag(
                    subscriber_id=str(sub),
                    rule="reading_went_backwards",
                    strength=0.8,
                    evidence=(
                        f"reading fell by {abs(row.consumed):,.0f} in "
                        f"{row.period:%B %Y}, which a {digits}-digit rollover does not explain"
                    ),
                    zone_id=row.zone_id,
                    innocent_explanations=[
                        "the meter was replaced and the new one started from zero",
                        "the reading was mistyped or misread",
                    ],
                )
            )
            break
    return out


# --- rule 4 ----------------------------------------------------------------
def over_draw(df: pd.DataFrame, supply_hours: pd.DataFrame | None = None) -> list[Flag]:
    """
    More energy than the contracted ampere limit can physically deliver.

    The ceiling is amperes x volts x phases x THE HOURS THE ZONE WAS ACTUALLY
    SUPPLIED. That last part is the whole rule.

    The first version of this used 24 hours a day, on the reasoning that a
    ceiling nobody could exceed even with the generator running non-stop would
    never produce a false accusation. It produced no accusation at all: this
    network supplies about 12.6 hours a day, so the ceiling was roughly twice
    what any subscriber could physically draw and the rule scored 0 of 12.
    A threshold set so wide that it can never fire is not caution, it is a
    rule that does nothing while looking careful.

    Supply hours are measured per zone per month from zone_energy_daily, so a
    quiet month raises no flags and a long one is judged against its own length.

    NOTE FOR THE REPORT: this is the one threshold revised after the rules were
    scored against the labels. The reason is physical rather than statistical
    and is checkable without them, but the reader should know it, and both
    figures are reported.
    """
    if df.empty:
        return []
    d = df.dropna(subset=["consumed", "ampere_capacity"]).copy()
    phases = d.phase_type.eq("three_phase").map({True: 3, False: 1})

    if supply_hours is not None and not supply_hours.empty:
        d = d.merge(supply_hours, on=["zone_id", "period"], how="left")
        hours = d.supply_hours_month.fillna(supply_hours.supply_hours_month.median())
    else:
        hours = pd.Series(12.6 * 30, index=d.index)

    d["ceiling_kwh"] = d.ampere_capacity * NOMINAL_VOLTAGE * phases / 1000.0 * hours

    # A margin above the ceiling, for measurement rather than for caution.
    # A reading carries OCR uncertainty, the meter month and the generator month
    # are different windows, and 220 V is nominal rather than measured. A month
    # that lands a few percent over the line is inside that noise; one that
    # lands 20% over is not.
    hits = d[d.consumed > d.ceiling_kwh * (1.0 + OVER_DRAW_MARGIN)]
    out = []
    for sub, group in hits.groupby("subscriber_id"):
        worst = group.loc[group.consumed.idxmax()]
        ratio = float(worst.consumed / worst.ceiling_kwh)
        out.append(
            Flag(
                subscriber_id=str(sub),
                rule="over_draw",
                strength=min(1.0, (ratio - 1.0)),
                evidence=(
                    f"used {worst.consumed:,.0f} kWh in {worst.period:%B %Y} against a "
                    f"{worst.ampere_capacity:.0f} A limit that allows at most "
                    f"{worst.ceiling_kwh:,.0f} kWh over the hours that zone was supplied"
                ),
                zone_id=worst.zone_id,
                innocent_explanations=[
                    "the contracted capacity on record is out of date",
                    "two properties share one meter",
                ],
            )
        )
    return out


# --- rule 4b: the sustained drop -------------------------------------------
def sustained_drop(df: pd.DataFrame) -> list[Flag]:
    """
    Consumption fell by 40% or more and stayed down.

    Not one of the briefing's six, and included because the briefing's own
    description of a partial bypass is exactly this shape: "Customer's
    consumption drops 40-60% and stays down, while neighbours stay the same."

    It is also the rule most likely to be wrong about a person, so it carries
    the longest list of innocent explanations and its strength is capped: a
    drop is a reason to ask a question, and the question is the point.
    """
    if df.empty:
        return []
    out = []
    for sub, group in df.groupby("subscriber_id"):
        values = group.consumed.dropna().values
        if len(values) < 8:
            continue
        half = len(values) // 2
        before, after = values[:half].mean(), values[half:].mean()
        if before <= 0:
            continue
        drop = 100.0 * (before - after) / before
        if drop < SUSTAINED_DROP_PCT:
            continue
        out.append(
            Flag(
                subscriber_id=str(sub),
                rule="sustained_drop",
                strength=min(0.9, drop / 100.0),
                evidence=(
                    f"average monthly use fell from {before:,.0f} kWh to {after:,.0f} kWh, "
                    f"down {drop:.0f}%, and stayed down"
                ),
                zone_id=group.zone_id.iloc[0],
                innocent_explanations=[
                    "the household travelled or the property emptied",
                    "an air conditioner or water heater broke and was not replaced",
                    "the tenant changed",
                    "a genuine effort to use less",
                ],
            )
        )
    return out


# --- rules 5 and 6: about generators, not people ---------------------------
def grid_findings(db: Session) -> list[GridFinding]:
    """
    Phase imbalance and fuel ratio.

    These are two of the briefing's six rules and neither can ever appear in a
    per-subscriber score, because neither is about a subscriber. They are the
    findings that cost the owner nothing to act on and no customer anything to
    be accused of, which is the briefing's point about where the real money is.
    """
    findings: list[GridFinding] = []
    names = {g.generator_id: g.name for g in db.query(Generator).all()}

    rows = (
        db.query(
            GeneratorMonthMetrics.generator_id,
            func.avg(GeneratorMonthMetrics.phase_imbalance_pct),
            func.avg(GeneratorMonthMetrics.hours_above_flag_pct),
        )
        .group_by(GeneratorMonthMetrics.generator_id)
        .all()
    )
    # Worst first, which the screen above this list promises and the query did
    # not deliver: with no ordering the rows came back by generator id, so
    # Boura-2 at 16.7% was listed above Nidal-6 at 28.3% under a heading that
    # says "fix these first". The order IS the recommendation on a list a
    # supervisor works down.
    rows = sorted(rows, key=lambda row: float(row[1] or 0.0), reverse=True)
    for gid, imbalance, hours in rows:
        if imbalance is not None and imbalance > IMBALANCE_FLAG_PCT:
            findings.append(
                GridFinding(
                    generator_id=gid,
                    generator_name=names.get(gid, gid),
                    rule="phase_imbalance",
                    evidence=(
                        f"average imbalance {imbalance:.1f}% against a {IMBALANCE_FLAG_PCT:.0f}% "
                        f"threshold, above it for {hours or 0:.0f}% of running hours"
                    ),
                    action="Send a technician to balance the loads across the three phases.",
                )
            )

    # Fuel ratio drifting upward: engine wear, or diesel leaving another way.
    fuel = (
        db.query(
            GeneratorMonthMetrics.generator_id,
            GeneratorMonthMetrics.month,
            GeneratorMonthMetrics.litres_per_kwh,
        )
        .filter(GeneratorMonthMetrics.litres_per_kwh.isnot(None))
        .order_by(GeneratorMonthMetrics.generator_id, GeneratorMonthMetrics.month)
        .all()
    )
    df = pd.DataFrame(fuel, columns=["generator_id", "month", "lpk"])
    for gid, group in df.groupby("generator_id"):
        if len(group) < 6:
            continue
        half = len(group) // 2
        early = group.lpk.iloc[:half].mean()
        late = group.lpk.iloc[half:].mean()
        if early and (late - early) / early > 0.05:
            findings.append(
                GridFinding(
                    generator_id=gid,
                    generator_name=names.get(gid, gid),
                    rule="fuel_ratio_rising",
                    evidence=(
                        f"litres per kWh rose from {early:.3f} to {late:.3f}, "
                        f"up {100 * (late - early) / early:.0f}%"
                    ),
                    action="Service the engine, and check the fuel record against deliveries.",
                )
            )
    return findings


# ---------------------------------------------------------------------------
def _supply_hours_by_zone_month(db: Session) -> pd.DataFrame:
    """Hours each zone was actually supplied, per month."""
    from app.models.network import ZoneEnergyDaily

    rows = db.query(ZoneEnergyDaily.zone_id, ZoneEnergyDaily.date,
                    ZoneEnergyDaily.supply_hours).all()
    df = pd.DataFrame(rows, columns=["zone_id", "date", "hours"])
    if df.empty:
        return df
    df["period"] = pd.to_datetime(df.date).dt.to_period("M").dt.to_timestamp()
    return (
        df.groupby(["zone_id", "period"], as_index=False)
        .hours.sum()
        .rename(columns={"hours": "supply_hours_month"})
    )


def run_all(db: Session) -> dict:
    """
    Every rule, and the shortlist they produce.

    The shortlist is capped at twenty. The briefing is specific: rank the top
    20 for inspection, not 200, because nobody can check 200 and a list that
    long is the same as no list.
    """
    df = _readings(db)

    per_rule = {
        "disconnected_use": disconnected_but_consuming(df),
        "stuck_meter": stuck_meter(df),
        "reading_went_backwards": reading_went_backwards(df),
        "over_draw": over_draw(df, _supply_hours_by_zone_month(db)),
        "sustained_drop": sustained_drop(df),
    }

    # One subscriber can trip several rules, and that is itself evidence: the
    # combination is more interesting than any single flag.
    combined: dict[str, list[Flag]] = {}
    for flags in per_rule.values():
        for flag in flags:
            combined.setdefault(flag.subscriber_id, []).append(flag)

    # A shortlist is a list of people to go and visit, so it carries their names.
    # Until the identity pipeline ran there were none and S00060 was all anybody
    # could be told; now that every subscriber has a record, sending a collector
    # to "S00060 in Z08" when the system knows it is Ali Kanaan in Harjali is a
    # gap between what is known and what is shown.
    names = {
        subscriber_id: (name, zone_name)
        for subscriber_id, name, zone_name in db.query(
            Subscriber.subscriber_id, Customer.name, Customer.region
        ).join(Customer, Customer.customer_id == Subscriber.customer_id)
    }

    shortlist = sorted(
        (
            {
                "subscriberId": sub,
                "subscriberName": names.get(sub, (None, None))[0],
                "zoneName": names.get(sub, (None, None))[1],
                "zoneId": flags[0].zone_id,
                "rules": [f.rule for f in flags],
                "score": round(min(1.0, sum(f.strength for f in flags) / 2.0), 2),
                "evidence": [f.evidence for f in flags],
                "innocentExplanations": merge_explanations(flags),
                "visitChecks": visit_checks(flags),
            }
            for sub, flags in combined.items()
        ),
        key=lambda r: (len(r["rules"]), r["score"]),
        reverse=True,
    )

    total_subscribers = db.query(func.count()).select_from(Subscription).scalar() or 0
    return {
        "perRule": {name: [f.subscriber_id for f in flags] for name, flags in per_rule.items()},
        "flaggedSubscribers": sorted(combined),
        "flaggedCount": len(combined),
        "totalSubscribers": total_subscribers,
        "shortlist": shortlist[:20],
        "gridFindings": [
            {
                "generatorId": g.generator_id,
                "generatorName": g.generator_name,
                "rule": g.rule,
                "evidence": g.evidence,
                "action": g.action,
            }
            for g in grid_findings(db)
        ],
    }


def payment_defaulters(db: Session, min_unpaid: int = 3) -> list[str]:
    """
    Subscribers with several unpaid invoices.

    Kept out of run_all() on purpose. Not paying is a collections matter, not
    an energy-loss one: the electricity was delivered, measured and billed
    correctly, and the meter is telling the truth. Mixing it into a loss
    shortlist would send a technician to look for a bypass at a house whose
    only problem is a bill.
    """
    rows = (
        db.query(Invoice.subscriber_id, func.count(Invoice.invoice_id))
        .outerjoin(InvoicePayment, InvoicePayment.invoice_id == Invoice.invoice_id)
        .filter(InvoicePayment.payment_id.is_(None))
        .group_by(Invoice.subscriber_id)
        .having(func.count(Invoice.invoice_id) >= min_unpaid)
        .all()
    )
    return sorted(str(s) for s, _ in rows)
