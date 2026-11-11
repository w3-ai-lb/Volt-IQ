"""
AI Module, Customer Segmentation.

Model: KMeans (scikit-learn) over behavioural features, with StandardScaler
applied first (essential, the features have very different units).

Clusters are labelled by inspecting their centroids rather than by fixed
index, so the naming stays correct across re-runs.

Two behavioural segments are computed separately from the consumption
clusters because they answer a different question (payment risk and tenure),
matching the segments the platform reports.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.analytics import asof
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer

logger = logging.getLogger(__name__)

PALETTE = {
    "High Consumers": "#2563eb",
    "Average Consumers": "#10b981",
    "Low Consumers": "#06b6d4",
    "Late Payment": "#f59e0b",
    "Loyal Customers": "#8b5cf6",
}


def build_feature_frame(db: Session) -> pd.DataFrame:
    """
    One row per customer with the features used for clustering:
      avg_monthly_kwh · peak_kwh · overdue_bills · balance · tenure_days
    """
    customers = db.query(Customer).filter(Customer.role == "customer").all()
    if not customers:
        return pd.DataFrame()

    usage = dict(
        db.query(Consumption.customer_id, func.sum(Consumption.kwh))
        .group_by(Consumption.customer_id)
        .all()
    )
    peaks = dict(
        db.query(Consumption.customer_id, func.max(Consumption.kwh))
        .group_by(Consumption.customer_id)
        .all()
    )
    overdue = dict(
        db.query(Bill.customer_id, func.count(Bill.bill_id))
        .filter(Bill.status == "Overdue")
        .group_by(Bill.customer_id)
        .all()
    )

    # Average per month must be divided by the number of months the data
    # actually spans: hard-coding 12 would inflate every figure when the
    # dataset covers two years.
    span = db.query(
        func.min(Consumption.timestamp), func.max(Consumption.timestamp)
    ).first()
    months_covered = 1.0
    if span and span[0] and span[1]:
        months_covered = max(1.0, (span[1] - span[0]).days / 30.44)

    # Tenure is counted to the day the data reaches, not to the wall clock,
    # for the reason given in ai/risk.reference_date: a segment that moves
    # while the data stands still is a calendar, not a measurement. On an
    # export ending in June 2026 the "Loyal Customers" segment (two years)
    # was empty all through 2026 and then, on 2 January 2027, claimed all 300
    # subscribers at once, because every account carries the month of its own
    # first invoice and the clock had simply passed it. With live data the
    # anchor is today, so the segment behaves as it reads.
    now = datetime.combine(asof.anchor(db).as_of, datetime.min.time()).replace(tzinfo=UTC)
    records = []
    for customer in customers:
        created = customer.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        tenure_days = max(0, (now - created).days) if created else 0

        total_kwh = float(usage.get(customer.customer_id) or 0.0)
        records.append(
            {
                "customer_id": customer.customer_id,
                "avg_monthly_kwh": total_kwh / months_covered if total_kwh else 0.0,
                "peak_kwh": float(peaks.get(customer.customer_id) or 0.0),
                "overdue_bills": int(overdue.get(customer.customer_id) or 0),
                "balance": float(customer.balance or 0.0),
                "tenure_days": tenure_days,
            }
        )

    return pd.DataFrame(records)


def _label_clusters(frame: pd.DataFrame, labels: np.ndarray) -> dict[int, str]:
    """Rank clusters by mean consumption and name them accordingly."""
    frame = frame.copy()
    frame["cluster"] = labels
    means = frame.groupby("cluster")["avg_monthly_kwh"].mean().sort_values()

    ordered = list(means.index)
    names = ["Low Consumers", "Average Consumers", "High Consumers"]

    # Handle k < 3 gracefully.
    if len(ordered) == 1:
        return {ordered[0]: "Average Consumers"}
    if len(ordered) == 2:
        return {ordered[0]: "Low Consumers", ordered[1]: "High Consumers"}

    return {cluster: names[min(i, len(names) - 1)] for i, cluster in enumerate(ordered)}


def _threshold_segments(frame: pd.DataFrame) -> pd.Series:
    """Rule-based fallback when scikit-learn is unavailable."""
    def classify(kwh: float) -> str:
        if kwh > 800:
            return "High Consumers"
        if kwh >= 300:
            return "Average Consumers"
        return "Low Consumers"

    return frame["avg_monthly_kwh"].apply(classify)


def generate_segments(db: Session) -> list[dict]:
    """Return the payload for GET /ai/segments."""
    frame = build_feature_frame(db)
    if frame.empty:
        return []

    total = len(frame)
    features = ["avg_monthly_kwh", "peak_kwh", "balance"]

    assigned: pd.Series | None = None
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        if total >= 3:
            matrix = StandardScaler().fit_transform(frame[features].to_numpy(dtype=float))
            k = min(3, total)
            model = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = model.fit_predict(matrix)
            mapping = _label_clusters(frame, labels)
            assigned = pd.Series([mapping[label] for label in labels], index=frame.index)
    except ImportError:
        logger.info("scikit-learn unavailable, using threshold segmentation")
    except Exception as exc:  # pragma: no cover
        logger.warning("KMeans failed, using threshold segmentation: %s", exc)

    if assigned is None:
        assigned = _threshold_segments(frame)

    segments: list[dict] = []
    for name in ["High Consumers", "Average Consumers", "Low Consumers"]:
        members = frame.loc[assigned == name, "avg_monthly_kwh"]
        if members.empty:
            continue

        # Describe each segment by the range its members actually occupy.
        # A hard-coded band would contradict the clustering as soon as the
        # dataset changes: which is exactly what a supervisor's dataset does.
        low, high = float(members.min()), float(members.max())
        description = (
            f"{low:,.0f}-{high:,.0f} kWh/month"
            if high - low >= 1
            else f"~{low:,.0f} kWh/month"
        )

        segments.append(
            {
                "name": name,
                "count": int(len(members)),
                "percentage": round(len(members) / total * 100, 1),
                "color": PALETTE[name],
                "description": description,
            }
        )

    # --- Behavioural segments (computed independently of the clusters) -----
    late_count = int((frame["overdue_bills"] > 0).sum())
    if late_count:
        segments.append(
            {
                "name": "Late Payment",
                "count": late_count,
                "percentage": round(late_count / total * 100, 1),
                "color": PALETTE["Late Payment"],
                "description": "Has at least one overdue bill",
            }
        )

    loyal_count = int((frame["tenure_days"] >= 365 * 2).sum())
    if loyal_count:
        segments.append(
            {
                "name": "Loyal Customers",
                "count": loyal_count,
                "percentage": round(loyal_count / total * 100, 1),
                "color": PALETTE["Loyal Customers"],
                "description": "2+ years tenure",
            }
        )

    return segments
