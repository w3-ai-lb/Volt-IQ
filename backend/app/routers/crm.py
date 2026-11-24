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

STAGE 2 CHANGES
---------------
* Linked billing: an invoice issued here also becomes the customer's portal
  bill, and payments are mirrored both ways (app/core/billing_link.py).
* Users: staff sign-in accounts live in `users`, not `customers`.
* Fast lists: every list costs a fixed number of queries however many rows it
  returns (no query per customer), and the customer list is paged and
  searched on the server (/crm/customers/page).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.accounts import email_in_use
from app.core.billing_link import link_invoice, mirror_crm_payment, refresh_customer_feeds
from app.core.deps import require_office, require_staff
from app.core.security import hash_password
from app.database import get_db
from app.models.customer import Customer
from app.models.employee import ACCOUNT_ROLE_FOR, Employee, EmployeeAssignment
from app.models.invoice import Invoice, InvoicePayment, Tariff
from app.models.network import Zone
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription
from app.models.user import User
from app.schemas.crm import (
    AssignmentUpdate,
    CrmCustomerCreate,
    CrmCustomerOption,
    CrmCustomerOut,
    CrmCustomerPage,
    CrmCustomerUpdate,
    CrmInvoiceOut,
    CrmMe,
    CrmPaymentOut,
    CrmSummary,
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
MAX_PAGE = 500

# CRM permission role <-> job role stored on the employee.
_DB_ROLE_FROM_APP = {"ADMIN": "admin", "MANAGER": "office_staff", "OFFICE_EMPLOYEE": "field_employee"}
_APP_ROLE_FROM_DB = {v: k for k, v in _DB_ROLE_FROM_APP.items()}
_APP_ROLE_FROM_ACCOUNT = {"admin": "ADMIN", "staff": "MANAGER", "field": "OFFICE_EMPLOYEE"}


# --- small helpers ---------------------------------------------------------------
def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _round(value: float) -> float:
    return round(float(value or 0.0), 2)


def _title(role: str) -> str:
    return role.replace("_", " ").title()


def _employee_for_account(db: Session, account) -> Employee | None:
    return db.query(Employee).filter(Employee.account_id == account.customer_id).first()


def _actor_id(db: Session, account) -> str:
    """Who did it: the employee id when there is one, else the account id."""
    emp = _employee_for_account(db, account)
    return emp.employee_id if emp else account.customer_id


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


def _staff_names(db: Session, ids: set[str]) -> dict[str, str]:
    """Display names for employee ids or account ids (one query each)."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    names = {e.employee_id: e.full_name for e in db.query(Employee).filter(Employee.employee_id.in_(ids))}
    rest = ids - names.keys()
    if rest:
        names.update({u.user_id: u.name for u in db.query(User).filter(User.user_id.in_(rest))})
        rest -= names.keys()
    if rest:
        names.update({c.customer_id: c.name for c in db.query(Customer).filter(Customer.customer_id.in_(rest))})
    return names


# --- customer rows: a fixed number of queries for any page size --------------------
def _customer_rows(db: Session, subs: list[Subscriber]) -> list[CrmCustomerOut]:
    """
    Build CRM customer rows for these subscribers with seven queries in total,
    whether there are 5 or 5,000 of them. (Stage 1 made one query per customer.)
    """
    if not subs:
        return []
    sub_ids = [s.subscriber_id for s in subs]
    cust_ids = {s.customer_id for s in subs if s.customer_id}
    zone_ids = {s.zone_id for s in subs if s.zone_id}

    customers = (
        {c.customer_id: c for c in db.query(Customer).filter(Customer.customer_id.in_(cust_ids))} if cust_ids else {}
    )
    zones = {z.zone_id: z.name for z in db.query(Zone).filter(Zone.zone_id.in_(zone_ids))} if zone_ids else {}

    subscription: dict[str, Subscription] = {}
    for sbn in db.query(Subscription).filter(Subscription.subscriber_id.in_(sub_ids)).order_by(
        Subscription.subscription_id
    ):
        subscription.setdefault(sbn.subscriber_id, sbn)
    sbn_ids = [s.subscription_id for s in subscription.values()]
    meters = {m.subscription_id: m for m in db.query(Meter).filter(Meter.subscription_id.in_(sbn_ids))} if sbn_ids else {}

    assignment = dict(
        db.query(EmployeeAssignment.subscriber_id, EmployeeAssignment.employee_id).filter(
            EmployeeAssignment.subscriber_id.in_(sub_ids)
        )
    )
    emp_names = (
        dict(db.query(Employee.employee_id, Employee.full_name).filter(Employee.employee_id.in_(set(assignment.values()))))
        if assignment
        else {}
    )

    billed = dict(
        db.query(Invoice.subscriber_id, func.sum(Invoice.total_amount))
        .filter(Invoice.subscriber_id.in_(sub_ids))
        .group_by(Invoice.subscriber_id)
    )
    paid = dict(
        db.query(InvoicePayment.subscriber_id, func.sum(InvoicePayment.amount))
        .filter(InvoicePayment.subscriber_id.in_(sub_ids))
        .group_by(InvoicePayment.subscriber_id)
    )

    # The last two readings of every subscription, in ONE query (window function).
    latest: dict[str, list] = defaultdict(list)
    if sbn_ids:
        rn = (
            func.row_number()
            .over(
                partition_by=MeterReading.subscription_id,
                order_by=(MeterReading.billing_period.desc(), MeterReading.reading_date.desc()),
            )
            .label("rn")
        )
        ranked = (
            select(
                MeterReading.subscription_id,
                MeterReading.reading_value,
                MeterReading.reading_date,
                MeterReading.billing_period,
                rn,
            )
            .where(MeterReading.subscription_id.in_(sbn_ids))
            .subquery()
        )
        for row in db.execute(select(ranked).where(ranked.c.rn <= 2).order_by(ranked.c.subscription_id, ranked.c.rn)):
            latest[row.subscription_id].append(row)

    out = []
    for sub in subs:
        ident = customers.get(sub.customer_id) if sub.customer_id else None
        sbn = subscription.get(sub.subscriber_id)
        meter = meters.get(sbn.subscription_id) if sbn else None
        reads = latest.get(sbn.subscription_id, []) if sbn else []
        start = (meter.initial_reading if meter else 0.0) or 0.0
        current = reads[0].reading_value if reads else start
        previous = reads[1].reading_value if len(reads) > 1 else start
        balance = max(0.0, (billed.get(sub.subscriber_id) or 0.0) - (paid.get(sub.subscriber_id) or 0.0))
        emp_id = assignment.get(sub.subscriber_id)
        out.append(
            CrmCustomerOut(
                id=sub.subscriber_id,
                account_no=sub.customer_id or sub.subscriber_id,
                meter_no=(meter.serial_number or meter.meter_id) if meter else None,
                name=ident.name if ident else sub.subscriber_id,
                email=None if ident is None or ident.email.startswith("unclaimed.") else ident.email,
                phone=ident.phone if ident else None,
                address=ident.address if ident else None,
                tariff_type=ident.plan if ident else (sub.subscriber_type or "residential").title(),
                zone=zones.get(sub.zone_id) if sub.zone_id else None,
                assigned_employee_id=emp_id,
                assigned_employee_name=emp_names.get(emp_id, "Unassigned") if emp_id else "Unassigned",
                previous_reading=previous,
                current_reading=current,
                last_reading_date=(reads[0].reading_date or reads[0].billing_period) if reads else None,
                status=ident.status if ident else ((sbn.status or "active").title() if sbn else "Active"),
                balance=_round(balance),
                outstanding_status="Unpaid" if balance > 0.005 else "Paid",
                meter_type=meter.meter_type if meter else None,
                has_portal_access=bool(ident and ident.is_claimed),
            )
        )
    return out


def _customer_query(
    db: Session,
    *,
    search: str | None = None,
    tariff_type: str | None = None,
    employee_id: str | None = None,
    zone: str | None = None,
    status_: str | None = None,
):
    """Subscribers matching the filters, sorted by name. Search runs in the database."""
    q = db.query(Subscriber).outerjoin(Customer, Customer.customer_id == Subscriber.customer_id)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        meter_match = (
            select(Subscription.subscriber_id)
            .join(Meter, Meter.subscription_id == Subscription.subscription_id)
            .where(or_(func.lower(Meter.serial_number).like(term), func.lower(Meter.meter_id).like(term)))
        )
        q = q.filter(
            or_(
                func.lower(Customer.name).like(term),
                func.lower(Customer.customer_id).like(term),
                func.lower(Customer.phone).like(term),
                func.lower(Subscriber.subscriber_id).like(term),
                Subscriber.subscriber_id.in_(meter_match),
            )
        )
    if tariff_type and tariff_type != "All":
        q = q.filter(Customer.plan == tariff_type)
    if status_ and status_ != "All":
        q = q.filter(Customer.status == status_)
    if employee_id and employee_id != "All":
        assigned = select(EmployeeAssignment.subscriber_id).where(EmployeeAssignment.employee_id == employee_id)
        q = q.filter(Subscriber.subscriber_id.in_(assigned))
    if zone and zone != "All":
        q = q.outerjoin(Zone, Zone.zone_id == Subscriber.zone_id).filter(func.lower(Zone.name) == zone.lower())
    return q.order_by(func.coalesce(Customer.name, Subscriber.subscriber_id), Subscriber.subscriber_id)


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


# --- invoice / payment rows ----------------------------------------------------------
def _invoice_rows(db: Session, invoices: list[Invoice]) -> list[CrmInvoiceOut]:
    if not invoices:
        return []
    ids = [i.invoice_id for i in invoices]
    sub_ids = {i.subscriber_id for i in invoices}
    paid = dict(
        db.query(InvoicePayment.invoice_id, func.sum(InvoicePayment.amount))
        .filter(InvoicePayment.invoice_id.in_(ids))
        .group_by(InvoicePayment.invoice_id)
    )
    reading_ids = [i.reading_id for i in invoices if i.reading_id]
    reading_dates = (
        dict(db.query(MeterReading.reading_id, MeterReading.reading_date).filter(MeterReading.reading_id.in_(reading_ids)))
        if reading_ids
        else {}
    )
    subs = {s.subscriber_id: s for s in db.query(Subscriber).filter(Subscriber.subscriber_id.in_(sub_ids))}
    cust_ids = {s.customer_id for s in subs.values() if s.customer_id}
    customers = (
        {c.customer_id: c for c in db.query(Customer).filter(Customer.customer_id.in_(cust_ids))} if cust_ids else {}
    )
    meter_by_sbn = {
        m.subscription_id: m
        for m in db.query(Meter).filter(Meter.subscription_id.in_({i.subscription_id for i in invoices}))
    }
    names = _staff_names(db, {i.issued_by for i in invoices if i.issued_by})

    out = []
    for inv in invoices:
        sub = subs.get(inv.subscriber_id)
        ident = customers.get(sub.customer_id) if sub and sub.customer_id else None
        meter = meter_by_sbn.get(inv.subscription_id)
        issue = reading_dates.get(inv.reading_id) or inv.billing_period
        due = issue + timedelta(days=DUE_AFTER_DAYS)
        received = paid.get(inv.invoice_id) or 0.0
        out.append(
            CrmInvoiceOut(
                id=inv.invoice_id,
                invoice_number=inv.invoice_id,
                customer_id=inv.subscriber_id,
                customer_name=ident.name if ident else inv.subscriber_id,
                account_no=(sub.customer_id if sub else None) or inv.subscriber_id,
                meter_no=(meter.serial_number or meter.meter_id) if meter else None,
                billing_period=inv.billing_period,
                issue_date=issue,
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
                paid_amount=_round(received),
                status=_invoice_status(inv.total_amount or 0.0, received, due),
                currency=inv.currency or settings.CURRENCY,
                recorded_by=names.get(inv.issued_by, inv.issued_by) if inv.issued_by else None,
                recorded_by_id=inv.issued_by,
            )
        )
    return out


def _payment_rows(db: Session, payments: list[InvoicePayment]) -> list[CrmPaymentOut]:
    if not payments:
        return []
    subs = {
        s.subscriber_id: s
        for s in db.query(Subscriber).filter(Subscriber.subscriber_id.in_({p.subscriber_id for p in payments}))
    }
    cust_ids = {s.customer_id for s in subs.values() if s.customer_id}
    customers = (
        dict(db.query(Customer.customer_id, Customer.name).filter(Customer.customer_id.in_(cust_ids))) if cust_ids else {}
    )
    names = _staff_names(db, {p.collected_by for p in payments if p.collected_by})
    names.setdefault("PORTAL", "Customer portal")
    out = []
    for p in payments:
        sub = subs.get(p.subscriber_id)
        out.append(
            CrmPaymentOut(
                id=p.payment_id,
                receipt_no=p.receipt_no or p.payment_id,
                customer_id=p.subscriber_id,
                customer_name=customers.get(sub.customer_id, p.subscriber_id) if sub and sub.customer_id else p.subscriber_id,
                invoice_id=p.invoice_id,
                invoice_number=p.invoice_id or "General Account Payment",
                amount=_round(p.amount),
                currency=p.currency or settings.CURRENCY,
                payment_method=p.payment_method,
                payment_date=p.payment_date,
                reference_no=p.reference_no,
                recorded_by=names.get(p.collected_by, p.collected_by) if p.collected_by else None,
                notes=p.notes,
            )
        )
    return out


# --- who am I ----------------------------------------------------------------------
@router.get("/me", response_model=CrmMe)
def me(db: Session = Depends(get_db), user=Depends(require_staff)) -> CrmMe:
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


# --- summary (dashboard numbers without loading any list) ---------------------------
@router.get("/summary", response_model=CrmSummary)
def summary(db: Session = Depends(get_db), _=Depends(require_staff)) -> CrmSummary:
    billed = db.query(func.coalesce(func.sum(Invoice.total_amount), 0.0)).scalar() or 0.0
    collected = db.query(func.coalesce(func.sum(InvoicePayment.amount), 0.0)).scalar() or 0.0

    plans = dict(
        db.query(Customer.plan, func.count(Subscriber.subscriber_id))
        .join(Customer, Customer.customer_id == Subscriber.customer_id)
        .group_by(Customer.plan)
    )
    active = (
        db.query(func.count(Subscriber.subscriber_id))
        .outerjoin(Customer, Customer.customer_id == Subscriber.customer_id)
        .filter(or_(Customer.status == "Active", Customer.customer_id.is_(None)))
        .scalar()
        or 0
    )
    paid_per_invoice = (
        select(InvoicePayment.invoice_id, func.sum(InvoicePayment.amount).label("paid"))
        .group_by(InvoicePayment.invoice_id)
        .subquery()
    )
    unpaid = (
        db.query(func.count(Invoice.invoice_id))
        .outerjoin(paid_per_invoice, paid_per_invoice.c.invoice_id == Invoice.invoice_id)
        .filter(Invoice.total_amount - func.coalesce(paid_per_invoice.c.paid, 0.0) > 0.005)
        .scalar()
        or 0
    )
    return CrmSummary(
        total_customers=db.query(func.count(Subscriber.subscriber_id)).scalar() or 0,
        active_customers=active,
        residential_customers=plans.get("Residential", 0),
        commercial_customers=plans.get("Commercial", 0),
        total_employees=db.query(func.count(Employee.employee_id)).scalar() or 0,
        total_billed=_round(billed),
        total_collected=_round(collected),
        outstanding=_round(max(0.0, billed - collected)),
        kwh_billed=_round(db.query(func.coalesce(func.sum(Invoice.units_consumed), 0.0)).scalar() or 0.0),
        invoice_count=db.query(func.count(Invoice.invoice_id)).scalar() or 0,
        unpaid_invoices=unpaid,
        payment_count=db.query(func.count(InvoicePayment.payment_id)).scalar() or 0,
        currency=settings.CURRENCY,
    )


# --- customers ---------------------------------------------------------------------
@router.get("/customers", response_model=list[CrmCustomerOut])
def list_customers(
    mine: bool = Query(False, description="Only the subscribers assigned to the signed-in employee"),
    search: str | None = None,
    limit: int = Query(MAX_PAGE * 10, ge=1, le=MAX_PAGE * 10),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(require_staff),
) -> list[CrmCustomerOut]:
    """Full rows as a plain list (the field app uses this). Prefer /customers/page on the web."""
    q = _customer_query(db, search=search, employee_id=_actor_id(db, user) if mine else None)
    return _customer_rows(db, q.offset(offset).limit(limit).all())


@router.get("/customers/page", response_model=CrmCustomerPage)
def customers_page(
    search: str | None = None,
    tariff_type: str | None = Query(None, alias="tariffType"),
    employee_id: str | None = Query(None, alias="employeeId"),
    zone: str | None = None,
    status_: str | None = Query(None, alias="status"),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=MAX_PAGE),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
) -> CrmCustomerPage:
    """One page of the customer directory, searched and filtered in the database."""
    q = _customer_query(db, search=search, tariff_type=tariff_type, employee_id=employee_id, zone=zone, status_=status_)
    total = q.order_by(None).count()
    rows = _customer_rows(db, q.offset(offset).limit(limit).all())
    return CrmCustomerPage(items=rows, total=total, offset=offset, limit=limit)


@router.get("/customers/options", response_model=list[CrmCustomerOption])
def customer_options(db: Session = Depends(get_db), _=Depends(require_staff)) -> list[CrmCustomerOption]:
    """Every customer as a small row for pickers: three queries, no readings or meters."""
    billed = dict(db.query(Invoice.subscriber_id, func.sum(Invoice.total_amount)).group_by(Invoice.subscriber_id))
    paid = dict(
        db.query(InvoicePayment.subscriber_id, func.sum(InvoicePayment.amount)).group_by(InvoicePayment.subscriber_id)
    )
    assignment = dict(db.query(EmployeeAssignment.subscriber_id, EmployeeAssignment.employee_id))
    rows = (
        db.query(Subscriber.subscriber_id, Subscriber.customer_id, Customer.name, Customer.plan, Customer.status)
        .outerjoin(Customer, Customer.customer_id == Subscriber.customer_id)
        .order_by(func.coalesce(Customer.name, Subscriber.subscriber_id))
        .all()
    )
    return [
        CrmCustomerOption(
            id=r.subscriber_id,
            account_no=r.customer_id or r.subscriber_id,
            name=r.name or r.subscriber_id,
            tariff_type=r.plan or "Residential",
            status=r.status or "Active",
            assigned_employee_id=assignment.get(r.subscriber_id),
            balance=_round(max(0.0, (billed.get(r.subscriber_id) or 0.0) - (paid.get(r.subscriber_id) or 0.0))),
        )
        for r in rows
    ]


@router.get("/customers/{subscriber_id}", response_model=CrmCustomerOut)
def get_customer(subscriber_id: str, db: Session = Depends(get_db), _=Depends(require_staff)):
    return _customer_rows(db, [_get_subscriber(db, subscriber_id)])[0]


@router.post("/customers", response_model=CrmCustomerOut, status_code=status.HTTP_201_CREATED)
def create_customer(
    payload: CrmCustomerCreate, db: Session = Depends(get_db), _=Depends(require_staff)
) -> CrmCustomerOut:
    customer_id = _new_id("CUST")
    email = (payload.email or "").strip().lower() or f"unclaimed.{customer_id.lower()}@voltiq.demo"
    if email_in_use(db, email):
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
    return _customer_rows(db, [db.get(Subscriber, sub_id)])[0]


@router.patch("/customers/{subscriber_id}", response_model=CrmCustomerOut)
def update_customer(
    subscriber_id: str,
    payload: CrmCustomerUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_office),
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
            if email_in_use(db, email, exclude_id=ident.customer_id):
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
    return _customer_rows(db, [sub])[0]


@router.delete("/customers/{subscriber_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(subscriber_id: str, db: Session = Depends(get_db), _=Depends(require_office)):
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


# --- employees -----------------------------------------------------------------------
@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(db: Session = Depends(get_db), _=Depends(require_staff)) -> list[EmployeeOut]:
    counts = dict(
        db.query(EmployeeAssignment.employee_id, func.count(EmployeeAssignment.id))
        .group_by(EmployeeAssignment.employee_id)
    )
    emails = dict(db.query(User.user_id, User.email))
    return [
        _employee_out(e, counts.get(e.employee_id, 0), emails.get(e.account_id))
        for e in db.query(Employee).order_by(Employee.full_name).all()
    ]


@router.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    payload: EmployeeCreate, db: Session = Depends(get_db), user=Depends(require_office)
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
        if email_in_use(db, email):
            raise HTTPException(status.HTTP_409_CONFLICT, "This email is already used by another account")
        # Stage 2: staff sign in from `users`, never from `customers`.
        account = User(
            user_id=_new_id("USR"),
            name=emp.full_name,
            email=email,
            password_hash=hash_password(payload.password),
            role=ACCOUNT_ROLE_FOR[role],
            phone=payload.phone,
            region=payload.zone,
            status="Active",
        )
        db.add(account)
        db.flush()
        emp.account_id = account.user_id

    db.add(emp)
    db.commit()
    return _employee_out(emp)


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_office),
) -> EmployeeOut:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    fields = payload.model_dump(exclude_unset=True)
    account = db.get(User, emp.account_id) if emp.account_id else None

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
def delete_employee(employee_id: str, db: Session = Depends(get_db), user=Depends(require_office)):
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    if emp.account_id == user.customer_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own employee record")
    if emp.role == "admin" and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an administrator can delete an administrator")
    account = db.get(User, emp.account_id) if emp.account_id else None
    db.delete(emp)
    if account is not None:
        db.delete(account)
    db.commit()


@router.put("/employees/{employee_id}/customers", response_model=EmployeeOut)
def assign_customers(
    employee_id: str,
    payload: AssignmentUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_office),
) -> EmployeeOut:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    ids = list(dict.fromkeys(payload.customer_ids))
    known = {s for (s,) in db.query(Subscriber.subscriber_id).filter(Subscriber.subscriber_id.in_(ids))} if ids else set()
    missing = [i for i in ids if i not in known]
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Customer not found: {missing[0]}")
    db.query(EmployeeAssignment).filter(
        or_(EmployeeAssignment.employee_id == employee_id, EmployeeAssignment.subscriber_id.in_(ids))
    ).delete(synchronize_session=False)
    db.add_all(EmployeeAssignment(employee_id=employee_id, subscriber_id=s) for s in ids)
    db.commit()
    return _employee_out(emp, len(ids))


# --- readings -> invoices ---------------------------------------------------------------
@router.post("/readings", response_model=CrmInvoiceOut, status_code=status.HTTP_201_CREATED)
def record_reading(payload: ReadingCreate, db: Session = Depends(get_db), user=Depends(require_staff)) -> CrmInvoiceOut:
    """
    Save a meter reading and issue the invoice it produces, in one step.

    This is what a field employee's phone calls after reading a meter, and what
    "Generate invoice" calls in the office. Since Stage 2 the same invoice also
    appears on the customer's Bills page in the portal.
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
        issued_by=_actor_id(db, user),
    )
    db.add_all([reading, invoice])
    db.flush()
    bill = link_invoice(db, invoice, when)        # Stage 2: the customer sees it too
    db.commit()
    if bill is not None:
        refresh_customer_feeds(db, bill.customer_id)
    return _invoice_rows(db, [invoice])[0]


