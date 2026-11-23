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
        db.add(Customer(customer_id="ADM-T", name="Test Admin", email="admin@example.com",
                        password_hash=hash_password(PASSWORD), role="admin", status="Active"))
        db.add(Customer(customer_id="CUS-T", name="Test Customer", email="cust@example.com",
                        password_hash=hash_password(PASSWORD), role="customer", region="Beirut",
                        status="Active"))
        db.commit()
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
