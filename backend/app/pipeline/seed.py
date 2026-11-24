"""
Development seeder, generates a realistic dataset so the platform is fully
demoable before the supervisor's real data arrives.

The generated consumption is not random noise: it layers the structure real
electricity demand actually has, which is what makes the AI models produce
meaningful output rather than fitting to noise.

    seasonal curve   summer cooling peak, mild spring/autumn
    weekly cycle     weekends higher for residential, lower for commercial
    daily profile    morning peak ~7am, evening peak ~7-9pm, overnight trough
    customer scale   per-customer baseline (residential vs commercial)
    injected faults  a handful of deliberate anomalies for the detector to find

Run:
    python -m app.pipeline.seed          # seed if empty
    python -m app.pipeline.seed --reset  # wipe and reseed
"""

from __future__ import annotations

import argparse
import logging
import math
import random
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal, create_all_tables, engine
from app.models.bill import Bill
from app.models.chat import ChatConversation, ChatMessage
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment
from app.pipeline.plans import normalise_plan

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("seed")

random.seed(42)

TARIFF = settings.TARIFF_LBP_PER_KWH   # LBP/kWh, see config.py for the basis
HOURLY_DAYS = 100          # recent window stored at hourly resolution
DAILY_DAYS = 640           # older history stored as one row per day

# --- Demo accounts ---------------------------------------------------------
# Localised to Lebanon: NXTTRN is a Lebanese company and the platform serves a
# private Lebanese electricity provider, so regions are the country's official
# governorates (muhafazat) rather than the US regions the early mock data used.
#
# Note on the documentation: neither the SRS nor the Software Architecture
# specifies any region list: the SRS Customers table (Section VII-i) does not
# even include a region field. Regions are required by the Proposal, which
# states management "lacks a consolidated view of business performance across
# regions or customer segments". See REGIONS below.
ADMIN = {
    "customer_id": "ADMIN-001",
    "name": "Rami Khoury",
    "email": "admin@nxttrn.com",
    "password": "admin123",
    "role": "admin",
    "region": "Beirut",
}

# The eight official Lebanese governorates. Customers are weighted towards
# Beirut and Mount Lebanon, which is where demand actually concentrates.
REGIONS = [
    "Beirut",
    "Mount Lebanon",
    "North Lebanon",
    "South Lebanon",
    "Beqaa",
    "Nabatieh",
    "Akkar",
    "Baalbek-Hermel",
]

CUSTOMERS = [
    # customer_id, name, email, region, plan, status, scale, phone, address
    ("CUST-0001", "Lara Awad",       "customer@nxttrn.com",        "Beirut",         "Residential", "Active",    1.00, "+961 3 214 887",  "Hamra Street, Bldg 12, Beirut"),
    ("CUST-0002", "Ziad El Halabi",  "ziad.halabi@example.com",    "Mount Lebanon",  "Residential", "Active",    1.15, "+961 70 331 204", "Rue Mar Elias, Antelias, Mount Lebanon"),
    ("CUST-0003", "Nour Haddad",     "nour.haddad@example.com",    "Beirut",         "Commercial",  "Active",    3.40, "+961 1 748 512",  "Verdun 732 Center, Beirut"),
    ("CUST-0004", "Karim Mansour",   "karim.mansour@example.com",  "South Lebanon",  "Residential", "Suspended", 0.76, "+961 71 905 663", "Riad El Solh Street, Saida"),
    ("CUST-0005", "Maya Saliba",     "maya.saliba@example.com",    "Mount Lebanon",  "Commercial",  "Active",    4.10, "+961 9 636 118",  "Fouad Chehab Ave, Jounieh"),
    ("CUST-0006", "Hadi Chamoun",    "hadi.chamoun@example.com",   "Nabatieh",       "Residential", "Active",    0.70, "+961 76 442 019", "Main Road, Nabatieh El Faouqa"),
    ("CUST-0007", "Rana Fakhoury",   "rana.fakhoury@example.com",  "North Lebanon",  "Residential", "Active",    1.33, "+961 6 431 770",  "Azmi Street, Tripoli"),
    ("CUST-0008", "Elie Gerges",     "elie.gerges@example.com",    "Beqaa",          "Commercial",  "Active",    2.98, "+961 8 802 345",  "Boulevard Zahle, Zahle"),
    ("CUST-0009", "Dana Sleiman",    "dana.sleiman@example.com",   "Akkar",          "Residential", "Inactive",  0.00, "+961 78 117 260", "Halba Main Street, Akkar"),
    ("CUST-0010", "Omar Baydoun",    "omar.baydoun@example.com",   "Beirut",         "Residential", "Active",    0.85, "+961 3 556 902",  "Mazraa, Bldg Najjar, Beirut"),
    ("CUST-0011", "Yara Nassar",     "yara.nassar@example.com",    "Mount Lebanon",  "Commercial",  "Active",    3.66, "+961 5 455 831",  "Old Saida Road, Baabda"),
    ("CUST-0012", "Jad Abou Khalil", "jad.aboukhalil@example.com", "Baalbek-Hermel", "Residential", "Active",    0.98, "+961 79 220 471", "Ras El Ain Street, Baalbek"),
    # Industrial accounts. The admin form has always offered this plan; until
    # now nothing in the data exercised it, so a bug that modelled a factory as
    # a household went unnoticed.
    ("CUST-0013", "Sidon Steel Works",  "ops@sidonsteel.example.com", "South Lebanon", "Industrial", "Active", 11.50, "+961 7 733 019", "Industrial Zone, Sidon"),
    ("CUST-0014", "Bekaa Food Plant",   "plant@bekaafoods.example.com", "Beqaa",       "Industrial", "Active",  8.20, "+961 8 811 476", "Terbol Industrial Road, Zahle"),
]

