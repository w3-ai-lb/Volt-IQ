"""
AI Module, Anomaly Detection.

Primary model : IsolationForest (scikit-learn), unsupervised outlier
                detection over per-customer daily consumption features.
Fallback      : robust z-score against a 30-day rolling median.

Detects the four categories the platform reports:
  * Unusual Consumption, sustained deviation from the customer's own baseline
  * Abnormal Spike     , sharp short-term increase
  * Possible Fraud     , sharp sustained drop (meter tampering signature)
  * Meter Error        , missing readings / flat-lined meter
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, time, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics import asof
from app.models.anomaly import Anomaly
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.subscription import Subscriber

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 90
MIN_DAYS_REQUIRED = 14

# A day has to differ from the customer's own baseline by at least this much
# before it is worth reporting.
#
# Without it the detector reports something for everybody. IsolationForest is
# told to treat 6% of days as outliers, so it always returns roughly five days
# per customer whether or not anything happened, and the three most extreme of
# those got reported regardless of how ordinary they were. Measured against the
# faults the seeder plants, that gave 94% of customers a finding and a precision
# of 6%. A list that flags everyone tells staff nothing.
#
# 25% matches where the severity scale already starts calling a deviation
# meaningful: below 20% it is rated "low", which is to say normal variation.
MIN_DEVIATION_PCT = 25.0

# ...and it has to be unusual for THAT customer, not just large in percentage
# terms. A household whose daily usage routinely swings by half is not having
# an incident when it swings by half again; a steady commercial site is.
# Robust z-score, so a couple of extreme days cannot inflate the spread and
# hide everything else behind them.
MIN_ROBUST_Z = 3.0

# Days either side used to establish "normal" for a given day.
#
# The comparison used to be against the median of the whole 90-day window,
# which silently compared July against April. Across a seasonal transition that
# range is legitimately close to 2:1, so ordinary summer days looked extreme
# against a spring median and the detector flagged 94% of customers. Measured
# per customer, the deliberately planted faults sat at robust z of 5.6 to 17.2
# while untouched customers reached 51: no threshold could separate them,
# because the thing being measured was mostly the season.
#
# Three weeks is long enough to average out weekday and weather variation and
# short enough that the season barely moves inside it.
LOCAL_BASELINE_DAYS = 21


def _daily_frame(db: Session, customer_id: str, since: datetime) -> pd.DataFrame:
    rows = (
        db.query(Consumption.timestamp, Consumption.kwh)
        .filter(Consumption.customer_id == customer_id, Consumption.timestamp >= since)
        .order_by(Consumption.timestamp)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["date", "kwh"])

    df = pd.DataFrame(rows, columns=["timestamp", "kwh"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    daily = df.set_index("timestamp")["kwh"].resample("D").sum().reset_index()
    daily.columns = ["date", "kwh"]

    # Drop today. Resampling gives today a bucket holding only the hours that
    # have happened so far, so a normal day in progress sums well below a full
    # one: which the classifier reads as a sharp drop and reports as possible
    # meter tampering. Left in, it flagged every customer for fraud every day.
    today = pd.Timestamp(datetime.now(UTC).replace(tzinfo=None).date())
    daily = daily[daily["date"] < today].reset_index(drop=True)

    return daily


def _severity_from_deviation(pct: float) -> str:
    magnitude = abs(pct)
    if magnitude >= 60:
        return "critical"
    if magnitude >= 35:
        return "high"
    if magnitude >= 20:
        return "medium"
    return "low"


def _classify(pct: float, is_flat: bool) -> tuple[str, str]:
    """Return (anomaly_type, description)."""
    if is_flat:
        return (
            "Meter Error",
            "No readings received for an extended period. Possible hardware or "
            "communication fault at the meter.",
        )
    if pct <= -50:
        return (
            "Possible Fraud",
            "Reported usage dropped sharply against the customer's established "
            "baseline, a known meter-tampering signature. Recommend field inspection.",
        )
    if pct >= 35:
        return (
            "Abnormal Spike",
            f"Consumption rose {pct:.0f}% above the 30-day rolling baseline within a "
            "short window. Possible appliance fault or unreported load.",
        )
    return (
        "Unusual Consumption",
        f"Consumption deviates {pct:+.0f}% from this customer's normal pattern, "
        "detected by the AI model.",
    )


def _detect_with_isolation_forest(daily: pd.DataFrame) -> list[int]:
    """Return positional indices flagged as outliers, or [] if unavailable."""
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
    except ImportError:  # pragma: no cover
        return []

    if len(daily) < MIN_DAYS_REQUIRED:
        return []

    frame = daily.copy()
    frame["rolling_mean"] = frame["kwh"].rolling(7, min_periods=1).mean()
    frame["deviation"] = frame["kwh"] - frame["rolling_mean"]
    frame["pct_change"] = frame["kwh"].pct_change().fillna(0).replace([np.inf, -np.inf], 0)

    features = frame[["kwh", "deviation", "pct_change"]].to_numpy(dtype=float)
    try:
        scaled = StandardScaler().fit_transform(features)
        model = IsolationForest(contamination=0.06, random_state=42, n_estimators=120)
        labels = model.fit_predict(scaled)
        return [i for i, label in enumerate(labels) if label == -1]
    except Exception as exc:  # pragma: no cover
        logger.warning("IsolationForest failed: %s", exc)
        return []


def _local_baseline(daily: pd.DataFrame) -> np.ndarray:
    """
    What each day should have looked like, from the days around it.

    A centred rolling median, so a day is judged against its own part of the
    year rather than against the whole window. Centred rather than trailing so
    that the day after an incident is not measured against the incident.
    """
    return (
        daily["kwh"]
        .rolling(LOCAL_BASELINE_DAYS, center=True, min_periods=5)
        .median()
        .bfill()
        .ffill()
        .to_numpy(dtype=float)
    )


def _robust_z(daily: pd.DataFrame) -> np.ndarray:
    """
    Robust z-score of each day against its own local baseline.

    Median and MAD rather than mean and standard deviation, because the days
    being looked for are exactly the ones that would drag a mean along with
    them and hide themselves.
    """
    values = daily["kwh"].to_numpy(dtype=float)
    baseline = _local_baseline(daily)
    residuals = values - baseline

    mad = float(np.median(np.abs(residuals - np.median(residuals))))
    if mad == 0:
        mad = float(np.std(residuals))
    if mad == 0:
        return np.zeros(len(values))
    return 0.6745 * (residuals - np.median(residuals)) / mad


def _detect_with_zscore(daily: pd.DataFrame) -> list[int]:
    """Robust z-score fallback, used when scikit-learn is unavailable."""
    if len(daily) < MIN_DAYS_REQUIRED:
        return []
    scores = _robust_z(daily)
    return [i for i, score in enumerate(scores) if abs(score) > MIN_ROBUST_Z]


def detect_anomalies_for_customer(db: Session, customer_id: str) -> list[dict]:
    """
    Run detection for one customer and return plain dicts (not persisted).

    The lookback runs back from this customer's own newest reading rather than
    from today. Meter data lags reality by weeks here, so a wall-clock window
    fell past the end of the readings and detection had nothing to look at.

    THE DAY COUNT IS OF REAL READINGS, NOT OF RESAMPLED BUCKETS
    ----------------------------------------------------------
    `_daily_frame` resamples to one row per day, which fills every day without
    a reading with a zero. Against a meter read once a month that turns three
    readings into sixty-six rows, sixty-three of them invented, and the
    `MIN_DAYS_REQUIRED` guard below passed on all sixty-six.

    What came out was not a near miss. A single monthly reading sitting beside
    twenty-one days of zeros gives a local baseline of about nothing, so the
    deviation is measured against nothing: the anomaly report showed +14,340%,
    +29,970%, +99,180%, and marked 403 of 869 findings critical, effectively
    every customer, on one date, all of them "abnormal spikes". A page full of
    confident nonsense is worse than an empty one, because somebody acts on it.

    So the guard now counts the days that actually carry a reading. A daily or
    hourly feed passes exactly as before; a monthly one does not reach the
    detector at all, which is the honest answer, a detector built to compare
    one day with the days around it has nothing to compare when there is one
    reading a month. What CAN be found in monthly readings is found by
    app/analytics/rules.py, stuck meters, sustained drops, consumption while
    disconnected, and that engine is measured, at 89.5% precision, and has its
    own page.
    """
    since = asof.customer_anchor(db, customer_id) - timedelta(days=LOOKBACK_DAYS)
    daily = _daily_frame(db, customer_id, since)

    if daily.empty:
        return []
    days_with_a_reading = int((daily["kwh"] > 0).sum())
    if days_with_a_reading < MIN_DAYS_REQUIRED:
        return []

    flagged = _detect_with_isolation_forest(daily) or _detect_with_zscore(daily)
    if not flagged:
        return []

    local = _local_baseline(daily)
    z_scores = _robust_z(daily)
    findings: list[dict] = []

    # Report only deviations large enough to act on, most extreme first. A
    # silent meter is always reported however small the customer, since zero
    # readings mean the meter stopped rather than that usage fell.
    ranked = sorted(flagged, key=lambda i: abs(float(z_scores[i])), reverse=True)

    for idx in ranked:
        row = daily.iloc[idx]
        value = float(row["kwh"])
        reference = float(local[idx]) or 1.0
        pct = ((value - reference) / reference) * 100
        is_flat = value <= 0.01

        # IsolationForest is configured to call 6% of days outliers, so on its
        # own it returns candidates for every customer whether or not anything
        # happened. Both gates have to hold: a big enough change, and one that
        # is genuinely unusual for this customer.
        if not is_flat and (
            abs(pct) < MIN_DEVIATION_PCT or abs(float(z_scores[idx])) < MIN_ROBUST_Z
        ):
            continue
        if len(findings) >= 3:
            break

        anomaly_type, description = _classify(pct, is_flat)
        findings.append(
            {
                "customer_id": customer_id,
                "type": anomaly_type,
                "severity": "medium" if is_flat else _severity_from_deviation(pct),
                "value": "Offline" if is_flat else f"{pct:+.0f}%",
                "score": round(pct, 2),
                "description": description,
                "detected_at": pd.Timestamp(row["date"]).to_pydatetime(),
            }
        )

    return findings


# ---------------------------------------------------------------------------
# The detector this data can actually support
# ---------------------------------------------------------------------------
# The detector above compares one day with the days around it, and this
# provider's meters are photographed once a month. Every account has three or
# four reading-days in the ninety-day window and the guard needs fourteen, so
# it returns nothing for all three hundred, every time. The page said so
# honestly, and an honest empty page is still an empty page: the module is one
# of five the platform claims, and "Run detection" produced nothing at all.
#
# There IS a detector that fits monthly readings, and it is already in the
# repository and already measured. app/ai/subscriber_anomaly.py fits an
# IsolationForest to twelve features built from readings and contracts, which
# is the model reported at 60.5% precision and 50.0% recall against the rules
# engine's 89.5% and 73.9%. It writes nothing anywhere; it only fed the
# comparison. It can fill this page.
#
# It is used as a FALLBACK, decided by the data rather than by the outcome. A
# database with daily readings keeps the day-level detector, which is the
# better instrument when the data supports it. Only where the readings cannot
# support it does the monthly model run, and the page says which one produced
# what it is showing, together with the fact that the rules beat this model on
# the labelled sample. A screen that offers a model's shortlist without saying
# the simpler method scored higher is selling it.
MONTHLY_TYPE = "Unusual Monthly Profile"

# How many accounts the monthly model may flag. The rules engine flags 38 of
# 300 on this data; matching that order is what keeps the two comparable and
# keeps the list to a number of doors somebody could actually knock on.
MONTHLY_BUDGET_SHARE = 0.125


def daily_readings_available(db: Session) -> bool:
    """
    Whether ANY account has enough reading-days for the day-level detector.

    One query rather than three hundred, and PER CUSTOMER rather than over the
    whole table. Counting distinct dates across every account together is the
    wrong question and answers yes on this data: three hundred subscribers read
    on staggered days fill the calendar between them while each one of them has
    three or four. What matters is the best-covered single account, because if
    that one cannot reach the threshold none of the others can.
    """
    anchor = asof.anchor(db).moment
    since = anchor - timedelta(days=LOOKBACK_DAYS)
    per_customer = (
        db.query(func.count(func.distinct(func.date(Consumption.timestamp))).label("days"))
        .filter(Consumption.timestamp >= since, Consumption.timestamp <= anchor)
        .group_by(Consumption.customer_id)
        .subquery()
    )
    best = db.query(func.max(per_customer.c.days)).scalar()
    return int(best or 0) >= MIN_DAYS_REQUIRED


def _monthly_severity(rank: int, flagged: int) -> str:
    """
    Where in the shortlist this case sits, and nothing stronger than that.

    Deliberately tops out at "high". This model was beaten by the rules on the
    labelled sample, so a "critical" from it would be claiming a confidence the
    measurement does not support.
    """
    if flagged <= 0:
        return "low"
    position = rank / flagged
    if position <= 0.25:
        return "high"
    if position <= 0.6:
        return "medium"
    return "low"


def monthly_findings(db: Session) -> list[dict]:
    """One finding per subscriber the monthly model flags, with its reasons."""
    from app.ai import subscriber_anomaly

    owner = {
        subscriber_id: customer_id
        for subscriber_id, customer_id in db.query(
            Subscriber.subscriber_id, Subscriber.customer_id
        ).all()
        if customer_id
    }
    if not owner:
        return []

    budget = max(1, int(len(owner) * MONTHLY_BUDGET_SHARE))
    scored = subscriber_anomaly.detect(db, budget=budget)
    if scored.empty or "flagged" not in scored:
        return []

    flagged = scored[scored["flagged"]]
    detected_at = datetime.combine(asof.anchor(db).as_of, time.min)

    findings: list[dict] = []
    for rank, (_, row) in enumerate(flagged.iterrows(), start=1):
        customer_id = owner.get(row["subscriber_id"])
        if not customer_id:
            continue
        findings.append(
            {
                "customer_id": customer_id,
                "type": MONTHLY_TYPE,
                "severity": _monthly_severity(rank, len(flagged)),
                # The rank, not the score. An IsolationForest score is a
                # number nobody can check; "3rd of 37" says exactly what it is.
                "value": f"{rank} of {len(flagged)}",
                "score": round(float(row["anomaly_score"]), 4),
                "description": subscriber_anomaly.explain(row, scored),
                "detected_at": detected_at,
            }
        )
    return findings


def run_detection(db: Session, persist: bool = True) -> list[Anomaly]:
    """
    Scan every active customer and persist the findings.

    Called by the pipeline after a data load and available on demand from
    POST /ai/anomalies/run.

    IDEMPOTENT, WHICH IT WAS NOT
    ----------------------------
    It used to `db.add` every finding on every run without checking what was
    already stored, so running the pipeline twice over the same readings
    doubled the anomaly count, 869 became 1,738, and a third run would have
    made it 2,607. Nothing errors, and the Anomalies page simply shows every
    finding twice, which reads as the detector firing repeatedly on the same
    customer rather than as the pipeline having been run again.

    A finding is identified by the customer, the day and the type: the same
    detector over the same readings must produce the same row, not another
    one. An existing row is refreshed in place, so a human's `resolved` flag
    survives a re-run, the alert engine already worked this way, and the two
    should not disagree about what a re-run means.
    """
    existing = {
        (row.customer_id, row.detected_at, row.type): row
        for row in db.query(Anomaly).all()
    }

    # Which detector this data can support. See `daily_readings_available`.
    if daily_readings_available(db):
        customers = db.query(Customer).filter(Customer.status != "Inactive").all()
        produced = [
            finding
            for customer in customers
            for finding in detect_anomalies_for_customer(db, customer.customer_id)
        ]
    else:
        produced = monthly_findings(db)

    created: list[Anomaly] = []
    for finding in produced:
        key = (finding["customer_id"], finding["detected_at"], finding["type"])
        match = existing.get(key)
        if match is not None:
            # Same finding, possibly restated: refresh the wording and
            # severity, leave `resolved` alone.
            for field, value in finding.items():
                if field != "resolved":
                    setattr(match, field, value)
            continue
        anomaly = Anomaly(**finding)
        created.append(anomaly)
        if persist:
            db.add(anomaly)
            existing[key] = anomaly

    if persist:
        db.commit()

    return created
