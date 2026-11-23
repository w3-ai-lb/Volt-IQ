"""
Give the supervisor's 300 subscribers a CRM record each.

    python -m app.pipeline.identities
    python -m app.pipeline.identities --replace     # regenerate from scratch

WHY THIS EXISTS
---------------
From the supervisor, 18 August: the real customer records are postponed, the
team is dealing with maintenance faults and power problems that take priority.
In the meantime, generate data that reflects the real business context and is
as logical as possible, and **structure the subscriber and meter data to match
the shape used in the CRM project**.

His analytics export identifies subscribers as S00000, S00001 and so on, with
a zone and a type and nothing else. No name, no phone, no address. A customer
portal cannot show that, and the CRM half of the system has a record shape this
half is supposed to match.

WHERE THE NAMES COME FROM
-------------------------
Not from anything invented here. `data/crm/customer_side_seed_data.sql` is the
customer-side project's own seed, and it carries forty-five people with a name,
a phone, an address and a coordinate. Those forty-five are placed on his
subscribers first, each one onto a subscriber IN THE SAME ZONE, so a person who
appears in both halves of the system appears in one place in both. The other
255 are built from the same name pools, the same address format and the same
phone prefixes, so no record is distinguishable from the CRM's by its style.

See app/pipeline/crm_identities.py for what is read from that file and, more
importantly, what is deliberately not: its readings, invoices and payments
describe the same twelve zones over a different year than his export does.

WHAT IS GENERATED, AND WHAT IS NOT
----------------------------------
Only the identity. Name, email, phone, street, coordinate.

Everything measurable is MEASURED, from the data the supervisor supplied:

    consumption   the sum of that subscriber's own meter-reading differences
    balance       their own invoices, minus their own payments
    region        the real name of the zone their meter is in
    plan          their real subscriber_type
    status        their real subscription status
    created_at    the month of their own first invoice, not the moment this ran

That division is the point. A generated name is a placeholder for a name. A
generated consumption figure would be a lie sitting in the same row as real
ones, indistinguishable a month later, and it would end up in a chart.

DETERMINISTIC ON PURPOSE
------------------------
The name for S00042 is derived from the id itself, so running this twice gives
the same person and a screenshot taken today still matches the database next
week. Nothing here uses a random seed that could drift.

HOW TO TELL THESE APART FROM REAL DATA LATER
--------------------------------------------
Every record created here gets customer_id GEN-xxxxx and an @example.com email
address. `scripts/data_provenance.py` reports them as their own tier, keyed on
the customer_id, so the boundary between measured, supplied and generated is
always visible and nobody has to remember it.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import SessionLocal, create_all_tables
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoicePayment
from app.models.network import Zone
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription
from app.pipeline import crm_identities

logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
logger = logging.getLogger("identities")

# Marks a record as generated rather than supplied or measured.
GENERATED_PREFIX = "GEN-"

# WHY example.com AND NOT SOMETHING THAT LOOKS NICER
# --------------------------------------------------
# This was "@generated.local", and it made 298 of the 300 subscribers unable to
# sign in at all. `.local` is reserved by RFC 6762 for multicast DNS, so the
# email validator behind every EmailStr field in this project rejects it as a
# special-use domain, and the login endpoint answered 422 before it ever looked
# at the password. The customer portal was unreachable for every subscriber
# except the two whose address had been overwritten by registering.
#
# Nothing in the interface said so. The address looked like an address, the
# customer list printed it happily, and the failure only appeared at the one
# place nobody tests with generated data: signing in as one of them.
#
# example.com is reserved by RFC 2606 for exactly this purpose. It is a valid
# address, it can never receive mail, and it cannot be mistaken for a real one.
GENERATED_DOMAIN = "@example.com"


def repair_emails(db: Session) -> int:
    """
    Move any subscriber still on the old unusable domain onto this one.

    Kept because a database loaded before the domain changed would otherwise
    stay unusable until somebody reloaded it from scratch, and reloading throws
    away every password anyone has set.
    """
    stale = (
        db.query(Customer)
        .filter(Customer.email.like("%@generated.local"))
        .all()
    )
    for record in stale:
        record.email = record.email.replace("@generated.local", GENERATED_DOMAIN)
    if stale:
        db.commit()
    return len(stale)


def _digest(seed: str, salt: str = "") -> str:
    return hashlib.sha256(f"{salt}{seed}".encode()).hexdigest()


def _pick(seed: str, options, salt: str = ""):
    """
    Deterministic choice from a sequence.

    A hash of the subscriber id rather than a random draw, so S00042 is the
    same person on every run and a screenshot stays true to the database.
    """
    return options[int(_digest(seed, salt)[:8], 16) % len(options)]


def _phone(seed: str) -> str:
    """Eight digits behind a Lebanese mobile prefix, as the CRM file writes them."""
    digest = _digest(seed, "phone")
    prefix = crm_identities.PHONE_PREFIXES[int(digest[:2], 16) % len(crm_identities.PHONE_PREFIXES)]
    return f"{prefix}{int(digest[2:8], 16) % 1_000_000:06d}"


def _spread(seed: str, low: float, high: float, salt: str) -> float:
    """A point in a range, fixed by the id. Six decimals, as the source has."""
    fraction = int(_digest(seed, salt)[:8], 16) / 0xFFFFFFFF
    return round(low + (high - low) * fraction, 6)


def _generated_name(sid: str, seed: crm_identities.CrmSeed, reserved: set[str]) -> str:
    """
    A name from the CRM's own pools, never one of the CRM's own PEOPLE.

    Two subscribers of 300 sharing a name is ordinary and is left alone: towns
    contain several Ali Khalils. But the forty-five people the CRM names are
    each asserted to live in a particular zone, and drawing one of those names
    for a subscriber somewhere else would put one person in two places across
    the two halves of the system. Sixteen of the 255 did exactly that before
    this check existed. On a collision the draw is repeated with a bumped salt,
    which keeps it deterministic.
    """
    for attempt in range(32):
        suffix = "" if attempt == 0 else str(attempt)
        first = _pick(sid, seed.first_names, f"first{suffix}")
        family = _pick(sid, seed.family_names, f"family{suffix}")
        name = f"{first} {family}"
        if name not in reserved:
            return name
    # 28 x 22 combinations against 45 reserved names: unreachable in practice,
    # and if the pools ever shrink far enough to reach it, an obviously odd
    # name is better than a silent contradiction.
    return f"{first} {family} ({sid})"


def _as_datetime(day) -> datetime:
    """A billing month as a timestamp, or now if the subscriber has no invoice."""
    if day is None:
        return datetime.now(UTC)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _measured(db: Session) -> dict[str, dict]:
    """
    The figures that must NOT be invented, taken from the supplied data.

    CONSUMPTION
    -----------
    A meter reading is the number on the dial, so the energy used in a month
    is the difference between two readings. The first reading of each meter
    has no reading before it, but it does have one, on the meter record:
    `meters.initial_reading`, the dial when the meter was installed.

    That column is not decoration. Without it the first of each subscriber's
    eighteen months is silently dropped and every consumption figure in the
    system comes out about 7% low. With it, the reading differences reproduce
    the supervisor's own `invoices.units_consumed` exactly, on all 5,400 rows:
    1,528,617 kWh against 1,528,621, the gap being the one-decimal rounding
    in his export. That agreement is the check that this is being done right.

    BALANCE
    -------
    What is owed is everything invoiced minus everything paid. Counting only
    invoices with no payment row at all is wrong here: 845 of the 5,400
    invoices were paid in part, and treating a part-payment as settled put
    276 of the 300 subscribers at a balance of zero when only 8 owe nothing.
    """
    # --- consumption: reading differences, seeded from the installed dial ---
    initial = {
        subscription_id: float(value or 0.0)
        for subscription_id, value in db.query(Meter.subscription_id, Meter.initial_reading).all()
    }
    consumption: dict[str, float] = {}
    rows = (
        db.query(
            Subscription.subscriber_id,
            MeterReading.subscription_id,
            MeterReading.billing_period,
            MeterReading.reading_value,
        )
        .join(Subscription, Subscription.subscription_id == MeterReading.subscription_id)
        .order_by(MeterReading.subscription_id, MeterReading.billing_period)
        .all()
    )
    previous: dict[str, float] = dict(initial)
    for subscriber_id, subscription_id, _period, value in rows:
        if subscription_id in previous:
            used = float(value) - previous[subscription_id]
            if used > 0:                       # a rollover is not consumption
                consumption[subscriber_id] = consumption.get(subscriber_id, 0.0) + used
        previous[subscription_id] = float(value)

    # --- when the account starts: their own first billed month -------------
    # Not the moment this script ran. `created_at` drives the customer-growth
    # chart, and 300 accounts all created today would draw a cliff on the day
    # the pipeline was run rather than the history the data actually has.
    started = {
        subscriber_id: first
        for subscriber_id, first in db.query(
            Invoice.subscriber_id, func.min(Invoice.billing_period)
        )
        .group_by(Invoice.subscriber_id)
        .all()
    }

    # --- balance: invoiced minus paid, part-payments included --------------
    invoiced = dict(
        db.query(Invoice.subscriber_id, func.sum(Invoice.total_amount))
        .group_by(Invoice.subscriber_id)
        .all()
    )
    paid = dict(
        db.query(InvoicePayment.subscriber_id, func.sum(InvoicePayment.amount))
        .group_by(InvoicePayment.subscriber_id)
        .all()
    )
    balance: dict[str, float] = {}
    for subscriber_id, total in invoiced.items():
        # Clipped at zero: an overpayment is a credit, and this column is what
        # is owed. No row in this dataset is overpaid, so nothing is hidden.
        balance[subscriber_id] = max(
            0.0, float(total or 0.0) - float(paid.get(subscriber_id) or 0.0)
        )

    return {"consumption": consumption, "balance": balance, "started": started}


def _assign_crm_identities(
    subscribers: list[Subscriber], zone_names: dict[str, str], seed: crm_identities.CrmSeed
) -> dict[str, crm_identities.Identity]:
    """
    Place each person the CRM already holds onto a subscriber in the same zone.

    Same zone, because that is the one fact the two files agree on about these
    people. Putting Rabih Khalil of Harjali onto a subscriber in Yassine would
    make the two halves of the system disagree about where he lives, which is
    exactly the kind of small contradiction that costs an afternoon later.

    Sorted by subscriber id, so the assignment is the same on every run.
    """
    by_zone: dict[str, list[str]] = {}
    for subscriber in sorted(subscribers, key=lambda s: s.subscriber_id):
        zone = zone_names.get(subscriber.zone_id or "", "")
        by_zone.setdefault(zone, []).append(subscriber.subscriber_id)

    assigned: dict[str, crm_identities.Identity] = {}
    taken: dict[str, int] = {}
    for identity in seed.identities:
        candidates = by_zone.get(identity.zone_name, [])
        index = taken.get(identity.zone_name, 0)
        if index >= len(candidates):
            logger.warning(
                "No free subscriber left in %s for %s; generating instead",
                identity.zone_name or "an unknown zone",
                identity.name,
            )
            continue
        assigned[candidates[index]] = identity
        taken[identity.zone_name] = index + 1
    return assigned


def generate(db: Session, replace: bool = False) -> tuple[int, int]:
    """Returns (records created, of which taken verbatim from the CRM seed)."""
    subscribers = db.query(Subscriber).all()
    if not subscribers:
        logger.error("No subscribers loaded. Run: python -m app.pipeline.ishtirak")
        return 0, 0

    if replace:
        removed = (
            db.query(Customer)
            .filter(Customer.customer_id.like(f"{GENERATED_PREFIX}%"))
            .delete(synchronize_session=False)
        )
        db.query(Subscriber).update({Subscriber.customer_id: None}, synchronize_session=False)
        db.commit()
        logger.info("Removed %d previously generated records", removed)

    measured = _measured(db)
    zones = {z.zone_id: z for z in db.query(Zone).all()}
    zone_names = {zone_id: zone.name for zone_id, zone in zones.items()}
    statuses = {s.subscriber_id: s.status for s in db.query(Subscription).all()}

    seed = crm_identities.load()
    if seed.available:
        logger.info(
            "Read %d identities from the CRM seed (%d first names, %d family names)",
            len(seed.identities), len(seed.first_names), len(seed.family_names),
        )
    else:
        logger.warning(
            "CRM seed not found at %s; using the name pools recorded in the module",
            crm_identities.SEED_PATH,
        )
    from_crm = _assign_crm_identities(subscribers, zone_names, seed)
    # Names the CRM has already committed to a zone. Off limits to the draw.
    crm_names = {identity.name for identity in seed.identities}

    taken_emails = {e for (e,) in db.query(Customer.email).all()}
    created = 0
    verbatim = 0

    for subscriber in subscribers:
        if subscriber.customer_id:
            continue

        sid = subscriber.subscriber_id
        zone_name = zone_names.get(subscriber.zone_id or "", subscriber.zone_id or "Unknown")

        identity = from_crm.get(sid)
        if identity is not None:
            name = identity.name
            phone = identity.phone
            address = identity.address
            gps_lat, gps_lng = identity.gps_lat, identity.gps_lng
            verbatim += 1
        else:
            name = _generated_name(sid, seed, reserved=crm_names)
            phone = _phone(sid)
            building = 1 + int(_digest(sid, "building")[:4], 16) % 220
            address = crm_identities.ADDRESS_FORMAT.format(building=building, zone=zone_name)
            gps_lat = _spread(sid, *seed.lat_range, salt="lat")
            gps_lng = _spread(sid, *seed.lng_range, salt="lng")

        # The id carries the subscriber's own number, so the two halves of the
        # system can be read against each other by eye.
        customer_id = f"{GENERATED_PREFIX}{sid.lstrip('S').zfill(5)}"

        base = name.lower().replace(" ", ".").replace("'", "")
        email = f"{base}{GENERATED_DOMAIN}"
        if email in taken_emails:
            email = f"{base}.{sid.lower()}{GENERATED_DOMAIN}"
        taken_emails.add(email)

        db.merge(
            Customer(
                customer_id=customer_id,
                name=name,
                email=email,
                password_hash="",        # a record, not a login, until somebody registers
                role="customer",
                phone=phone,
                address=address,
                region=zone_name,
                gps_lat=gps_lat,
                gps_lng=gps_lng,
                plan=(subscriber.subscriber_type or "residential").capitalize(),
                status=(statuses.get(sid) or "active").capitalize(),
                consumption=round(measured["consumption"].get(sid, 0.0), 1),
                balance=round(measured["balance"].get(sid, 0.0), 2),
                created_at=_as_datetime(measured["started"].get(sid)),
            )
        )
        subscriber.customer_id = customer_id
        created += 1

    db.commit()
    return created, verbatim


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Give each ishtirak subscriber a CRM-shaped record."
    )
    parser.add_argument("--replace", action="store_true",
                        help="Delete previously generated records and rebuild them")
    parser.add_argument("--repair-emails", action="store_true",
                        help="Move subscribers off the old @generated.local domain, "
                             "which no email field in this project accepts")
    args = parser.parse_args()

    create_all_tables()
    db = SessionLocal()
    try:
        if args.repair_emails:
            fixed = repair_emails(db)
            if fixed:
                print(f"\n  {fixed} subscribers moved to {GENERATED_DOMAIN} and can now sign in.")
                print("  Nothing else on any record was changed.\n")
            else:
                print("\n  Every subscriber already has a usable email address.\n")
            return 0

        created, verbatim = generate(db, replace=args.replace)
        if not created:
            print("Nothing to do: every subscriber already has a record.")
            return 0

        linked = db.query(func.count()).select_from(Subscriber).filter(
            Subscriber.customer_id.isnot(None)
        ).scalar()

        print("\n" + "=" * 72)
        print(f"  {created} subscriber records created, {linked} subscribers now linked")
        print("=" * 72)
        print(f"    {verbatim:>3} taken from the CRM project's own seed file, each")
        print("        placed on a subscriber in the same zone")
        print(f"    {created - verbatim:>3} built from the same name pools, address format and")
        print("        phone prefixes, so the two sets read as one company's records")
        print()
        print("  GENERATED   name, email, phone, street, coordinate")
        print("  MEASURED    consumption, balance, region, plan, status, start date")
        print()
        print("  Consumption is the sum of each subscriber's own reading differences,")
        print("  counted from the installed dial so the first month is not lost.")
        print("  Balance is their own invoices minus their own payments. Neither is invented.")
        print()
        print("  The CRM seed's own readings, invoices and payments were NOT loaded:")
        print("  they cover the same twelve zones over a different year than the")
        print("  supervisor's export, and both behind one zone would be two answers.")
        print()

        for row in db.query(Customer).filter(
            Customer.customer_id.like(f"{GENERATED_PREFIX}%")
        ).limit(4):
            print(f"    {row.customer_id}  {row.name:<22} {row.region:<14} "
                  f"{row.consumption:>9.0f} kWh  {row.balance:>14.0f} LBP")
        print()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