@router.get("/invoices", response_model=list[CrmInvoiceOut])
def list_invoices(
    customer_id: str | None = Query(None, alias="customerId"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
) -> list[CrmInvoiceOut]:
    """Newest first. A fixed number of queries for any page size."""
    q = db.query(Invoice)
    if customer_id:
        q = q.filter(Invoice.subscriber_id == customer_id)
    invoices = q.order_by(Invoice.billing_period.desc(), Invoice.invoice_id.desc()).offset(offset).limit(limit).all()
    return _invoice_rows(db, invoices)


# --- payments -----------------------------------------------------------------------------
@router.get("/payments", response_model=list[CrmPaymentOut])
def list_payments(
    customer_id: str | None = Query(None, alias="customerId"),
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(require_staff),
) -> list[CrmPaymentOut]:
    q = db.query(InvoicePayment)
    if customer_id:
        q = q.filter(InvoicePayment.subscriber_id == customer_id)
    payments = (
        q.order_by(InvoicePayment.payment_date.desc(), InvoicePayment.payment_id.desc()).offset(offset).limit(limit).all()
    )
    return _payment_rows(db, payments)


@router.post("/payments", response_model=CrmPaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(payload: PaymentCreate, db: Session = Depends(get_db), user=Depends(require_staff)) -> CrmPaymentOut:
    sub = _get_subscriber(db, payload.customer_id)
    invoice = None
    if payload.invoice_id:
        invoice = db.get(Invoice, payload.invoice_id)
        if invoice is None or invoice.subscriber_id != sub.subscriber_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found for this customer")
    else:
        # The oldest invoice that is not fully paid, found in the database.
        paid_per_invoice = (
            select(InvoicePayment.invoice_id, func.sum(InvoicePayment.amount).label("paid"))
            .where(InvoicePayment.subscriber_id == sub.subscriber_id)
            .group_by(InvoicePayment.invoice_id)
            .subquery()
        )
        invoice = (
            db.query(Invoice)
            .outerjoin(paid_per_invoice, paid_per_invoice.c.invoice_id == Invoice.invoice_id)
            .filter(
                and_(
                    Invoice.subscriber_id == sub.subscriber_id,
                    Invoice.total_amount - func.coalesce(paid_per_invoice.c.paid, 0.0) > 0.005,
                )
            )
            .order_by(Invoice.billing_period)
            .first()
        )

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
    db.flush()
    mirrored = mirror_crm_payment(db, payment)   # Stage 2: the portal sees it too
    db.commit()
    if mirrored is not None:
        refresh_customer_feeds(db, mirrored.customer_id)
    return _payment_rows(db, [payment])[0]


# --- tariff ---------------------------------------------------------------------------------
@router.get("/tariff", response_model=TariffOut)
def get_tariff(db: Session = Depends(get_db), _=Depends(require_staff)) -> TariffOut:
    tariff = _current_tariff(db)
    return TariffOut(
        rate_per_kwh=tariff.rate_per_kwh_base if tariff else settings.TARIFF_LBP_PER_KWH,
        fixed_charge=settings.FIXED_CHARGE_PER_INVOICE,
        currency=(tariff.currency if tariff else None) or settings.CURRENCY,
        effective_month=tariff.effective_month if tariff else None,
    )


@router.put("/tariff", response_model=TariffOut)
def set_tariff(payload: TariffUpdate, db: Session = Depends(get_db), user=Depends(require_office)) -> TariffOut:
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
    return get_tariff(db, user)
