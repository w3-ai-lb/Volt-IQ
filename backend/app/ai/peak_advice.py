"""
Phase 4: advice worth giving, and an honest measurement of how little it buys.

WHAT THE ADVICE IS, AND WHAT IT IS NOT
--------------------------------------
Not "use less electricity". The owner SELLS electricity; telling his customers
to buy less is telling him to earn less, and he will stop using the system.

The advice is to move the same consumption off the peak hour. Loss follows
current SQUARED, so the same kilowatt-hours spread across the evening cost less
in heat than the same kilowatt-hours delivered in one spike. Same energy sold,
same revenue, less burned in the cable.

HOW MUCH IT IS ACTUALLY WORTH ON THIS NETWORK
---------------------------------------------
Measured, not assumed, and the answer is small.

The controllers show the system peaking at 19:00. If every kilowatt-hour were
redistributed perfectly flat across the supplied hours, which no advice could
ever achieve, the sum of I squared falls by about 5%. Technical loss is around
5.8% of everything delivered, so a PERFECT flattening saves roughly 0.3% of
total energy. Realistic partial shifting saves a fraction of that.

The briefing estimates 1-2% and says it plainly: "the chatbot is a helper, not
the solution. Never present it as the answer to loss." On this network the
measurement is lower still. Fixing one bad joint is worth 3%, and Nidal-6's
28% phase imbalance is worth more than every customer on the network changing
their habits.

That comparison is the point of this module. It computes the advice AND the
ceiling on what the advice can do, so nobody has to take either on faith.
"""

from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.network import GeneratorTelemetry

logger = logging.getLogger(__name__)

# An hour with fewer samples than this is not a load profile, it is noise.
MIN_SAMPLES_PER_HOUR = 100


def load_profile(db: Session) -> pd.DataFrame:
    """Average current by hour of day, across every generator."""
    rows = db.query(
        GeneratorTelemetry.timestamp,
        GeneratorTelemetry.current_l1,
        GeneratorTelemetry.current_l2,
        GeneratorTelemetry.current_l3,
        GeneratorTelemetry.active_power_kw,
    ).all()
    df = pd.DataFrame(rows, columns=["ts", "l1", "l2", "l3", "kw"]).dropna(
        subset=["l1", "l2", "l3"]
    )
    if df.empty:
        return df

    df["hour"] = pd.to_datetime(df.ts).dt.hour
    df["current"] = df[["l1", "l2", "l3"]].mean(axis=1)
    by_hour = df.groupby("hour").agg(
        amps=("current", "mean"), kw=("kw", "mean"), samples=("current", "size")
    )
    # Hours the generators are not usually running say nothing about load.
    return by_hour[by_hour.samples >= MIN_SAMPLES_PER_HOUR].reset_index()


_CACHE: dict[tuple, dict | None] = {}


def _fingerprint(db: Session) -> tuple:
    """
    Cheap identity for the telemetry table: how many rows, and the newest one.

    Both change when the pipeline loads a file and neither changes otherwise, so
    a cached answer is thrown away exactly when the data behind it moves. Two
    aggregates over an indexed column cost a fraction of a millisecond; the
    analysis they guard costs three tenths of a second.
    """
    return db.query(
        func.count(GeneratorTelemetry.id), func.max(GeneratorTelemetry.timestamp)
    ).one()


