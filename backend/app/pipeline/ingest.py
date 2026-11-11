"""
Data Pipeline, "Data pipeline consolidating consumption, billing and payment
data" (Proposal deliverable).

THIS IS WHERE THE SUPERVISOR'S DATASET GOES.

Usage:
    python -m app.pipeline.ingest --consumption data/readings.csv
    python -m app.pipeline.ingest --consumption data/readings.csv \
                                  --customers data/customers.csv \
                                  --bills data/bills.csv \
                                  --payments data/payments.csv

The loader is column-name tolerant: it looks for several common spellings of
each field (see COLUMN_ALIASES) so most utility exports load without editing
the CSV. Anything it cannot map is reported rather than silently dropped.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, create_all_tables
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment
from app.pipeline.plans import normalise_plan

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("pipeline")

# USD/kWh applied when the dataset has no cost column.
DEFAULT_TARIFF = settings.TARIFF_LBP_PER_KWH

# Placeholder address for an account the provider holds but nobody has
# registered for. Registration replaces it with the customer's real email.
UNCLAIMED_EMAIL_PREFIX = "unclaimed."
UNCLAIMED_EMAIL_DOMAIN = "@nxttrn.com"

# Accepted spellings for each logical field, lower-cased and stripped.
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "customer_id": ("customer_id", "customerid", "customer", "cust_id", "id", "meter_id", "account"),
    "timestamp": ("timestamp", "datetime", "date_time", "date", "reading_time", "time", "period"),
    "kwh": ("kwh", "consumption", "energy", "usage", "value", "active_power", "load", "demand"),
    "cost": ("cost", "amount", "charge", "price", "bill_amount", "total"),
    "name": ("name", "customer_name", "full_name"),
    "email": ("email", "e-mail", "mail"),
    "region": ("region", "area", "zone", "city", "district"),
    "plan": ("plan", "tariff", "customer_type", "type", "category"),
    "status": ("status", "state", "account_status"),
    "bill_id": ("bill_id", "billid", "invoice_id", "invoice"),
    "due_date": ("due_date", "duedate", "due"),
    "month": ("month", "billing_month", "period"),
    "payment_id": ("payment_id", "paymentid", "transaction_id", "txn_id"),
    "method": ("method", "payment_method", "channel"),
}


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename dataset columns onto our canonical names."""
    lookup = {str(col).strip().lower().replace(" ", "_"): col for col in df.columns}
    rename: dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lookup and lookup[alias] not in rename:
                rename[lookup[alias]] = canonical
                break

    return df.rename(columns=rename)