# Accounts the provider holds but nobody has registered for yet: exactly what
# the pipeline produces from a real dataset. They exist with consumption and
# billing history but no password, so they cannot be signed into until a
# customer registers with the Customer ID and a one-time registration code.
#
# These make the registration flow demonstrable: issue a code for one of them
# (the key button on the Customers page, or scripts/issue_registration_codes.py),
# register with its Customer ID and that code, and the account's existing
# readings appear immediately.
UNCLAIMED = [
    # customer_id, name, region, plan, scale
    ("MTR-40118", "Georges Rizk",   "Beirut",        "Residential", 1.08),
    ("MTR-40219", "Sarah Mroueh",   "Mount Lebanon", "Residential", 0.92),
    ("MTR-40327", "Tarek Zeineddine", "North Lebanon", "Commercial",  2.75),
]

# Payment channels a Lebanese provider actually uses. OMT and Whish Money are
# the dominant cash-transfer networks; card penetration is comparatively low.
PAYMENT_METHODS = [
    "OMT Transfer",
    "Whish Money",
    "Bank Transfer",
    "Cash at Office",
    "Visa •••• 4242",
]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ---------------------------------------------------------------------------
# Consumption generator
#
# Each customer gets their OWN load profile, not a scaled copy of one shared
# curve. Scaling a single shape means every customer's chart is identical in
# form and only differs by a multiplier: which reads as "everyone has the
# same data" and gives the AI models nothing real to distinguish.
#
# The parameters below vary the things that actually differ between real
# households and businesses: which season they peak in (cooling vs heating),
# how pronounced that seasonality is, when their daily peak falls, how much
# baseload they draw overnight, weekend behaviour, and how volatile they are.
# ---------------------------------------------------------------------------
# Industrial used to fall through to the residential branch, so a factory was
# modelled with a family's evening cooking peak and a weekend rise. What
# actually distinguishes the three plans is the shape of the day: a home peaks
# in the evening, a shop tracks opening hours, and a plant runs a near-flat load
# around the clock on a shift pattern rather than a weather-driven one.


