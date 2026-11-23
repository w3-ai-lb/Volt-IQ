"""
CRM module: the provider's office and field work, served by the same API as
the analytics platform.

Replaces the separate Supabase project that the CRM web app and the Flutter
field app used to talk to. Everything here works on the ishtirak tables that
the analytics side already reads (subscribers, subscriptions, meters,
meter_readings, invoices, invoice_payments, tariffs), plus `employees`. So a
reading captured on a phone is, the moment it is saved, an invoice in the CRM
and a data point for the loss and anomaly models.

Who may do what:

    GET  anything ............................ admin, staff, field
    POST /crm/readings, /crm/payments,
         /crm/customers ...................... admin, staff, field
    PATCH/DELETE customers, tariff ........... admin, staff
    employees: create/update/delete/assign ... admin, staff
    create an employee with role admin ....... admin only
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import require_office, require_staff
from app.core.security import hash_password
from app.database import get_db
from app.models.customer import Customer
from app.models.employee import ACCOUNT_ROLE_FOR, Employee, EmployeeAssignment
from app.models.invoice import Invoice, InvoicePayment, Tariff
from app.models.network import Zone
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription
from app.schemas.crm import (
    AssignmentUpdate,
    CrmCustomerCreate,
    CrmCustomerOut,
    CrmCustomerUpdate,
    CrmInvoiceOut,
    CrmMe,
    CrmPaymentOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    PaymentCreate,
    ReadingCreate,
    TariffOut,
    TariffUpdate,
)

router = APIRouter(prefix="/crm", tags=["CRM"])

DUE_AFTER_DAYS = 15
MIN_PASSWORD_LENGTH = 8

# CRM permission role <-> job role stored on the employee.
_DB_ROLE_FROM_APP = {"ADMIN": "admin", "MANAGER": "office_staff", "OFFICE_EMPLOYEE": "field_employee"}
_APP_ROLE_FROM_DB = {v: k for k, v in _DB_ROLE_FROM_APP.items()}
_APP_ROLE_FROM_ACCOUNT = {"admin": "ADMIN", "staff": "MANAGER", "field": "OFFICE_EMPLOYEE"}


# --- helpers -----------------------------------------------------------------
def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _round(value: float) -> float:
    return round(float(value or 0.0), 2)


def _title(role: str) -> str:
    return role.replace("_", " ").title()


def _employee_for_account(db: Session, account: Customer) -> Employee | None:
    return db.query(Employee).filter(Employee.account_id == account.customer_id).first()


def _db_role(app_role: str | None) -> str:
    role = (app_role or "").strip()
    if role in _DB_ROLE_FROM_APP:
        return _DB_ROLE_FROM_APP[role]
    if role in ACCOUNT_ROLE_FOR:
        return role
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown employee role: {app_role}")


def _zone_for_name(db: Session, name: str | None) -> Zone | None:
    """Find a zone by its name, creating it the first time it is used."""
    if not name or not name.strip():
        return None
    name = name.strip()
    zone = db.query(Zone).filter(func.lower(Zone.name) == name.lower()).first()
    if zone is None:
        zone = Zone(zone_id=_new_id("Z")[:10], name=name)
        db.add(zone)
        db.flush()
    return zone


def _current_tariff(db: Session, on: date | None = None) -> Tariff | None:
    on = on or date.today()
    return (
        db.query(Tariff)
        .filter(Tariff.effective_month <= on)
        .order_by(Tariff.effective_month.desc())
        .first()
    )


def _rate_for(db: Session, zone_id: str | None, on: date) -> tuple[float, str | None, str]:
    """(rate per kWh, tariff_id, currency) for a zone on a date."""
    tariff = _current_tariff(db, on)
    if tariff is None:
        return settings.TARIFF_LBP_PER_KWH, None, settings.CURRENCY
    rate = tariff.rate_per_kwh_base
    if zone_id and tariff.rate_per_kwh_highland:
        zone = db.get(Zone, zone_id)
        if zone is not None and zone.altitude_band == "above_700m":
            rate = tariff.rate_per_kwh_highland
    return rate, tariff.tariff_id, tariff.currency or settings.CURRENCY


def _invoice_status(total: float, paid: float, due: date) -> str:
    if paid >= total - 0.005:
        return "Paid"
    if paid > 0:
        return "Partial"
    if due < date.today():
        return "Overdue"
    return "Unpaid"


def _employee_out(emp: Employee, assigned: int = 0, account_email: str | None = None) -> EmployeeOut:
    return EmployeeOut(
        id=emp.employee_id,
        name=emp.full_name,
        email=emp.email or account_email,
        phone=emp.phone,
        role=_APP_ROLE_FROM_DB.get(emp.role, "OFFICE_EMPLOYEE"),
        db_role=emp.role,
        role_title=_title(emp.role),
        department=emp.department,
        zone=emp.zone_name,
        status="Active" if emp.is_active else "Inactive",
        can_sign_in=emp.account_id is not None,
        assigned_customers_count=assigned,
    )


class _Lookups:
    """Everything the customer, invoice and payment lists need, loaded once."""

    def __init__(self, db: Session):
        self.customers = {c.customer_id: c for c in db.query(Customer).all()}
        self.zones = {z.zone_id: z.name for z in db.query(Zone).all()}
        self.employees = {e.employee_id: e for e in db.query(Employee).all()}
        self.assignment = {a.subscriber_id: a.employee_id for a in db.query(EmployeeAssignment).all()}
        self.subscription = {}
        for sub in db.query(Subscription).all():
            self.subscription.setdefault(sub.subscriber_id, sub)
        self.meter = {m.subscription_id: m for m in db.query(Meter).all()}
        self.billed = dict(
            db.query(Invoice.subscriber_id, func.sum(Invoice.total_amount)).group_by(Invoice.subscriber_id)
        )
        self.paid = dict(
            db.query(InvoicePayment.subscriber_id, func.sum(InvoicePayment.amount))
            .group_by(InvoicePayment.subscriber_id)
        )

    def identity(self, sub: Subscriber) -> Customer | None:
        return self.customers.get(sub.customer_id) if sub.customer_id else None

    def name_of(self, sub_id: str, subscriber: Subscriber | None = None) -> str:
        if subscriber is not None:
            ident = self.identity(subscriber)
            if ident is not None:
                return ident.name
        return sub_id

    def staff_name(self, staff_id: str | None) -> str | None:
        if not staff_id:
            return None
        emp = self.employees.get(staff_id)
        if emp is not None:
            return emp.full_name
        acc = self.customers.get(staff_id)
        return acc.name if acc is not None else staff_id


def _customer_out(db: Session, sub: Subscriber, lk: _Lookups) -> CrmCustomerOut:
    ident = lk.identity(sub)
    subscription = lk.subscription.get(sub.subscriber_id)
    meter = lk.meter.get(subscription.subscription_id) if subscription else None

    latest = (
        db.query(MeterReading)
        .filter(MeterReading.subscription_id == subscription.subscription_id)
        .order_by(MeterReading.billing_period.desc(), MeterReading.reading_date.desc())
        .limit(2)
        .all()
        if subscription
        else []
    )
    current = latest[0].reading_value if latest else (meter.initial_reading if meter else 0.0) or 0.0
    previous = latest[1].reading_value if len(latest) > 1 else (meter.initial_reading if meter else 0.0) or 0.0
    last_date = (latest[0].reading_date or latest[0].billing_period) if latest else None

    balance = max(0.0, (lk.billed.get(sub.subscriber_id) or 0.0) - (lk.paid.get(sub.subscriber_id) or 0.0))
    emp_id = lk.assignment.get(sub.subscriber_id)
    emp = lk.employees.get(emp_id) if emp_id else None

    return CrmCustomerOut(
        id=sub.subscriber_id,
        account_no=sub.customer_id or sub.subscriber_id,
        meter_no=(meter.serial_number or meter.meter_id) if meter else None,
        name=ident.name if ident else sub.subscriber_id,
        email=None if ident is None or ident.email.startswith("unclaimed.") else ident.email,
        phone=ident.phone if ident else None,
        address=ident.address if ident else None,
        tariff_type=(ident.plan if ident else (sub.subscriber_type or "residential").title()),
        zone=lk.zones.get(sub.zone_id) if sub.zone_id else None,
        assigned_employee_id=emp_id,
        assigned_employee_name=emp.full_name if emp else "Unassigned",
        previous_reading=previous,
        current_reading=current,
        last_reading_date=last_date,
        status=ident.status if ident else ((subscription.status or "active").title() if subscription else "Active"),
        balance=_round(balance),
        outstanding_status="Unpaid" if balance > 0.005 else "Paid",
        meter_type=meter.meter_type if meter else None,
        has_portal_access=bool(ident and ident.is_claimed),
    )


def _get_subscriber(db: Session, subscriber_id: str) -> Subscriber:
    sub = db.get(Subscriber, subscriber_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return sub


def _set_assignment(db: Session, subscriber_id: str, employee_id: str | None) -> None:
    db.query(EmployeeAssignment).filter(EmployeeAssignment.subscriber_id == subscriber_id).delete()
    if employee_id:
        if db.get(Employee, employee_id) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown employee")
        db.add(EmployeeAssignment(employee_id=employee_id, subscriber_id=subscriber_id))


def _invoice_out(inv: Invoice, paid: float, lk: _Lookups, sub: Subscriber | None, issue: date | None) -> CrmInvoiceOut:
    issue_date = issue or inv.billing_period
    due = issue_date + timedelta(days=DUE_AFTER_DAYS)
    subscription = lk.subscription.get(inv.subscriber_id)
    meter = lk.meter.get(subscription.subscription_id) if subscription else None
    ident = lk.identity(sub) if sub else None
    return CrmInvoiceOut(
        id=inv.invoice_id,
        invoice_number=inv.invoice_id,
        customer_id=inv.subscriber_id,
        customer_name=lk.name_of(inv.subscriber_id, sub),
        account_no=(sub.customer_id if sub else None) or inv.subscriber_id,
        meter_no=(meter.serial_number or meter.meter_id) if meter else None,
        billing_period=inv.billing_period,
        issue_date=issue_date,
        due_date=due,
        previous_reading=inv.previous_reading,
        current_reading=inv.current_reading,
        kwh_consumed=_round(inv.units_consumed),
        tariff_type=ident.plan if ident else "Residential",
        rate_applied=inv.rate_applied,
        base_charge=_round(inv.fixed_charge),
        consumption_charge=_round(inv.variable_charge),
        tax_amount=0.0,
        total_amount=_round(inv.total_amount),
        paid_amount=_round(paid),
        status=_invoice_status(inv.total_amount or 0.0, paid, due),
        currency=inv.currency or settings.CURRENCY,
        recorded_by=lk.staff_name(inv.issued_by),
        recorded_by_id=inv.issued_by,
    )


def _payment_out(p: InvoicePayment, lk: _Lookups, subs: dict[str, Subscriber]) -> CrmPaymentOut:
    return CrmPaymentOut(
        id=p.payment_id,
        receipt_no=p.receipt_no or p.payment_id,
        customer_id=p.subscriber_id,
        customer_name=lk.name_of(p.subscriber_id, subs.get(p.subscriber_id)),
        invoice_id=p.invoice_id,
        invoice_number=p.invoice_id or "General Account Payment",
        amount=_round(p.amount),
        currency=p.currency or settings.CURRENCY,
        payment_method=p.payment_method,
        payment_date=p.payment_date,
        reference_no=p.reference_no,
        recorded_by=lk.staff_name(p.collected_by),
        notes=p.notes,
    )


def _actor_id(db: Session, account: Customer) -> str:
    """Who did it: the employee id when there is one, else the account id."""
    emp = _employee_for_account(db, account)
    return emp.employee_id if emp else account.customer_id


# --- who am I ----------------------------------------------------------------
@router.get("/me", response_model=CrmMe)
def me(db: Session = Depends(get_db), user: Customer = Depends(require_staff)) -> CrmMe:
    emp = _employee_for_account(db, user)
    return CrmMe(
        id=emp.employee_id if emp else user.customer_id,
        account_id=user.customer_id,
        name=emp.full_name if emp else user.name,
        email=user.email,
        role=_APP_ROLE_FROM_ACCOUNT.get(user.role, "OFFICE_EMPLOYEE"),
        role_title=_title(emp.role) if emp else _title(user.role),
        account_role=user.role,
        zone=emp.zone_name if emp else user.region,
        phone=emp.phone if emp else user.phone,
    )


# --- customers -----------------------------------------------------------------
@router.get("/customers", response_model=list[CrmCustomerOut])
def list_customers(
    mine: bool = Query(False, description="Only the subscribers assigned to the signed-in employee"),
    db: Session = Depends(get_db),
    user: Customer = Depends(require_staff),
) -> list[CrmCustomerOut]:
    lk = _Lookups(db)
    subs = db.query(Subscriber).order_by(Subscriber.subscriber_id).all()
    if mine:
        me_id = _actor_id(db, user)
        subs = [s for s in subs if lk.assignment.get(s.subscriber_id) == me_id]
    return [_customer_out(db, s, lk) for s in subs]


@router.get("/customers/{subscriber_id}", response_model=CrmCustomerOut)
def get_customer(subscriber_id: str, db: Session = Depends(get_db), _: Customer = Depends(require_staff)):
    return _customer_out(db, _get_subscriber(db, subscriber_id), _Lookups(db))


@router.post("/customers", response_model=CrmCustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CrmCustomerCreate, db: Session = Depends(get_db), _: Customer = Depends(require_staff)
) -> CrmCustomerOut:
    customer_id = _new_id("CUST")
    email = (payload.email or "").strip().lower() or f"unclaimed.{customer_id.lower()}@voltiq.demo"
    if db.query(Customer).filter(func.lower(Customer.email) == email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "This email is already used by another account")

    zone = _zone_for_name(db, payload.zone)
    db.add(
        Customer(
            customer_id=customer_id,
            name=payload.name.strip(),
            email=email,
            password_hash="",          # unclaimed until the customer registers
            role="customer",
            phone=payload.phone,
            address=payload.address,
            region=zone.name if zone else None,
            plan=payload.tariff_type or "Residential",
            status=payload.status or "Active",
        )
    )
    sub_id = _new_id("SUB")
    db.add(
        Subscriber(
            subscriber_id=sub_id,
            zone_id=zone.zone_id if zone else None,
            subscriber_type=(payload.tariff_type or "Residential").lower(),
            customer_id=customer_id,
        )
    )
    subscription_id = _new_id("SBN")
    db.add(
        Subscription(
            subscription_id=subscription_id,
            subscriber_id=sub_id,
            zone_id=zone.zone_id if zone else None,
            billing_model="metered",
            status="active",
        )
    )
    db.add(
        Meter(
            meter_id=_new_id("MTR"),
            subscription_id=subscription_id,
            serial_number=payload.meter_no,
            meter_type=payload.meter_type or "digital",
            initial_reading=payload.initial_reading or 0.0,
        )
    )
    db.flush()
    _set_assignment(db, sub_id, payload.assigned_employee_id)
    db.commit()
    return _customer_out(db, db.get(Subscriber, sub_id), _Lookups(db))


@router.patch("/customers/{subscriber_id}", response_model=CrmCustomerOut)
def update_customer(
    subscriber_id: str,
    payload: CrmCustomerUpdate,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_office),
) -> CrmCustomerOut:
    sub = _get_subscriber(db, subscriber_id)
    fields = payload.model_dump(exclude_unset=True)
    ident = db.get(Customer, sub.customer_id) if sub.customer_id else None

    if ident is not None:
        for src, dst in (("name", "name"), ("phone", "phone"), ("address", "address"),
                         ("tariff_type", "plan"), ("status", "status")):
            if fields.get(src) is not None:
                setattr(ident, dst, fields[src])
        if fields.get("email"):
            email = fields["email"].strip().lower()
            clash = db.query(Customer).filter(func.lower(Customer.email) == email).first()
            if clash is not None and clash.customer_id != ident.customer_id:
                raise HTTPException(status.HTTP_409_CONFLICT, "This email is already used by another account")
            ident.email = email

    if "zone" in fields:
        zone = _zone_for_name(db, fields["zone"])
        sub.zone_id = zone.zone_id if zone else None
        if ident is not None and zone is not None:
            ident.region = zone.name
    if fields.get("meter_type"):
        subscription = db.query(Subscription).filter(Subscription.subscriber_id == sub.subscriber_id).first()
        if subscription and subscription.meter:
            subscription.meter.meter_type = fields["meter_type"]
    if "assigned_employee_id" in fields:
        _set_assignment(db, sub.subscriber_id, fields["assigned_employee_id"])

    db.commit()
    return _customer_out(db, sub, _Lookups(db))


@router.delete("/customers/{subscriber_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(subscriber_id: str, db: Session = Depends(get_db), _: Customer = Depends(require_office)):
    sub = _get_subscriber(db, subscriber_id)
    ident = db.get(Customer, sub.customer_id) if sub.customer_id else None
    db.delete(sub)
    # The identity goes too unless somebody signed in with it: a claimed
    # account holds the customer's own history and is closed, not erased.
    if ident is not None and ident.role == "customer":
        if ident.is_claimed:
            ident.status = "Inactive"
        else:
            db.delete(ident)
    db.commit()


# --- employees -----------------------------------------------------------------
@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db), _: Customer = Depends(require_staff)) -> list[EmployeeOut]:
    counts = dict(
        db.query(EmployeeAssignment.employee_id, func.count(EmployeeAssignment.id))
        .group_by(EmployeeAssignment.employee_id)
    )
    emails = {c.customer_id: c.email for c in db.query(Customer).filter(Customer.role != "customer")}
    return [
        _employee_out(e, counts.get(e.employee_id, 0), emails.get(e.account_id))
        for e in db.query(Employee).order_by(Employee.full_name).all()
    ]


@router.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate, db: Session = Depends(get_db), user: Customer = Depends(require_office)
) -> EmployeeOut:
    role = _db_role(payload.role)
    if role == "admin" and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can add another administrator")

    emp = Employee(
        employee_id=_new_id("EMP"),
        full_name=payload.name.strip(),
        email=(payload.email or "").strip().lower() or None,
        phone=payload.phone,
        role=role,
        department=payload.department,
        zone_name=payload.zone,
        is_active=True,
    )

    if payload.email and payload.password:
        if len(payload.password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"The password must be at least {MIN_PASSWORD_LENGTH} characters",
            )
        email = payload.email.strip().lower()
        if db.query(Customer).filter(func.lower(Customer.email) == email).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "This email is already used by another account")
        account = Customer(
            customer_id=_new_id("STF"),
            name=emp.full_name,
            email=email,
            password_hash=hash_password(payload.password),
            role=ACCOUNT_ROLE_FOR[role],
            phone=payload.phone,
            region=payload.zone,
            plan="Staff",
            status="Active",
        )
        db.add(account)
        db.flush()
        emp.account_id = account.customer_id

    db.add(emp)
    db.commit()
    return _employee_out(emp)


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    user: Customer = Depends(require_office),
) -> EmployeeOut:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    fields = payload.model_dump(exclude_unset=True)
    account = db.get(Customer, emp.account_id) if emp.account_id else None

    if fields.get("role"):
        role = _db_role(fields["role"])
        if (role == "admin" or emp.role == "admin") and user.role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can change an administrator")
        emp.role = role
        if account is not None:
            account.role = ACCOUNT_ROLE_FOR[role]
            account.session_version = (account.session_version or 0) + 1   # re-sign-in with new rights
    if fields.get("name"):
        emp.full_name = fields["name"]
        if account is not None:
            account.name = fields["name"]
    for src, dst in (("phone", "phone"), ("department", "department"), ("zone", "zone_name")):
        if src in fields:
            setattr(emp, dst, fields[src])
    if fields.get("status"):
        emp.is_active = fields["status"] == "Active"
        if account is not None:
            account.status = "Active" if emp.is_active else "Inactive"

    db.commit()
    count = db.query(EmployeeAssignment).filter(EmployeeAssignment.employee_id == employee_id).count()
    return _employee_out(emp, count, account.email if account else None)


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: str, db: Session = Depends(get_db), user: Customer = Depends(require_office)):
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    if emp.account_id == user.customer_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own employee record")
    if emp.role == "admin" and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can delete an administrator")
    account = db.get(Customer, emp.account_id) if emp.account_id else None
    db.delete(emp)
    if account is not None and account.role != "customer":
        db.delete(account)
    db.commit()


@router.put("/employees/{employee_id}/customers", response_model=EmployeeOut)
def assign_customers(
    employee_id: str,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
    _: Customer = Depends(require_office),
) -> EmployeeOut:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    db.query(EmployeeAssignment).filter(EmployeeAssignment.employee_id == employee_id).delete()
    for sub_id in dict.fromkeys(payload.customer_ids):
        _get_subscriber(db, sub_id)
        _set_assignment(db, sub_id, employee_id)
    db.commit()
    return _employee_out(emp, len(set(payload.customer_ids)))


# --- readings -> invoices -----------------------------------------------------
@router.post("/readings", response_model=CrmInvoiceOut, status_code=status.HTTP_201_CREATED)
def record_reading(
    payload: ReadingCreate, db: Session = Depends(get_db), user: Customer = Depends(require_staff)
) -> CrmInvoiceOut:
    """
    Save a meter reading and issue the invoice it produces, in one step.

    This is what a field employee's phone calls after reading a meter, and what
    "Generate invoice" calls in the office.
    """
    sub = _get_subscriber(db, payload.customer_id)
    subscription = db.query(Subscription).filter(Subscription.subscriber_id == sub.subscriber_id).first()
    if subscription is None or subscription.meter is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This customer has no meter on file")
    meter = subscription.meter

    last = (
        db.query(MeterReading)
        .filter(MeterReading.subscription_id == subscription.subscription_id)
        .order_by(MeterReading.billing_period.desc(), MeterReading.reading_date.desc())
        .first()
    )
    previous = payload.previous_reading
    if previous is None:
        previous = last.reading_value if last else (meter.initial_reading or 0.0)
    if payload.current_reading < previous:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"The new reading ({payload.current_reading:g}) is lower than the previous one "
            f"({previous:g}). Check the dial; if the meter rolled over, record it from the office.",
        )

    when = payload.reading_date or date.today()
    period = when.replace(day=1)
    units = (payload.current_reading - previous) * (meter.multiplier or 1.0)
    rate, tariff_id, currency = _rate_for(db, sub.zone_id, when)
    fixed = settings.FIXED_CHARGE_PER_INVOICE
    variable = units * rate
    actor = _actor_id(db, user)

    reading = MeterReading(
        reading_id=_new_id("RD"),
        meter_id=meter.meter_id,
        subscription_id=subscription.subscription_id,
        billing_period=period,
        reading_value=payload.current_reading,
        capture_method=payload.capture_method,
        ocr_confidence=payload.ocr_confidence,
        was_corrected=False,
        subscription_status=subscription.status,
        reading_date=when,
    )
    invoice = Invoice(
        invoice_id=_new_id("INV"),
        subscription_id=subscription.subscription_id,
        subscriber_id=sub.subscriber_id,
        zone_id=sub.zone_id,
        billing_period=period,
        units_consumed=units,
        tariff_id=tariff_id,
        rate_applied=rate,
        fixed_charge=fixed,
        variable_charge=variable,
        total_amount=fixed + variable,
        currency=currency,
        previous_reading=previous,
        current_reading=payload.current_reading,
        reading_id=reading.reading_id,
        issued_by=actor,
    )
    db.add_all([reading, invoice])
    db.commit()
    return _invoice_out(invoice, 0.0, _Lookups(db), sub, when)


@router.get("/invoices", response_model=list[CrmInvoiceOut])
def list_invoices(
    customer_id: str | None = Query(None, alias="customerId"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: Customer = Depends(require_staff),
) -> list[CrmInvoiceOut]:
    q = db.query(Invoice)
    if customer_id:
        q = q.filter(Invoice.subscriber_id == customer_id)
    invoices = q.order_by(Invoice.billing_period.desc(), Invoice.invoice_id.desc()).limit(limit).all()

    ids = [i.invoice_id for i in invoices]
    paid = dict(
        db.query(InvoicePayment.invoice_id, func.sum(InvoicePayment.amount))
        .filter(InvoicePayment.invoice_id.in_(ids))
        .group_by(InvoicePayment.invoice_id)
    ) if ids else {}
    reading_ids = [i.reading_id for i in invoices if i.reading_id]
    reading_dates = dict(
        db.query(MeterReading.reading_id, MeterReading.reading_date).filter(MeterReading.reading_id.in_(reading_ids))
    ) if reading_ids else {}
    subs = {s.subscriber_id: s for s in db.query(Subscriber).filter(
        Subscriber.subscriber_id.in_({i.subscriber_id for i in invoices}))} if invoices else {}

    lk = _Lookups(db)
    return [
        _invoice_out(i, paid.get(i.invoice_id) or 0.0, lk, subs.get(i.subscriber_id), reading_dates.get(i.reading_id))
        for i in invoices
    ]


# --- payments ------------------------------------------------------------------
@router.get("/payments", response_model=list[CrmPaymentOut])
def list_payments(
    customer_id: str | None = Query(None, alias="customerId"),
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: Customer = Depends(require_staff),
) -> list[CrmPaymentOut]:
    q = db.query(InvoicePayment)
    if customer_id:
        q = q.filter(InvoicePayment.subscriber_id == customer_id)
    payments = q.order_by(InvoicePayment.payment_date.desc(), InvoicePayment.payment_id.desc()).limit(limit).all()
    subs = {s.subscriber_id: s for s in db.query(Subscriber).filter(
        Subscriber.subscriber_id.in_({p.subscriber_id for p in payments}))} if payments else {}
    lk = _Lookups(db)
    return [_payment_out(p, lk, subs) for p in payments]


@router.post("/payments", response_model=CrmPaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(
    payload: PaymentCreate, db: Session = Depends(get_db), user: Customer = Depends(require_staff)
) -> CrmPaymentOut:
    sub = _get_subscriber(db, payload.customer_id)
    invoice = None
    if payload.invoice_id:
        invoice = db.get(Invoice, payload.invoice_id)
        if invoice is None or invoice.subscriber_id != sub.subscriber_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found for this customer")
    else:
        # The oldest invoice that is not fully paid, if any.
        paid = dict(
            db.query(InvoicePayment.invoice_id, func.sum(InvoicePayment.amount))
            .filter(InvoicePayment.subscriber_id == sub.subscriber_id)
            .group_by(InvoicePayment.invoice_id)
        )
        for inv in db.query(Invoice).filter(Invoice.subscriber_id == sub.subscriber_id).order_by(Invoice.billing_period):
            if (paid.get(inv.invoice_id) or 0.0) < (inv.total_amount or 0.0) - 0.005:
                invoice = inv
                break

    now = datetime.now(UTC)
    payment = InvoicePayment(
        payment_id=_new_id("PAY"),
        invoice_id=invoice.invoice_id if invoice else None,
        subscriber_id=sub.subscriber_id,
        amount=payload.amount,
        currency=invoice.currency if invoice else settings.CURRENCY,
        payment_method=payload.payment_method,
        payment_date=now.date(),
        collected_by=_actor_id(db, user),
        receipt_no=f"RCP-{now:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}",
        reference_no=payload.reference_no,
        notes=payload.notes,
    )
    db.add(payment)
    db.commit()
    return _payment_out(payment, _Lookups(db), {sub.subscriber_id: sub})


# --- tariff ----------------------------------------------------------------------
@router.get("/tariff", response_model=TariffOut)
def get_tariff(db: Session = Depends(get_db), _: Customer = Depends(require_staff)) -> TariffOut:
    tariff = _current_tariff(db)
    return TariffOut(
        rate_per_kwh=tariff.rate_per_kwh_base if tariff else settings.TARIFF_LBP_PER_KWH,
        fixed_charge=settings.FIXED_CHARGE_PER_INVOICE,
        currency=(tariff.currency if tariff else None) or settings.CURRENCY,
        effective_month=tariff.effective_month if tariff else None,
    )


@router.put("/tariff", response_model=TariffOut)
def set_tariff(payload: TariffUpdate, db: Session = Depends(get_db), _: Customer = Depends(require_office)) -> TariffOut:
    """
    Set this month's rate. Applies to invoices issued from now on; invoices
    already issued keep the rate printed on them.
    """
    month = date.today().replace(day=1)
    tariff = db.query(Tariff).filter(Tariff.effective_month == month).first()
    if tariff is None:
        tariff = Tariff(tariff_id=f"T-{month:%Y-%m}", effective_month=month, currency=settings.CURRENCY,
                        rate_per_kwh_base=payload.rate_per_kwh)
        db.add(tariff)
    tariff.rate_per_kwh_base = payload.rate_per_kwh
    db.commit()
    return get_tariff(db, _)


# Kept for callers that want the totals without loading every list.
@router.get("/summary")
def summary(db: Session = Depends(get_db), _: Customer = Depends(require_staff)) -> dict:
    billed = db.query(func.coalesce(func.sum(Invoice.total_amount), 0.0)).scalar() or 0.0
    collected = db.query(func.coalesce(func.sum(InvoicePayment.amount), 0.0)).scalar() or 0.0
    by_zone: dict[str, int] = defaultdict(int)
    for (zone_id,) in db.query(Subscriber.zone_id):
        by_zone[zone_id or "-"] += 1
    return {
        "totalCustomers": db.query(func.count(Subscriber.subscriber_id)).scalar() or 0,
        "totalEmployees": db.query(func.count(Employee.employee_id)).scalar() or 0,
        "totalBilled": _round(billed),
        "totalCollected": _round(collected),
        "outstanding": _round(max(0.0, billed - collected)),
        "kwhBilled": _round(db.query(func.coalesce(func.sum(Invoice.units_consumed), 0.0)).scalar() or 0.0),
        "currency": settings.CURRENCY,
    }
