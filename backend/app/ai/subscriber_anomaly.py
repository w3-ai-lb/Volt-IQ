"""
Phase 3, Step 3: a model, and the bar it has to clear.

    "The rule: the AI must beat the simple rules. If the rules catch 60% and
     the model catches 55%, the rules win. Reporting that honestly is a good
     result, not a failure."

WHY UNSUPERVISED
----------------
IsolationForest never sees a label. That is not a limitation here, it is the
point: a model fitted to the labels it is later scored against produces a
number that measures nothing, and an examiner is entitled to ask whether that
happened. With an unsupervised model the answer is structural, it could not
have, because the labels are not an input to anything in this file.

It also matches the situation the owner is actually in. Nobody has a list of
confirmed cases. The briefing says so plainly, and says the chatbot's hidden
value is that it would start building one.

HOW THE COMPARISON IS MADE FAIR
-------------------------------
The model flags the SAME NUMBER of subscribers the rules flag. An owner has a
fixed number of afternoons; the honest question is not "how many can each
method flag" but "given twenty visits, whose method finds more". Letting the
model flag a hundred and then celebrating its recall would be comparing a
shortlist with a phone book.

WHAT IS DELIBERATELY NOT A FEATURE
----------------------------------
Anything about payment. The rules exclude non-payment from the loss shortlist
on principle, the electricity was delivered, measured and billed correctly,
and the meter is telling the truth, so giving the model that signal would let
it win on a category its opponent was forbidden to enter.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.models.subscription import Meter, MeterReading, Subscription

logger = logging.getLogger(__name__)

# Every feature, with the reason it might carry signal. A feature nobody can
# justify is a feature nobody can defend when the model is questioned.
FEATURES = {
    "mean_kwh": "how much this subscriber uses at all",
    "cv": "how unstable that use is month to month",
    "trend_pct": "whether it drifted up or down across the record",
    "worst_drop_pct": "the deepest single-month fall",
    "second_half_ratio": "whether a fall persisted rather than rebounding",
    "zero_months": "months the dial did not move",
    "flat_run": "the longest run of identical readings",
    "mean_ocr": "how well the readings could be recognised",
    "corrected_share": "how often a reading needed correcting by hand",
    "kwh_per_ampere": "use against the capacity actually contracted",
    "ratio_to_zone": "use against neighbours on the same feeder, same weather, same tariff",
    "disconnected_months": "months read while the account was marked disconnected",
}


def build_features(db: Session) -> pd.DataFrame:
    """One row per subscriber, from readings and contracts only."""
    rows = (
        db.query(
            Subscription.subscriber_id,
            Subscription.subscription_id,
            Subscription.zone_id,
            Subscription.ampere_capacity,
            Subscription.phase_type,
            MeterReading.billing_period,
            MeterReading.reading_value,
            MeterReading.ocr_confidence,
            MeterReading.was_corrected,
            MeterReading.subscription_status,
            Meter.digit_count,
            Meter.initial_reading,
        )
        .join(MeterReading, MeterReading.subscription_id == Subscription.subscription_id)
        .outerjoin(Meter, Meter.meter_id == MeterReading.meter_id)
        .all()
    )
    df = pd.DataFrame(
        rows,
        columns=[
            "subscriber_id", "subscription_id", "zone_id", "ampere_capacity", "phase_type",
            "period", "reading", "ocr", "corrected", "status", "digit_count", "initial_reading",
        ],
    )
    if df.empty:
        return df

    df["period"] = pd.to_datetime(df.period)
    df = df.sort_values(["subscription_id", "period"])
    # Seeded from the dial at installation so the first month counts. The model
    # is given the same eighteen months the rules see; anything else would make
    # the comparison between them a comparison of two different datasets.
    df["prev"] = df.groupby("subscription_id").reading.shift(1).fillna(df.initial_reading)
    df["consumed"] = df.reading - df.prev

    records = []
    for sub, g in df.groupby("subscriber_id"):
        used = g.consumed.dropna()
        if len(used) < 4:
            continue
        mean = float(used.mean())
        half = len(used) // 2
        first = float(used.iloc[:half].mean())
        second = float(used.iloc[half:].mean())

        flat = used.eq(0)
        longest_flat = int(flat.groupby((~flat).cumsum()).cumsum().max()) if len(flat) else 0

        deltas = used.pct_change().replace([np.inf, -np.inf], np.nan).dropna()

        records.append(
            {
                "subscriber_id": str(sub),
                "zone_id": g.zone_id.iloc[0],
                "mean_kwh": mean,
                "cv": float(used.std() / mean) if mean else 0.0,
                "trend_pct": 100.0 * (second - first) / first if first else 0.0,
                "worst_drop_pct": float(-deltas.min() * 100) if len(deltas) else 0.0,
                "second_half_ratio": second / first if first else 1.0,
                "zero_months": int(flat.sum()),
                "flat_run": longest_flat,
                "mean_ocr": float(g.ocr.mean()) if g.ocr.notna().any() else 1.0,
                "corrected_share": float(g.corrected.fillna(False).mean()),
                "kwh_per_ampere": mean / float(g.ampere_capacity.iloc[0])
                if g.ampere_capacity.iloc[0] else 0.0,
                "disconnected_months": int((g.status == "disconnected").sum()),
            }
        )

    out = pd.DataFrame(records)
    if out.empty:
        return out

    # The zones are the natural control the briefing describes: same generator,
    # same month, same weather, same tariff. Comparing a subscriber with the
    # median of their own feeder removes most of what is merely geography.
    zone_median = out.groupby("zone_id").mean_kwh.transform("median")
    out["ratio_to_zone"] = out.mean_kwh / zone_median.replace(0, np.nan)
    out["ratio_to_zone"] = out.ratio_to_zone.fillna(1.0)
    return out


def detect(db: Session, budget: int | None = None, seed: int = 42) -> pd.DataFrame:
    """
    Rank every subscriber by how unusual their behaviour is.

    `budget` is how many to flag. Passing the number the rules flagged is what
    makes the two comparable: the same number of doors, and the question is
    only whose list is better.
    """
    features = build_features(db)
    if features.empty:
        return features

    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    X = features[list(FEATURES)].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    X_scaled = StandardScaler().fit_transform(X)

    budget = budget or max(1, int(len(features) * 0.1))
    contamination = min(0.5, max(1e-4, budget / len(features)))

    forest = IsolationForest(
        n_estimators=300,
        contamination=contamination,
        random_state=seed,   # fixed, so the same data gives the same shortlist
    )
    forest.fit(X_scaled)

    # Lower score = more isolated = more unusual.
    features["anomaly_score"] = -forest.score_samples(X_scaled)
    features["flagged"] = forest.predict(X_scaled) == -1
    return features.sort_values("anomaly_score", ascending=False)


def explain(row: pd.Series, population: pd.DataFrame) -> str:
    """
    Why this subscriber stands out, in the features' own terms.

    A score with no explanation is not actionable and cannot be argued with,
    and the briefing requires that a flag be a hypothesis somebody can go and
    check rather than a number to be trusted.
    """
    reasons = []
    for name, meaning in FEATURES.items():
        value = row.get(name)
        if value is None or pd.isna(value):
            continue
        column = population[name].replace([np.inf, -np.inf], np.nan).dropna()
        if column.std() == 0:
            continue
        z = (value - column.mean()) / column.std()
        if abs(z) >= 2.0:
            direction = "unusually high" if z > 0 else "unusually low"
            reasons.append(f"{meaning} is {direction} ({name}={value:,.2f})")
    return "; ".join(reasons[:3]) or "no single feature stands out; the combination does"
