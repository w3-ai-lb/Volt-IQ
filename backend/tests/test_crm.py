"""
CRM module tests (VoltIQ unified backend).

Runs against a throwaway SQLite database, so it never touches real data:

    cd backend
    python -m pytest tests/test_crm.py -q
"""

from __future__ import annotations

import os
import tempfile

_DB = os.path.join(tempfile.mkdtemp(prefix="voltiq-crm-test-"), "crm.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal, create_all_tables  # noqa: E402
from app.main import app  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.pipeline.crm_seed import seed_crm  # noqa: E402

PASSWORD = "test-pass-1234"


@pytest.fixture(scope="module")
def client() -> TestClient:
    create_all_tables()
    with SessionLocal() as db:
        # The admin is created the OLD way (a login in `customers`), as a
        # database from before Stage 2 would have it. The start-up move below
        # must carry it over to `users`.
        db.add(Customer(customer_id="ADM-T", name="Test Admin", email="admin@example.com",
                        password_hash=hash_password(PASSWORD), role="admin", status="Active"))
        db.add(Customer(customer_id="CUS-T", name="Test Customer", email="cust@example.com",
                        password_hash=hash_password(PASSWORD), role="customer", region="Beirut",
                        status="Active"))
        db.commit()
    from app.core.accounts import move_staff_to_users
    from app.database import engine

    assert move_staff_to_users(engine) == 1
    with SessionLocal() as db:
        seed_crm(db)
    return TestClient(app)


def _login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_customer_cannot_open_crm(client):
    h = _login(client, "cust@example.com")
    assert client.get("/crm/customers", headers=h).status_code == 403


def test_admin_sees_seeded_crm(client):
    h = _login(client, "admin@example.com")
    customers = client.get("/crm/customers", headers=h).json()
    assert len(customers) == 1
    row = customers[0]
    for key in ("id", "accountNo", "meterNo", "name", "assignedEmployeeName", "balance", "currentReading"):
        assert key in row
    assert len(client.get("/crm/employees", headers=h).json()) == 3
    assert len(client.get("/crm/invoices", headers=h).json()) == 3


def test_field_employee_reads_meter_and_collects(client):
    h = _login(client, "field@voltiq.demo", "field1234")
    me = client.get("/crm/me", headers=h).json()
    assert me["accountRole"] == "field"

    mine = client.get("/crm/customers?mine=true", headers=h).json()
    assert len(mine) == 1
    cust = mine[0]

    r = client.post("/crm/readings", headers=h,
                    json={"customerId": cust["id"], "currentReading": cust["currentReading"] + 100})
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["kwhConsumed"] == 100
    assert inv["status"] == "Unpaid"
    assert inv["recordedBy"] == "Omar Fakhoury"

    # A reading lower than the last one is refused.
    bad = client.post("/crm/readings", headers=h, json={"customerId": cust["id"], "currentReading": 1})
    assert bad.status_code == 422

    pay = client.post("/crm/payments", headers=h,
                      json={"customerId": cust["id"], "invoiceId": inv["id"], "amount": inv["totalAmount"]})
    assert pay.status_code == 201, pay.text
    invoices = client.get(f"/crm/invoices?customerId={cust['id']}", headers=h).json()
    assert next(i for i in invoices if i["id"] == inv["id"])["status"] == "Paid"

    # Field staff may not manage employees.
    assert client.post("/crm/employees", headers=h, json={"name": "X"}).status_code == 403


def test_office_manages_customers_and_staff(client):
    h = _login(client, "office@voltiq.demo", "office1234")
    r = client.post("/crm/customers", headers=h, json={
        "name": "New Shop", "phone": "+961 1 000 000", "zone": "Tripoli",
        "tariffType": "Commercial", "initialReading": 500, "assignedEmployeeId": "EMP-0002"})
    assert r.status_code == 201, r.text
    new = r.json()
    assert new["zone"] == "Tripoli" and new["assignedEmployeeName"] == "Omar Fakhoury"

    r = client.patch(f"/crm/customers/{new['id']}", headers=h, json={"address": "Main St"})
    assert r.json()["address"] == "Main St"

    # Office staff cannot create administrators.
    r = client.post("/crm/employees", headers=h, json={"name": "Boss", "role": "ADMIN"})
    assert r.status_code == 403

    r = client.post("/crm/employees", headers=h, json={
        "name": "New Reader", "email": "reader@example.com", "password": "reader-pass-1", "role": "OFFICE_EMPLOYEE"})
    assert r.status_code == 201, r.text
    assert r.json()["canSignIn"] is True
    _login(client, "reader@example.com", "reader-pass-1")

    assert client.delete(f"/crm/customers/{new['id']}", headers=h).status_code == 204


def test_tariff_update_applies_to_new_invoices(client):
    h = _login(client, "admin@example.com")
    r = client.put("/crm/tariff", headers=h, json={"ratePerKwh": 40000})
    assert r.status_code == 200 and r.json()["ratePerKwh"] == 40000
    cust = client.get("/crm/customers", headers=h).json()[0]
    inv = client.post("/crm/readings", headers=h,
                      json={"customerId": cust["id"], "currentReading": cust["currentReading"] + 10}).json()
    assert inv["rateApplied"] == 40000
    assert inv["totalAmount"] == 400000


# --- Stage 2 ----------------------------------------------------------------------
def test_stage2_users_table_holds_staff(client):
    from app.models.user import User

    with SessionLocal() as db:
        # The legacy admin was moved, and the demo staff were created in `users`.
        assert db.get(User, "ADM-T") is not None
        assert db.get(Customer, "ADM-T") is None
        assert db.query(Customer).filter(Customer.role != "customer").count() == 0
        assert db.query(User).count() >= 4

    h = _login(client, "admin@example.com")          # signs in from `users`
    assert client.get("/auth/me", headers=h).json()["role"] == "admin"
    assert client.get("/dashboard/admin", headers=h).status_code == 200

    r = client.post("/crm/employees", headers=h, json={
        "name": "Stage Two", "email": "s2@example.com", "password": "stage-two-pass", "role": "MANAGER"})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == "s2@example.com").count() == 1
        assert db.query(Customer).filter(Customer.email == "s2@example.com").count() == 0

    # One email, one account, across both tables.
    clash = client.post("/crm/employees", headers=h, json={
        "name": "Dup", "email": "cust@example.com", "password": "another-pass-1", "role": "MANAGER"})
    assert clash.status_code == 409

    # Staff cannot write customer-only records.
    assert client.post("/chat/message", headers=h, json={"message": "hi"}).status_code == 403