def make_profile(seed_key: str, plan: str) -> dict:
    """
    Build a deterministic per-customer load profile.

    Keyed off the customer id, so the same customer always regenerates the
    same shape while different customers look genuinely different.
    """
    rng = random.Random(f"profile-{seed_key}")
    plan = normalise_plan(plan)
    is_commercial = plan == "Commercial"
    is_industrial = plan == "Industrial"

    if is_industrial:
        # A plant's consumption follows production, not the weather, so the
        # seasonal swing is small and the overnight baseload is very high.
        season_amp = rng.uniform(0.04, 0.14)
        night_load = rng.uniform(0.72, 0.92)
        weekend = rng.uniform(0.60, 0.85)     # reduced shift, not a shutdown
        volatility = rng.uniform(0.03, 0.10)  # process load is steady
    elif is_commercial:
        season_amp = rng.uniform(0.12, 0.40)
        night_load = rng.uniform(0.18, 0.45)
        weekend = rng.uniform(0.42, 0.78)
        volatility = rng.uniform(0.05, 0.20)
    else:
        season_amp = rng.uniform(0.12, 0.55)
        night_load = rng.uniform(0.18, 0.58)
        weekend = rng.uniform(0.95, 1.40)     # people are home at weekends
        volatility = rng.uniform(0.05, 0.24)

    return {
        "plan": plan,
        # Cooling-dominated (summer peak) or heating-dominated (winter peak).
        "heating_dominant": rng.random() < 0.30,
        # Shifts the seasonal peak by up to ~6 weeks either way.
        "season_phase": rng.uniform(-45, 45),
        # How strong the seasonal swing is: some homes barely vary.
        "season_amp": season_amp,
        "morning_peak": rng.uniform(0.75, 1.65),
        "evening_peak": rng.uniform(1.05, 2.05),
        # Hour the evening peak lands on: shift workers differ from families.
        "peak_hour": rng.choice([17, 18, 19, 20, 21]),
        # Overnight baseload as a fraction of the daytime average.
        "night_load": night_load,
        "midday": rng.uniform(0.55, 1.15),
        "weekend": weekend,
        "volatility": volatility,
        "is_commercial": is_commercial,
        "is_industrial": is_industrial,
        # Hour the day shift starts: industrial sites vary.
        "shift_start": rng.choice([5, 6, 7]),
    }


def _seasonal_factor(day_of_year: int, profile: dict | None = None) -> float:
    """
    Seasonal multiplier. Cooling-driven customers peak in mid-summer;
    heating-driven ones peak in mid-winter (half a year out of phase).
    """
    if profile is None:
        return 1.0 + 0.42 * math.sin((day_of_year - 105) / 365.0 * 2 * math.pi)

    offset = 105 + profile["season_phase"]
    if profile["heating_dominant"]:
        offset += 182.5  # push the peak to the opposite side of the year
    return 1.0 + profile["season_amp"] * math.sin((day_of_year - offset) / 365.0 * 2 * math.pi)


def _weekday_factor(weekday: int, is_commercial: bool, profile: dict | None = None) -> float:
    if profile is not None:
        return profile["weekend"] if weekday >= 5 else 1.0
    if is_commercial:
        return 0.55 if weekday >= 5 else 1.0
    return 1.18 if weekday >= 5 else 1.0


def _hourly_factor(hour: int, is_commercial: bool, profile: dict | None = None) -> float:
    """Load shape across the day, normalised around 1.0."""
    if profile is None:
        if is_commercial:
            if 8 <= hour <= 18:
                return 1.55
            if hour in (7, 19, 20):
                return 0.95
            return 0.32
        if 1 <= hour <= 5:
            return 0.34
        if 6 <= hour <= 8:
            return 1.22
        if 9 <= hour <= 16:
            return 0.72
        if 17 <= hour <= 22:
            return 1.62
        return 0.55

    if profile.get("is_industrial"):
        # Continuous process: a modest day-shift lift over a heavy baseload,
        # and no evening peak at all: nobody cooks dinner at a factory.
        shift = profile["shift_start"]
        if shift <= hour < shift + 8:
            return 1.15 + profile["midday"] * 0.20
        if shift + 8 <= hour < shift + 16:
            return 1.02 + profile["midday"] * 0.10
        return profile["night_load"]

    if profile["is_commercial"]:
        if 8 <= hour <= 18:
            return 1.35 + profile["midday"] * 0.35
        if hour in (7, 19, 20):
            return 0.95
        return profile["night_load"] * 0.9

    if 1 <= hour <= 5:
        return profile["night_load"]
    if 6 <= hour <= 8:
        return profile["morning_peak"]
    if 9 <= hour <= 16:
        return profile["midday"]

    # Evening peak centred on this customer's own peak hour, tapering either side.
    peak = profile["peak_hour"]
    if peak - 2 <= hour <= peak + 2:
        distance = abs(hour - peak)
        return profile["evening_peak"] * (1.0 - 0.16 * distance)
    if 17 <= hour <= 22:
        return profile["midday"] * 1.1
    return profile["night_load"] * 1.5