def _read_any(path: Path) -> pd.DataFrame:
    """Read CSV or Excel based on the file extension."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_customers(db: Session, path: Path) -> int:
    df = _normalise_columns(_read_any(path))

    if "customer_id" not in df.columns:
        raise ValueError(f"{path.name}: no customer id column found. Looked for: "
                         f"{COLUMN_ALIASES['customer_id']}")

    created = 0
    for _, row in df.iterrows():
        customer_id = str(row["customer_id"]).strip()
        if not customer_id or customer_id.lower() == "nan":
            continue

        if db.get(Customer, customer_id):
            continue

        email = str(row.get("email")
                    or f"{UNCLAIMED_EMAIL_PREFIX}{customer_id.lower()}{UNCLAIMED_EMAIL_DOMAIN}").strip()
        db.add(
            Customer(
                customer_id=customer_id,
                name=str(row.get("name") or f"Customer {customer_id}").strip(),
                email=email,
                # No password: the account exists in the provider's records but
                # nobody has registered for online access yet. The customer
                # claims it via /auth/register using this Customer ID.
                password_hash="",
                role="customer",
                region=str(row.get("region") or "Unassigned").strip(),
                # Normalised, because the load-profile logic branches on
                # the plan and a dataset spelling it "commercial" or
                # "COMMERCIAL" would otherwise be modelled as a household.
                plan=normalise_plan(str(row.get("plan") or "Residential")),
                status=str(row.get("status") or "Active").strip(),
            )
        )
        created += 1

    db.commit()
    logger.info("Customers loaded: %d new", created)
    return created


def load_consumption(db: Session, path: Path, batch_size: int = 5000) -> int:
    """
    Load meter readings, the most important table in the platform.

    Requires at minimum a customer id, a timestamp and a kWh column.
    Missing customers are auto-created so a readings-only dataset still works.
    """
    df = _normalise_columns(_read_any(path))

    missing = [col for col in ("customer_id", "timestamp", "kwh") if col not in df.columns]
    if missing:
        raise ValueError(
            f"{path.name}: missing required column(s) {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["timestamp", "kwh", "customer_id"])
    dropped = before - len(df)
    if dropped:
        logger.warning("Dropped %d rows with invalid timestamp/kwh/customer", dropped)

    if "cost" in df.columns:
        df["cost"] = pd.to_numeric(df["cost"], errors="coerce").fillna(
            df["kwh"] * DEFAULT_TARIFF
        )
    else:
        df["cost"] = df["kwh"] * DEFAULT_TARIFF

    # Auto-create any customer referenced by the readings but not yet stored.
    known = {row[0] for row in db.query(Customer.customer_id).all()}
    for customer_id in df["customer_id"].astype(str).str.strip().unique():
        if customer_id not in known:
            db.add(
                Customer(
                    customer_id=customer_id,
                    name=f"Customer {customer_id}",
                    email=f"{UNCLAIMED_EMAIL_PREFIX}{customer_id.lower()}{UNCLAIMED_EMAIL_DOMAIN}",
                    password_hash="",   # unclaimed, see load_customers
                    role="customer",
                    region="Unassigned",
                )
            )
            known.add(customer_id)
    db.commit()

    records = [
        {
            "customer_id": str(row.customer_id).strip(),
            "timestamp": row.timestamp.to_pydatetime(),
            "kwh": float(row.kwh),
            "cost": float(row.cost),
        }
        for row in df.itertuples(index=False)
    ]

    for start in range(0, len(records), batch_size):
        db.bulk_insert_mappings(Consumption, records[start : start + batch_size])
        db.commit()

    logger.info("Consumption readings loaded: %d", len(records))
    refresh_customer_rollups(db)
    return len(records)


def load_bills(db: Session, path: Path) -> int:
    df = _normalise_columns(_read_any(path))
    created = 0

    for index, row in df.iterrows():
        customer_id = str(row.get("customer_id") or "").strip()
        if not customer_id or not db.get(Customer, customer_id):
            continue

        bill_id = str(row.get("bill_id") or f"BILL-{index + 1:06d}").strip()
        if db.get(Bill, bill_id):
            continue

        due = pd.to_datetime(row.get("due_date"), errors="coerce")
        amount = pd.to_numeric(row.get("cost"), errors="coerce")

        db.add(
            Bill(
                bill_id=bill_id,
                customer_id=customer_id,
                month=str(row.get("month") or (due.strftime("%b %Y") if pd.notna(due) else "")),
                amount=float(amount) if pd.notna(amount) else 0.0,
                due_date=due.date() if pd.notna(due) else pd.Timestamp.today().date(),
                status=str(row.get("status") or "Pending").strip(),
            )
        )
        created += 1

    db.commit()
    logger.info("Bills loaded: %d", created)
    return created


def load_payments(db: Session, path: Path) -> int:
    df = _normalise_columns(_read_any(path))
    created = 0

    for index, row in df.iterrows():
        customer_id = str(row.get("customer_id") or "").strip()
        if not customer_id or not db.get(Customer, customer_id):
            continue

        payment_id = str(row.get("payment_id") or f"PAY-{index + 1:06d}").strip()
        if db.get(Payment, payment_id):
            continue

        paid_on = pd.to_datetime(row.get("timestamp"), errors="coerce")
        amount = pd.to_numeric(row.get("cost"), errors="coerce")

        db.add(
            Payment(
                payment_id=payment_id,
                customer_id=customer_id,
                bill_id=str(row["bill_id"]).strip() if "bill_id" in df.columns
                and pd.notna(row.get("bill_id")) else None,
                date=paid_on.date() if pd.notna(paid_on) else pd.Timestamp.today().date(),
                amount=float(amount) if pd.notna(amount) else 0.0,
                method=str(row.get("method") or "Bank Transfer").strip(),
                status=str(row.get("status") or "Completed").strip(),
            )
        )
        created += 1

    db.commit()
    logger.info("Payments loaded: %d", created)
    return created


def refresh_customer_rollups(db: Session) -> None:
    """Recompute the denormalised consumption/balance columns on Customer."""
    from sqlalchemy import func

    usage = dict(
        db.query(Consumption.customer_id, func.sum(Consumption.kwh))
        .group_by(Consumption.customer_id)
        .all()
    )
    outstanding = dict(
        db.query(Bill.customer_id, func.sum(Bill.amount))
        .filter(Bill.status != "Paid")
        .group_by(Bill.customer_id)
        .all()
    )

    for customer in db.query(Customer).all():
        customer.consumption = round(float(usage.get(customer.customer_id) or 0.0), 1)
        customer.balance = round(float(outstanding.get(customer.customer_id) or 0.0), 2)

    db.commit()
    logger.info("Customer rollups refreshed")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _confirm_wipe(assume_yes: bool) -> bool:
    """
    Empty every table, after saying plainly what is about to be lost.

    Loading real data on top of the demo data leaves seventeen invented
    customers sitting in the same tables as the provider's real ones, which is
    worse than either alone: every figure on the admin dashboard becomes a
    mixture, and nobody looking at the screen can tell which rows are which.
    This is the way out of that, so it deletes rather than merges, and it says
    so before it does.
    """
    from app.database import Base, engine

    db = SessionLocal()
    try:
        counts = {
            "customers": db.query(Customer).count(),
            "readings": db.query(Consumption).count(),
            "bills": db.query(Bill).count(),
            "payments": db.query(Payment).count(),
        }
    except Exception:
        counts = {}          # nothing created yet; there is nothing to lose
    finally:
        db.close()

    if any(counts.values()):
        logger.warning("--fresh will DELETE everything already in the database:")
        for table, n in counts.items():
            logger.warning("    %-12s %d", table, n)
        logger.warning("    ...including every account anyone has registered.")

        if not assume_yes:
            try:
                answer = input('Type "delete" to continue, anything else to stop: ')
            except EOFError:
                logger.error("--fresh needs a confirmation. Re-run with --yes if that is intended.")
                return False
            if answer.strip().lower() != "delete":
                logger.info("Stopped. Nothing was changed.")
                return False

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database emptied")
    logger.warning(
        "There is now no administrator and no password on any row. "
        "After loading, run:  python -m scripts.create_admin --email you@nxttrn.com"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Load the supervisor's dataset into the platform database."
    )
    parser.add_argument("--customers", type=Path, help="CSV/Excel of customer records")
    parser.add_argument("--consumption", type=Path, help="CSV/Excel of meter readings")
    parser.add_argument("--bills", type=Path, help="CSV/Excel of bills")
    parser.add_argument("--payments", type=Path, help="CSV/Excel of payments")
    parser.add_argument(
        "--rebuild-ai",
        action="store_true",
        help="Re-run recommendations and anomaly detection after loading",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Empty the database first, so the real data does not land beside the demo data",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt for --fresh (for scripted setup)",
    )
    args = parser.parse_args()

    if not any([args.customers, args.consumption, args.bills, args.payments]):
        parser.print_help()
        return 1

    if args.fresh and not _confirm_wipe(args.yes):
        return 1

    create_all_tables()
    db = SessionLocal()

    try:
        if args.customers:
            load_customers(db, args.customers)
        if args.consumption:
            load_consumption(db, args.consumption)
        if args.bills:
            load_bills(db, args.bills)
        if args.payments:
            load_payments(db, args.payments)

        refresh_customer_rollups(db)

        if args.rebuild_ai:
            from app.ai import alerts as alert_engine
            from app.ai import anomaly, forecasting, recommender

            logger.info("Re-running AI models...")
            # The cached forecast was fitted on the old data.
            forecasting.invalidate_cache()
            recommender.refresh_all(db)
            # Detection first: the alert engine promotes fresh anomalies into
            # the customer's own feed, so it has to see them.
            anomaly.run_detection(db)
            alert_engine.refresh_all(db)
            logger.info("AI models refreshed")

        logger.info("Pipeline finished successfully")
        return 0
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