def analyse(db: Session) -> dict | None:
    """
    The peak, and the most that moving load off it could ever save.

    The saving is computed against a PERFECTLY flat profile, which is not
    achievable by anyone. It is quoted as a ceiling for exactly that reason:
    the useful number is not what shifting saves, it is what shifting cannot
    exceed.

    MEMOISED, AND WHY IT HAD TO BE
    ------------------------------
    This pulls all 48,013 telemetry rows into pandas and groups them by hour.
    The chatbot calls it on EVERY message, to frame the peak and savings advice,
    so every question a customer asked cost a full scan of the generator
    telemetry: about three tenths of a second of pure CPU for a result that is
    identical for every customer and changes only when the pipeline loads new
    data. Two hundred subscribers asking one question each is a minute of the
    server doing the same arithmetic two hundred times.

    The answer is network-wide by design (see `advice_for_customer`), which is
    what makes it cacheable at all: there is nothing per-customer in it.
    """
    key = _fingerprint(db)
    if key in _CACHE:
        return _CACHE[key]

    profile = load_profile(db)
    if profile.empty:
        _CACHE[key] = None
        return None

    peak = profile.loc[profile.amps.idxmax()]
    quiet = profile.loc[profile.amps.idxmin()]

    # Loss is proportional to the sum of I squared over the hours.
    loss_now = float((profile.amps**2).sum())
    flat = float(profile.amps.mean())
    loss_flat = float((flat**2) * len(profile))
    ceiling_pct = 100.0 * (loss_now - loss_flat) / loss_now if loss_now else 0.0

    result = {
        "peakHour": int(peak.hour),
        "peakAmps": round(float(peak.amps), 1),
        "quietHour": int(quiet.hour),
        "quietAmps": round(float(quiet.amps), 1),
        "peakToQuietRatio": round(float(peak.amps / quiet.amps), 2) if quiet.amps else None,
        "hours": [
            {"hour": int(r.hour), "amps": round(float(r.amps), 1), "kw": round(float(r.kw or 0), 1)}
            for r in profile.itertuples()
        ],
        # The ceiling, stated as one.
        "maxTechnicalLossReductionPct": round(ceiling_pct, 1),
        "honestNote": (
            f"Moving load off {int(peak.hour):02d}:00 reduces heat in the cable because loss "
            f"follows current squared. Flattening the profile PERFECTLY, which no advice can "
            f"achieve, would cut technical loss by about {ceiling_pct:.0f}%, and technical loss "
            f"is a small part of the total. Realistic shifting saves a fraction of that. "
            f"Correcting the phase imbalance on a single generator is worth more than every "
            f"customer changing their habits."
        ),
    }
    _CACHE[key] = result
    return result


def advice_for_customer(db: Session, lang: str = "en") -> list[str]:
    """
    What a subscriber can usefully be told.

    Framed as the network's peak rather than the individual's, because meter
    readings are monthly and this system does not know any one subscriber's
    hour-by-hour profile. Claiming otherwise would be inventing a figure about
    somebody's own home, which is the worst place to do it.

    The Arabic wording lives here rather than in the chatbot because the
    MEASUREMENT lives here. Two sentences describing the same peak hour, one in
    each language, belong beside the analysis that produced the hour; splitting
    them would leave the chatbot free to phrase a number this module owns.
    """
    result = analyse(db)
    if result is None:
        return []
    peak = result["peakHour"]
    before = max(0, peak - 1)
    ratio = result["peakToQuietRatio"]

    if lang == "ar":
        return [
            f"تبلغ الشبكة ذروتها عند الساعة {peak:02d}:00. وتشغيل الغسّالة أو سخّان الماء "
            f"قبل {before:02d}:00 لا يكلّفك شيئاً ويخفّف الضغط عن الخط الذي يتشاركه الجميع.",
            f"الحِمل عند {peak:02d}:00 يساوي {ratio} ضعف أهدأ ساعة. وتوزيع الاستهلاك نفسه "
            f"على المساء يعني كهرباء أقل تتحوّل حرارةً في الكابل بدل أن تصل إلى البيوت.",
        ]

    return [
        f"The network is busiest at {peak:02d}:00. Running the washing machine or the water "
        f"heater before {before:02d}:00 costs you nothing and puts less strain on "
        f"the line everyone shares.",
        f"Load at {peak:02d}:00 is {ratio}x the quietest hour. Spreading "
        f"the same use across the evening means less electricity turning into heat in the "
        f"cable instead of reaching a home.",
    ]