def generate_consumption(db: Session, customers: list[Customer], scales: dict[str, float]) -> int:
    """Build the meter-reading history for every customer."""
    now = datetime.now(UTC).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    hourly_start = now - timedelta(days=HOURLY_DAYS)
    daily_start = hourly_start - timedelta(days=DAILY_DAYS)

    records: list[dict] = []

    for customer in customers:
        scale = scales.get(customer.customer_id, 1.0)
        if scale <= 0:                       # inactive account, no readings
            continue

        is_commercial = customer.plan == "Commercial"
        base_daily_kwh = 16.0 * scale        # ≈480 kWh/month at scale 1.0
        profile = make_profile(customer.customer_id, customer.plan)
        vol = profile["volatility"]

        # --- Older history: one aggregated row per day --------------------
        day = daily_start
        while day < hourly_start:
            factor = (
                _seasonal_factor(day.timetuple().tm_yday, profile)
                * _weekday_factor(day.weekday(), is_commercial, profile)
                * random.uniform(1 - vol, 1 + vol)
            )
            kwh = round(base_daily_kwh * factor, 2)
            records.append(
                {
                    "customer_id": customer.customer_id,
                    "timestamp": day.replace(hour=12),
                    "kwh": kwh,
                    "cost": round(kwh * TARIFF, 2),
                }
            )
            day += timedelta(days=1)

        # --- Recent window: hourly resolution -----------------------------
        timestamp = hourly_start
        while timestamp < now:
            factor = (
                _seasonal_factor(timestamp.timetuple().tm_yday, profile)
                * _weekday_factor(timestamp.weekday(), is_commercial, profile)
                * _hourly_factor(timestamp.hour, is_commercial, profile)
                * random.uniform(1 - vol, 1 + vol)
            )
            kwh = round((base_daily_kwh / 24.0) * factor, 3)
            records.append(
                {
                    "customer_id": customer.customer_id,
                    "timestamp": timestamp,
                    "kwh": kwh,
                    "cost": round(kwh * TARIFF, 4),
                }
            )
            timestamp += timedelta(hours=1)

    _inject_anomalies(records, now)

    for start in range(0, len(records), 5000):
        db.bulk_insert_mappings(Consumption, records[start : start + 5000])
        db.commit()

    logger.info("Consumption readings generated: %d", len(records))
    return len(records)


def _inject_anomalies(records: list[dict], now: datetime) -> None:
    """
    Plant deliberate faults so the anomaly detector has real signal to find.

    Each corresponds to one of the categories the platform reports.
    """
    index: dict[str, list[dict]] = {}
    for record in records:
        index.setdefault(record["customer_id"], []).append(record)

    # 1) CUST-0007: night-time spike (faulty appliance running 2am-4am)
    for record in index.get("CUST-0007", []):
        delta_days = (now - record["timestamp"]).days
        if 6 <= delta_days <= 9 and 2 <= record["timestamp"].hour <= 4:
            record["kwh"] = round(record["kwh"] * 5.2, 3)
            record["cost"] = round(record["kwh"] * TARIFF, 4)

    # 2) CUST-0003: sustained drop (meter tampering signature)
    for record in index.get("CUST-0003", []):
        if 10 <= (now - record["timestamp"]).days <= 17:
            record["kwh"] = round(record["kwh"] * 0.28, 3)
            record["cost"] = round(record["kwh"] * TARIFF, 4)

    # 3) CUST-0005: sudden sustained spike (unreported load)
    for record in index.get("CUST-0005", []):
        if 3 <= (now - record["timestamp"]).days <= 6:
            record["kwh"] = round(record["kwh"] * 1.9, 3)
            record["cost"] = round(record["kwh"] * TARIFF, 4)

    # 4) CUST-0011: meter offline (no readings transmitted)
    for record in index.get("CUST-0011", []):
        if 2 <= (now - record["timestamp"]).days <= 4:
            record["kwh"] = 0.0
            record["cost"] = 0.0


# ---------------------------------------------------------------------------
# Bills, payments, alerts
# ---------------------------------------------------------------------------
# How each customer pays. The risk model in app/ai/risk.py scores payment
# behaviour, so the demo data has to contain some: a dataset where everybody
# pays a week early makes every customer score identically and leaves the
# early-warning feature with nothing to warn about.
#
#   prompt             settles 1-12 days before the due date
#   occasionally-late  usually early, late roughly a third of the time
#   late               consistently settles after the due date
#   delinquent         months of unpaid bills and no recent payment
PAYER_PROFILES = {
    "CUST-0004": "delinquent",         # Karim Mansour, suspended over arrears
    "CUST-0011": "late",               # Yara Nassar
    "CUST-0007": "occasionally-late",  # Rana Fakhoury
}
DEFAULT_PAYER_PROFILE = "prompt"

