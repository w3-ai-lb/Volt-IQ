"""
Account provisioning, gives a newly registered customer a meter history.

WHY THIS EXISTS
---------------
Registering on the web portal is not the same as becoming a new utility
customer: the person already has an electricity meter that has been recording
for months. Their online account is new, their consumption history is not.

Without this, every account created through the Register page lands on an
empty dashboard with flat charts, no bills and no AI output, which makes the
platform look broken during a demo even though it is working correctly.

Controlled by PROVISION_DEMO_DATA in .env. Set it to false once the real
metering feed (or the supervisor's dataset) is the source of truth, so that
new accounts only ever show genuine data.
"""

from __future__ import annotations

import logging
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment
from app.pipeline.seed import (
    MONTH_NAMES,
    PAYMENT_METHODS,
    TARIFF,
    _hourly_factor,
    _seasonal_factor,
    _weekday_factor,
    make_profile,
)

logger = logging.getLogger(__name__)

HISTORY_MONTHS = 12
HOURLY_DAYS = 30       # recent window at hourly resolution
BILLING_MONTHS = 6


def provision_customer(db: Session, customer: Customer, scale: float | None = None) -> int:
    """
    Generate consumption, bills and payments for one customer.

    Returns the number of consumption rows created. Safe to call on a customer
    that already has readings. It does nothing in that case.
    """
    existing = (
        db.query(Consumption.consumption_id)
        .filter(Consumption.customer_id == customer.customer_id)
        .first()
    )
    if existing:
        return 0

    # Vary the household size per customer, derived from the id so the same
    # account always regenerates the same profile.
    rng = random.Random(customer.customer_id)
    if scale is None:
        # Industrial sites draw an order of magnitude more than a household,
        # and a shop sits between the two.
        if customer.plan == "Industrial":
            scale = rng.uniform(7.0, 13.0)
        elif customer.plan == "Commercial":
            scale = rng.uniform(2.5, 4.0)
        else:
            scale = rng.uniform(0.75, 1.45)

    is_commercial = customer.plan == "Commercial"
    base_daily_kwh = 16.0 * scale
    # Same per-customer profile machinery the seeder uses, so a provisioned
    # account does not look like a clone of the demo customer.
    profile = make_profile(customer.customer_id, customer.plan)
    vol = profile["volatility"]

    now = datetime.now(UTC).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    hourly_start = now - timedelta(days=HOURLY_DAYS)
    daily_start = now - timedelta(days=HISTORY_MONTHS * 30)

    records: list[dict] = []

    # --- Older history: one aggregated row per day -------------------------
    day = daily_start
    while day < hourly_start:
        factor = (
            _seasonal_factor(day.timetuple().tm_yday, profile)
            * _weekday_factor(day.weekday(), is_commercial, profile)
            * rng.uniform(1 - vol, 1 + vol)
        )
        kwh = round(base_daily_kwh * factor, 2)
        records.append({
            "customer_id": customer.customer_id,
            "timestamp": day.replace(hour=12),
            "kwh": kwh,
            "cost": round(kwh * TARIFF, 2),
        })
        day += timedelta(days=1)

    # --- Recent window: hourly, so the load-profile chart has shape --------
    timestamp = hourly_start
    while timestamp < now:
        factor = (
            _seasonal_factor(timestamp.timetuple().tm_yday, profile)
            * _weekday_factor(timestamp.weekday(), is_commercial, profile)
            * _hourly_factor(timestamp.hour, is_commercial, profile)
            * rng.uniform(1 - vol, 1 + vol)
        )
        kwh = round((base_daily_kwh / 24.0) * factor, 3)
        records.append({
            "customer_id": customer.customer_id,
            "timestamp": timestamp,
            "kwh": kwh,
            "cost": round(kwh * TARIFF, 4),
        })
        timestamp += timedelta(hours=1)

    db.bulk_insert_mappings(Consumption, records)
    db.commit()

    _create_billing_history(db, customer, rng)
    _refresh_rollups(db, customer)

    logger.info("Provisioned %s with %d readings", customer.customer_id, len(records))
    return len(records)


def _create_billing_history(db: Session, customer: Customer, rng: random.Random) -> None:
    """Six months of bills, with the most recent one still outstanding."""
    from sqlalchemy import func

    today = datetime.now(UTC).date()
    suffix = customer.customer_id.replace("CUST-", "")[-4:]

    for months_ago in range(BILLING_MONTHS - 1, -1, -1):
        period = (today.replace(day=1) - timedelta(days=months_ago * 30)).replace(day=1)

        total_kwh = float(
            db.query(func.coalesce(func.sum(Consumption.kwh), 0.0))
            .filter(
                Consumption.customer_id == customer.customer_id,
                Consumption.timestamp >= datetime.combine(period, datetime.min.time()),
                Consumption.timestamp
                < datetime.combine(period, datetime.min.time()) + timedelta(days=31),
            )
            .scalar() or 0.0
        )
        if total_kwh <= 0:
            continue

        amount = round(total_kwh * TARIFF, 2)
        due_date = period + timedelta(days=45)
        bill_id = f"BILL-{period.year}-{period.month:02d}-{suffix}"
        if db.get(Bill, bill_id):
            continue

        status = "Pending" if months_ago == 0 else "Paid"
        db.add(Bill(
            bill_id=bill_id,
            customer_id=customer.customer_id,
            month=f"{MONTH_NAMES[period.month - 1]} {period.year}",
            amount=amount,
            due_date=due_date,
            status=status,
        ))

        if status == "Paid":
            db.add(Payment(
                payment_id=f"PAY-{suffix}-{period.year}{period.month:02d}",
                customer_id=customer.customer_id,
                bill_id=bill_id,
                date=due_date - timedelta(days=rng.randint(1, 12)),
                amount=amount,
                method=rng.choice(PAYMENT_METHODS),
                status="Completed",
            ))

    db.commit()


def _refresh_rollups(db: Session, customer: Customer) -> None:
    from sqlalchemy import func

    total = float(
        db.query(func.coalesce(func.sum(Consumption.kwh), 0.0))
        .filter(Consumption.customer_id == customer.customer_id).scalar() or 0.0
    )
    outstanding = float(
        db.query(func.coalesce(func.sum(Bill.amount), 0.0))
        .filter(Bill.customer_id == customer.customer_id, Bill.status != "Paid")
        .scalar() or 0.0
    )
    customer.consumption = round(total, 1)
    customer.balance = round(outstanding, 2)
    db.commit()