def test_stage2_reading_appears_in_customer_portal(client):
    staff = _login(client, "field@voltiq.demo", "field1234")
    cust = _login(client, "cust@example.com")
    sub = client.get("/crm/customers?mine=true", headers=staff).json()[0]
    before = {b["id"] for b in client.get("/bills", headers=cust).json()}

    inv = client.post("/crm/readings", headers=staff,
                      json={"customerId": sub["id"], "currentReading": sub["currentReading"] + 50}).json()
    bills = client.get("/bills", headers=cust).json()
    new = [b for b in bills if b["id"] not in before]
    assert len(new) == 1 and round(new[0]["amount"]) == round(inv["totalAmount"])

    # The office records cash: the customer sees the payment and a paid bill.
    pay = client.post("/crm/payments", headers=staff,
                      json={"customerId": sub["id"], "invoiceId": inv["id"], "amount": inv["totalAmount"]})
    assert pay.status_code == 201, pay.text
    bill = next(b for b in client.get("/bills", headers=cust).json() if b["id"] == new[0]["id"])
    assert bill["status"] == "Paid"
    assert any(round(p["amount"]) == round(inv["totalAmount"]) for p in client.get("/payments", headers=cust).json())


def test_stage2_portal_payment_settles_crm_invoice(client):
    staff = _login(client, "office@voltiq.demo", "office1234")
    cust = _login(client, "cust@example.com")
    sub = client.get("/crm/customers", headers=staff).json()[0]
    inv = client.post("/crm/readings", headers=staff,
                      json={"customerId": sub["id"], "currentReading": sub["currentReading"] + 20}).json()
    bill = next(b for b in client.get("/bills", headers=cust).json() if b["id"] == f"BILL-{inv['id']}")

    r = client.post(f"/bills/{bill['id']}/pay", headers=cust, json={"method": "OMT"})
    assert r.status_code == 201, r.text
    crm_inv = next(i for i in client.get(f"/crm/invoices?customerId={sub['id']}", headers=staff).json()
                   if i["id"] == inv["id"])
    assert crm_inv["status"] == "Paid"
    portal_pay = next(p for p in client.get("/crm/payments", headers=staff).json() if p["invoiceId"] == inv["id"])
    assert portal_pay["recordedBy"] == "Customer portal"


def test_stage2_lists_use_a_fixed_number_of_queries(client):
    """The customer list must not run one query per customer (Stage 1 did)."""
    from sqlalchemy import event

    from app.database import engine

    h = _login(client, "office@voltiq.demo", "office1234")
    for n in range(12):
        client.post("/crm/customers", headers=h, json={"name": f"Bulk {n}", "zone": "Beirut", "initialReading": 1})

    counted = []

    def count(*_):
        counted.append(1)

    def queries(url):
        counted.clear()
        event.listen(engine, "before_cursor_execute", count)
        try:
            assert client.get(url, headers=h).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(counted)

    small = queries("/crm/customers/page?limit=2")
    large = queries("/crm/customers/page?limit=200")
    # Same bound for 2 rows or 200 (one optional query, employee names, runs
    # only when the page has assigned customers). Stage 1 needed 1 query per row.
    assert large <= small + 1 and large <= 15, (small, large)

    page = client.get("/crm/customers/page?search=bulk 1&limit=5", headers=h).json()
    assert page["total"] == 3 and all("Bulk 1" in c["name"] for c in page["items"])  # Bulk 1, 10, 11
    summary = client.get("/crm/summary", headers=h).json()
    assert summary["totalCustomers"] >= 13 and "unpaidInvoices" in summary
    assert len(client.get("/crm/customers/options", headers=h).json()) == summary["totalCustomers"]