# Months of unpaid bills behind a delinquent account.
DELINQUENT_ARREARS_MONTHS = 4


def _payment_lag_days(profile: str) -> int:
    """Days after the due date a bill is settled. Negative means paid early."""
    if profile == "late":
        return random.randint(4, 25)
    if profile == "occasionally-late":
        return random.randint(6, 20) if random.random() < 0.35 else -random.randint(1, 8)
    if profile == "delinquent":
        # The bills this account did settle, it settled very late.
        return random.randint(15, 40)
    return -random.randint(1, 12)


def generate_bills_and_payments(db: Session, customers: list[Customer]) -> None:
    """Twelve months of billing history per customer, with realistic statuses."""
    from sqlalchemy import func

    today = datetime.now(UTC).date()
    payment_counter = 7800

    for customer in customers:
        if customer.status == "Inactive":
            continue

        profile = PAYER_PROFILES.get(customer.customer_id, DEFAULT_PAYER_PROFILE)

        for months_ago in range(11, -1, -1):
            period = (today.replace(day=1) - timedelta(days=months_ago * 30)).replace(day=1)

            total_kwh = float(
                db.query(func.coalesce(func.sum(Consumption.kwh), 0.0))
                .filter(
                    Consumption.customer_id == customer.customer_id,
                    Consumption.timestamp >= datetime.combine(period, datetime.min.time()),
                    Consumption.timestamp
                    < datetime.combine(period, datetime.min.time()) + timedelta(days=31),
                )
                .scalar()
                or 0.0
            )
            if total_kwh <= 0:
                continue

            amount = round(total_kwh * TARIFF, 2)
            due_date = period + timedelta(days=45)
            bill_id = f"BILL-{period.year}-{period.month:02d}-{customer.customer_id[-4:]}"

            # The current month is always still open. Beyond that, status
            # follows how this customer pays.
            if months_ago == 0:
                status = "Pending"
            elif profile == "delinquent" and months_ago <= DELINQUENT_ARREARS_MONTHS:
                status = "Overdue"
            elif months_ago == 1 and profile == "late":
                status = "Overdue"
            else:
                status = "Paid"

            db.add(
                Bill(
                    bill_id=bill_id,
                    customer_id=customer.customer_id,
                    month=f"{MONTH_NAMES[period.month - 1]} {period.year}",
                    amount=amount,
                    due_date=due_date,
                    status=status,
                )
            )

            if status == "Paid":
                payment_counter += 1
                # Never dated in the future: a settled bill has to have been
                # settled by now, whatever the profile says about lateness.
                paid_on = min(due_date + timedelta(days=_payment_lag_days(profile)), today)
                db.add(
                    Payment(
                        payment_id=f"PAY-{payment_counter}",
                        customer_id=customer.customer_id,
                        bill_id=bill_id,
                        date=paid_on,
                        amount=amount,
                        method=random.choice(PAYMENT_METHODS),
                        status="Completed",
                    )
                )

    db.commit()
    logger.info("Bills and payments generated")


def generate_chat_history(db: Session) -> None:
    """A few prior conversations so the chat sidebar is not empty on first load."""
    demo = db.get(Customer, "CUST-0001")
    if demo is None:
        return

    now = datetime.now(UTC)
    seeds = [
        ("Why is my bill higher this month?", 0),
        ("Tips to reduce AC usage", 0),
        ("When are off-peak hours?", 1),
        ("Compare my last two months", 6),
    ]

    for title, days_ago in seeds:
        conversation = ChatConversation(
            customer_id=demo.customer_id,
            title=title,
            created_at=now - timedelta(days=days_ago),
        )
        db.add(conversation)
        db.flush()
        db.add(
            ChatMessage(
                conversation_id=conversation.conversation_id,
                role="user",
                content=title,
                created_at=now - timedelta(days=days_ago),
            )
        )

    db.commit()
    logger.info("Chat history generated")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def reset_database() -> None:
    """Drop and recreate every table."""
    from app.database import Base

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset")


