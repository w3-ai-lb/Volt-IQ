"""
Demo data for the CRM module: zones, subscribers, meters, three months of
readings with their invoices and payments, and three staff members who can
sign in.

It builds on the customer accounts that app/pipeline/seed.py creates, so the
same people appear in the analytics portal and in the CRM.

Run on its own (it does nothing if employees already exist):

    python -m app.pipeline.crm_seed

The demo staff passwords are public (they are printed here and in the README).
Never seed a database that other people can reach.
"""

from __future__ import annotations

import logging
import random
import sys
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import hash_password
from app.database import SessionLocal, create_all_tables
from app.models.customer import Customer
from app.models.employee import ACCOUNT_ROLE_FOR, Employee, EmployeeAssignment
from app.models.invoice import Invoice, InvoicePayment
from app.models.network import Zone
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription

logger = logging.getLogger(__name__)

STAFF = [
    # employee_id, name, email, password, role, zone
    ("EMP-0001", "Hiba Nasser", "office@voltiq.demo", "office1234", "office_staff", "Beirut"),
    ("EMP-0002", "Omar Fakhoury", "field@voltiq.demo", "field1234", "field_employee", "Beirut"),
    ("EMP-0003", "Rita Chamoun", "field2@voltiq.demo", "field1234", "field_employee", "Mount Lebanon"),
]

MONTHS = 3


def _month_start(d: date, back: int) -> date:
    y, m = d.year, d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def seed_crm(db: Session) -> bool:
    """Create the CRM demo data. Returns False (and does nothing) if staff already exist."""
    if db.query(Employee).first() is not None:
        logger.info("CRM demo data: employees already exist, nothing to do")
        return False

    rng = random.Random(42)
    today = date.today()

    customers = (
        db.query(Customer).filter(Customer.role == "customer").order_by(Customer.customer_id).all()
    )
    already = {s.customer_id for s in db.query(Subscriber).filter(Subscriber.customer_id.isnot(None))}

    # Zones from the regions the customers live in.
    zones: dict[str, Zone] = {z.name: z for z in db.query(Zone).all()}
    for region in sorted({c.region for c in customers if c.region}):
        if region not in zones:
            zones[region] = Zone(zone_id=f"Z-{len(zones) + 1:03d}", name=region, area_type="urban")
            db.add(zones[region])
    db.flush()

    # Staff and their sign-in accounts.
    employees: list[Employee] = []
    for emp_id, name, email, password, role, zone in STAFF:
        account = db.query(Customer).filter(Customer.email == email).first()
        if account is None:
            account = Customer(
                customer_id=f"STF-{emp_id[-4:]}",
                name=name,
                email=email,
                password_hash=hash_password(password),
                role=ACCOUNT_ROLE_FOR[role],
                region=zone,
                plan="Staff",
                status="Active",
            )
            db.add(account)
            db.flush()
        emp = Employee(
            employee_id=emp_id, full_name=name, email=email, role=role,
            department="Operations", zone_name=zone, is_active=True, account_id=account.customer_id,
            phone=f"+961 3 {rng.randint(100, 999)} {rng.randint(100, 999)}",
        )
        db.add(emp)
        employees.append(emp)
    db.flush()
    field_staff = [e for e in employees if e.role == "field_employee"]

    created = 0
    for i, cust in enumerate(customers, start=1):
        if cust.customer_id in already:
            continue
        zone = zones.get(cust.region) if cust.region else None
        sub_id = f"SUB-{i:04d}"
        sbn_id = f"SBN-{i:04d}"
        db.add(Subscriber(subscriber_id=sub_id, zone_id=zone.zone_id if zone else None,
                          subscriber_type=(cust.plan or "Residential").lower(), customer_id=cust.customer_id))
        db.add(Subscription(subscription_id=sbn_id, subscriber_id=sub_id, zone_id=zone.zone_id if zone else None,
                            ampere_capacity=rng.choice([5, 10, 15, 20]), phase_type="single_phase",
                            billing_model="metered", status="active"))
        start = float(rng.randint(1_000, 20_000))
        meter_id = f"MTR-{i:05d}"
        db.add(Meter(meter_id=meter_id, subscription_id=sbn_id, serial_number=f"SN-{740000 + i}",
                     meter_type=rng.choice(["digital", "mechanical"]), digit_count=6, multiplier=1.0,
                     initial_reading=start))

        # Assign to the field employee working that zone, else round-robin.
        match = [e for e in field_staff if e.zone_name == cust.region] or field_staff
        if match:
            db.add(EmployeeAssignment(employee_id=match[i % len(match)].employee_id, subscriber_id=sub_id))

        scale = 3.0 if cust.plan == "Commercial" else 1.0
        previous = start
        for back in range(MONTHS, 0, -1):
            period = _month_start(today, back)
            read_on = period + timedelta(days=rng.randint(24, 27))
            units = round(rng.uniform(180, 420) * scale, 1)
            current = previous + units
            rd_id = f"RD-{i:04d}-{back}"
            db.add(MeterReading(reading_id=rd_id, meter_id=meter_id, subscription_id=sbn_id, billing_period=period,
                                reading_value=current, capture_method="ocr",
                                ocr_confidence=round(rng.uniform(0.86, 0.99), 2),
                                subscription_status="active", reading_date=read_on))
            rate = settings.TARIFF_LBP_PER_KWH
            fixed = settings.FIXED_CHARGE_PER_INVOICE
            total = round(fixed + units * rate, 0)
            inv_id = f"INV-{i:04d}-{back}"
            reader = match[i % len(match)].employee_id if match else None
            db.add(Invoice(invoice_id=inv_id, subscription_id=sbn_id, subscriber_id=sub_id,
                           zone_id=zone.zone_id if zone else None, billing_period=period, units_consumed=units,
                           rate_applied=rate, fixed_charge=fixed, variable_charge=total - fixed,
                           total_amount=total, currency=settings.CURRENCY, previous_reading=previous,
                           current_reading=current, reading_id=rd_id, issued_by=reader))
            # Older months are mostly paid; the latest month is often still open.
            if back > 1 or rng.random() < 0.35:
                db.add(InvoicePayment(payment_id=f"PAY-{i:04d}-{back}", invoice_id=inv_id, subscriber_id=sub_id,
                                      amount=total, currency=settings.CURRENCY,
                                      payment_method=rng.choice(["cash", "omt", "whish"]),
                                      payment_date=read_on + timedelta(days=rng.randint(2, 12)),
                                      collected_by=reader, receipt_no=f"RCP-{i:04d}-{back}"))
            previous = current
        created += 1

    db.commit()
    logger.info("CRM demo data: %d staff, %d subscribers with %d months each", len(employees), created, MONTHS)
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    create_all_tables()
    with SessionLocal() as db:
        seed_crm(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
