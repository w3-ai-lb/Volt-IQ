"""
Request and response shapes for the CRM module (/crm).

Field names follow what the CRM web pages and the Flutter field app already
read (camelCase over the wire, through CamelModel), so the screens that were
built against Supabase needed only their data layer swapped.
"""

from datetime import date

from pydantic import Field

from app.schemas.common import CamelModel


# --- Staff -------------------------------------------------------------------
class CrmMe(CamelModel):
    id: str
    account_id: str
    name: str
    email: str
    role: str            # ADMIN | MANAGER | OFFICE_EMPLOYEE  (CRM permission role)
    role_title: str
    account_role: str    # admin | staff | field                (sign-in role)
    zone: str | None = None
    phone: str | None = None


class EmployeeOut(CamelModel):
    id: str
    name: str
    email: str | None = None
    phone: str | None = None
    role: str            # ADMIN | MANAGER | OFFICE_EMPLOYEE
    db_role: str         # admin | office_staff | field_employee
    role_title: str
    department: str | None = None
    zone: str | None = None
    status: str          # Active | Inactive
    can_sign_in: bool
    assigned_customers_count: int = 0


class EmployeeCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    password: str | None = None
    phone: str | None = None
    role: str = "OFFICE_EMPLOYEE"
    role_title: str | None = None
    department: str | None = None
    zone: str | None = None


class EmployeeUpdate(CamelModel):
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    department: str | None = None
    zone: str | None = None
    status: str | None = None


class AssignmentUpdate(CamelModel):
    customer_ids: list[str]


# --- Customers (subscribers) -------------------------------------------------
class CrmCustomerOut(CamelModel):
    id: str                       # subscriber_id
    account_no: str               # customer_id (the number printed on the bill)
    meter_no: str | None = None
    name: str
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tariff_type: str = "Residential"
    zone: str | None = None
    assigned_employee_id: str | None = None
    assigned_employee_name: str = "Unassigned"
    previous_reading: float = 0.0
    current_reading: float = 0.0
    last_reading_date: date | None = None
    status: str = "Active"
    balance: float = 0.0
    outstanding_status: str = "Paid"
    meter_type: str | None = None
    has_portal_access: bool = False


class CrmCustomerCreate(CamelModel):
    name: str = Field(min_length=1, max_length=120)
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tariff_type: str = "Residential"
    zone: str | None = None
    assigned_employee_id: str | None = None
    initial_reading: float = 0.0
    meter_no: str | None = None
    meter_type: str | None = None
    status: str = "Active"


class CrmCustomerUpdate(CamelModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    tariff_type: str | None = None
    zone: str | None = None
    assigned_employee_id: str | None = None
    status: str | None = None
    meter_type: str | None = None


# --- Readings, invoices, payments -----------------------------------------------
class ReadingCreate(CamelModel):
    customer_id: str                          # subscriber_id
    current_reading: float = Field(ge=0)
    previous_reading: float | None = None     # defaults to the last reading on file
    reading_date: date | None = None
    capture_method: str = "manual"            # manual | ocr
    ocr_confidence: float | None = None


class CrmInvoiceOut(CamelModel):
    id: str
    invoice_number: str
    customer_id: str
    customer_name: str
    account_no: str | None = None
    meter_no: str | None = None
    billing_period: date
    issue_date: date
    due_date: date
    previous_reading: float | None = None
    current_reading: float | None = None
    kwh_consumed: float
    tariff_type: str = "Residential"
    rate_applied: float | None = None
    base_charge: float = 0.0
    consumption_charge: float = 0.0
    tax_amount: float = 0.0
    total_amount: float
    paid_amount: float = 0.0
    status: str
    currency: str
    recorded_by: str | None = None
    recorded_by_id: str | None = None


class PaymentCreate(CamelModel):
    customer_id: str
    invoice_id: str | None = None
    amount: float = Field(gt=0)
    payment_method: str = "Cash"
    reference_no: str | None = None
    notes: str | None = None


class CrmPaymentOut(CamelModel):
    id: str
    receipt_no: str
    customer_id: str
    customer_name: str
    invoice_id: str | None = None
    invoice_number: str
    amount: float
    currency: str
    payment_method: str | None = None
    payment_date: date | None = None
    reference_no: str | None = None
    recorded_by: str | None = None
    notes: str | None = None


# --- Tariff ------------------------------------------------------------------
class TariffOut(CamelModel):
    rate_per_kwh: float
    fixed_charge: float
    currency: str
    effective_month: date | None = None


class TariffUpdate(CamelModel):
    rate_per_kwh: float = Field(gt=0)


# --- Stage 2: paging and light lists -------------------------------------------
class CrmCustomerPage(CamelModel):
    items: list[CrmCustomerOut]
    total: int
    offset: int
    limit: int


class CrmCustomerOption(CamelModel):
    """The small row used by pickers (payment, assignment): no readings, no meters."""

    id: str
    account_no: str
    name: str
    tariff_type: str = "Residential"
    status: str = "Active"
    assigned_employee_id: str | None = None
    balance: float = 0.0


class CrmSummary(CamelModel):
    total_customers: int
    active_customers: int
    residential_customers: int
    commercial_customers: int
    total_employees: int
    total_billed: float
    total_collected: float
    outstanding: float
    kwh_billed: float
    invoice_count: int
    unpaid_invoices: int
    payment_count: int
    currency: str