def seed(db: Session) -> None:
    now = datetime.now(UTC)

    # --- Accounts -------------------------------------------------------
    # Stage 2: the administrator is staff, so the login lives in `users`.
    from app.models.user import User

    db.add(
        User(
            user_id=ADMIN["customer_id"],
            name=ADMIN["name"],
            email=ADMIN["email"],
            password_hash=hash_password(ADMIN["password"]),
            role="admin",
            region=ADMIN["region"],
            status="Active",
            phone="+961 1 360 940",
            address="NXTTRN, Charles Helou Ave, Beirut",
            created_at=now - timedelta(days=900),
        )
    )

    customers: list[Customer] = []
    scales: dict[str, float] = {}

    for i, (cid, name, email, region, plan, status, scale, phone, address) in enumerate(CUSTOMERS):
        customer = Customer(
            customer_id=cid,
            name=name,
            email=email,
            password_hash=hash_password("customer123"),
            role="customer",
            region=region,
            plan=plan,
            status=status,
            phone=phone,
            address=address,
            # Staggered signup dates so the growth chart and the tenure-based
            # "Loyal Customers" segment both have real variation.
            created_at=now - timedelta(days=random.randint(120, 1100)),
        )
        db.add(customer)
        customers.append(customer)
        scales[cid] = scale

    # Unclaimed provider records: no password, so no sign-in until claimed.
    for cid, name, region, plan, scale in UNCLAIMED:
        record = Customer(
            customer_id=cid,
            name=name,
            email=f"unclaimed.{cid.lower()}@nxttrn.com",
            password_hash="",          # <- unclaimed
            role="customer",
            region=region,
            plan=plan,
            status="Active",
            created_at=now - timedelta(days=random.randint(200, 900)),
        )
        db.add(record)
        customers.append(record)
        scales[cid] = scale

    db.commit()
    logger.info(
        "Accounts created: 1 admin + %d customers (%d of them unclaimed)",
        len(customers), len(UNCLAIMED),
    )

    # --- Data -----------------------------------------------------------
    generate_consumption(db, customers, scales)
    generate_bills_and_payments(db, customers)
    generate_chat_history(db)

    # --- Rollups + AI ---------------------------------------------------
    from app.ai import alerts as alert_engine
    from app.ai import anomaly, forecasting, recommender
    from app.pipeline.ingest import refresh_customer_rollups

    refresh_customer_rollups(db)

    logger.info("Running AI models...")
    forecasting.invalidate_cache()
    count = recommender.refresh_all(db)
    logger.info("Recommendations generated: %d", count)

    findings = anomaly.run_detection(db)
    logger.info("Anomalies detected: %d", len(findings))

    # After detection, so anomalies can be promoted into customer feeds.
    generated = alert_engine.refresh_all(db)
    logger.info("Alerts generated: %d", generated)

    # --- CRM (VoltIQ unified) --------------------------------------------
    # Subscribers, meters, readings, invoices and staff for the same people,
    # so the CRM and the field app have something to show.
    from app.pipeline.crm_seed import seed_crm

    seed_crm(db)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the platform with demo data.")
    parser.add_argument("--reset", action="store_true", help="Drop all tables first")
    parser.add_argument(
        "--allow-non-sqlite",
        action="store_true",
        help="Allow a database that is not SQLite. For a disposable test database only.",
    )
    args = parser.parse_args()

    # The seeder creates demo logins whose passwords are published in the README
    # and printed by the launchers. On a shared or deployed database that is an
    # open door, so anything other than a local SQLite file is refused, and
    # --reset is refused with it, before the database is touched at all.
    if not settings.is_sqlite and not args.allow_non_sqlite:
        logger.error(
            "Refusing to seed a database that is not SQLite: the seeder creates demo logins "
            "whose passwords are published. --allow-non-sqlite is for a disposable test "
            "database only."
        )
        return 2

    create_all_tables()

    if args.reset:
        reset_database()

    db = SessionLocal()
    try:
        if db.query(Customer).count() > 0 and not args.reset:
            logger.warning("Database already contains data, use --reset to wipe and reseed.")
            return 0

        seed(db)

        logger.info("")
        logger.info("=" * 62)
        logger.info(" Seeding complete. Demo credentials:")
        logger.info("   Admin     admin@nxttrn.com     / admin123")
        logger.info("   Customer  customer@nxttrn.com  / customer123")
        logger.info("")
        logger.info(" To demo registration, issue a registration code for one of")
        logger.info(" these accounts (they already have consumption history, but")
        logger.info(" no login yet), then register with its Customer ID and the code:")
        for cid, name, _region, _plan, _scale in UNCLAIMED:
            logger.info("   %s   %s", cid, name)
        logger.info(" Codes: the key button on the Customers page, or")
        logger.info("   python -m scripts.issue_registration_codes --out codes.csv <Customer ID>")
        logger.info("=" * 62)
        return 0
    except Exception as exc:
        logger.error("Seeding failed: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
