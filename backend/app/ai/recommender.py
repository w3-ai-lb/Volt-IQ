"""
AI Module, Personalised Recommendation Engine.

Rules-based by design: every recommendation is traceable to a specific pattern
in the customer's own data, which makes the savings figures defensible in a
demo and avoids the cold-start problem a collaborative-filtering model would
have on a new platform.

Each rule inspects a real signal (peak-hour share, seasonal ratio, night-time
baseload, standby load) and computes savings from that customer's own tariff.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy.orm import Session

from app.analytics import asof
from app.config import settings
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.recommendation import Recommendation

ANALYSIS_DAYS = 90     # recent window, hourly behaviour (peak shift, standby)
SEASONAL_DAYS = 365    # full year, needed to compare summer against winter

# LBP/kWh fallback, used only when a customer has no cost history to divide.
DEFAULT_TARIFF = settings.TARIFF_LBP_PER_KWH


def _load_readings(db: Session, customer_id: str, days: int = ANALYSIS_DAYS) -> pd.DataFrame:
    # Measured back from this customer's newest reading, not from today. The
    # provider's meters are read by hand and the data lags by weeks, so a
    # wall-clock window fell past the end of the readings and returned nothing:
    # a customer with eighteen months of history received no recommendations at
    # all, and the page said so as though the account were new.
    since = asof.customer_anchor(db, customer_id) - timedelta(days=days)
    rows = (
        db.query(Consumption.timestamp, Consumption.kwh, Consumption.cost)
        .filter(Consumption.customer_id == customer_id, Consumption.timestamp >= since)
        .all()
    )
    if not rows:
        return pd.DataFrame(columns=["timestamp", "kwh", "cost", "hour", "month"])

    df = pd.DataFrame(rows, columns=["timestamp", "kwh", "cost"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"] = df["timestamp"].dt.hour
    df["month"] = df["timestamp"].dt.month
    return df


def _tariff(df: pd.DataFrame) -> float:
    total_kwh = float(df["kwh"].sum())
    total_cost = float(df["cost"].fillna(0).sum())
    if total_kwh > 0 and total_cost > 0:
        return total_cost / total_kwh
    return DEFAULT_TARIFF


def _monthly_kwh(db: Session, customer_id: str, df: pd.DataFrame) -> float:
    """
    The customer's average consumption per month over the recent window.

    Readings taken every day or every hour fill the 90-day window, so their sum
    is three months of consumption. A meter read by hand is different: each row
    is a whole month's consumption, stamped on the day the dial was
    photographed, and readings fall 24 to 40 days apart. A 90-day window holds
    three of them or four, depending on the day of the month, and dividing four
    readings by three overstated the month by up to 41%. On the supplied data
    that was 86 of 300 subscribers: their savings estimates were inflated by the
    same factor, and four of them were told to replace light bulbs because of a
    consumption level they did not have.

    For such a meter the month is the mean of the newest three readings, each of
    which the Consumption page shows as one month.
    """
    if df.empty:
        return 0.0
    months = max(1, round(ANALYSIS_DAYS / 30))
    if asof.has_daily(db, customer_id):
        return float(df["kwh"].sum()) / months
    return float(df.sort_values("timestamp").tail(months)["kwh"].mean())


def generate_recommendations(db: Session, customer_id: str) -> list[dict]:
    """Analyse a customer's usage and return recommendation dicts."""
    df = _load_readings(db, customer_id)
    if df.empty:
        return []

    tariff = _tariff(df)
    monthly_kwh = _monthly_kwh(db, customer_id, df)
    monthly_cost = monthly_kwh * tariff
    recommendations: list[dict] = []

    # --- Rule 1: evening peak share -------------------------------------
    has_hourly = df["hour"].nunique() > 1
    if has_hourly:
        peak_mask = df["hour"].between(18, 22)
        peak_share = float(df.loc[peak_mask, "kwh"].sum()) / max(float(df["kwh"].sum()), 1e-9)
        if peak_share > 0.28:
            shiftable = monthly_cost * peak_share * 0.35
            recommendations.append(
                {
                    "title": "Shift laundry and dishwashing to off-peak hours",
                    "description": (
                        f"{peak_share * 100:.0f}% of your electricity is used during the "
                        "6pm-10pm peak window. Running your washer, dryer and dishwasher "
                        # 10pm, not 8pm: the hours advised must lie outside the
                        # peak the sentence has just named.
                        "between 10pm and 6am can cut your monthly bill by up to 12%."
                    ),
                    "estimated_savings": round(shiftable, 2),
                    "priority": "High",
                    "icon": "WashingMachine",
                }
            )

    # --- Rule 2: night-time baseload (standby / phantom load) -----------
    if has_hourly:
        night_mask = df["hour"].between(1, 5)
        night_avg = float(df.loc[night_mask, "kwh"].mean() or 0)
        day_avg = float(df.loc[~night_mask, "kwh"].mean() or 1e-9)
        if day_avg > 0 and night_avg / day_avg > 0.45:
            standby_saving = monthly_cost * 0.08
            recommendations.append(
                {
                    "title": "Unplug idle electronics and chargers",
                    "description": (
                        "Your overnight baseload stays unusually high relative to daytime "
                        "usage, which points to standby draw. Phantom loads account for "
                        "roughly 8% of residential electricity use."
                    ),
                    "estimated_savings": round(standby_saving, 2),
                    "priority": "Medium",
                    "icon": "Unplug",
                }
            )

    # --- Rule 3: seasonal cooling load ----------------------------------
    # Uses a full year of history: a 90-day window can never contain both
    # summer and winter, so this comparison needs its own wider query.
    seasonal = _load_readings(db, customer_id, days=SEASONAL_DAYS)
    summer = seasonal[seasonal["month"].isin([6, 7, 8])]["kwh"].sum() if not seasonal.empty else 0
    winter = seasonal[seasonal["month"].isin([12, 1, 2])]["kwh"].sum() if not seasonal.empty else 0
    if winter > 0 and summer / winter > 1.4:
        hvac_saving = monthly_cost * 0.15
        recommendations.append(
            {
                "title": "Upgrade to a smart thermostat",
                "description": (
                    "Your summer consumption runs well above your winter baseline, so "
                    "cooling dominates your bill. A programmable thermostat optimises HVAC "
                    "cycles and typically reduces cooling costs by 10-15%."
                ),
                "estimated_savings": round(hvac_saving, 2),
                "priority": "High",
                "icon": "Thermostat",
            }
        )
        recommendations.append(
            {
                "title": "Schedule air-conditioning maintenance",
                "description": (
                    "A clean filter and tuned coils improve cooling efficiency by 5-15%. "
                    "Given your cooling-heavy profile this pays back within one season."
                ),
                "estimated_savings": round(monthly_cost * 0.06, 2),
                "priority": "Medium",
                "icon": "Wind",
            }
        )

    # --- Rule 4: overall high usage -------------------------------------
    if monthly_kwh > 600:
        recommendations.append(
            {
                "title": "Replace remaining incandescent bulbs with LEDs",
                "description": (
                    f"At {monthly_kwh:.0f} kWh/month your household is in the upper "
                    "consumption band. LEDs use up to 80% less energy than incandescent "
                    "lighting and last around 25 times longer."
                ),
                "estimated_savings": round(monthly_cost * 0.05, 2),
                "priority": "Medium",
                "icon": "Lightbulb",
            }
        )

    # --- Baseline advice so no customer sees an empty page ---------------
    if not recommendations:
        recommendations.append(
            {
                "title": "Enable monthly usage alerts",
                "description": (
                    "Your consumption is already well controlled. Turning on usage alerts "
                    "will notify you early if your pattern changes unexpectedly."
                ),
                "estimated_savings": round(monthly_cost * 0.03, 2),
                "priority": "Low",
                "icon": "BellRing",
            }
        )

    return recommendations


def refresh_for_customer(db: Session, customer_id: str) -> list[Recommendation]:
    """Regenerate recommendations, preserving any the customer already completed."""
    completed_titles = {
        row.title
        for row in db.query(Recommendation).filter(
            Recommendation.customer_id == customer_id,
            Recommendation.completed.is_(True),
        )
    }

    db.query(Recommendation).filter(
        Recommendation.customer_id == customer_id,
        Recommendation.completed.is_(False),
    ).delete(synchronize_session=False)

    created: list[Recommendation] = []
    for payload in generate_recommendations(db, customer_id):
        if payload["title"] in completed_titles:
            continue
        record = Recommendation(customer_id=customer_id, **payload)
        db.add(record)
        created.append(record)

    db.commit()
    return created


def refresh_all(db: Session) -> int:
    """Regenerate recommendations for every customer. Returns the row count."""
    total = 0
    for (customer_id,) in db.query(Customer.customer_id).filter(Customer.role == "customer"):
        total += len(refresh_for_customer(db, customer_id))
    return total
