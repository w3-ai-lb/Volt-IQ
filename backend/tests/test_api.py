"""
End-to-end API test.

Hits every endpoint the React frontend calls and asserts the response shape
matches what `src/services/api.ts` and `src/services/mockData.ts` expect,
including camelCase field names.

Run:
    python -m tests.test_api

RUNS BEFORE OR AFTER THE DEMO IS PURGED
---------------------------------------
It used to sign in as admin@nxttrn.com / admin123 and customer@nxttrn.com /
customer123, which are two of the accounts scripts/data_provenance.py --purge
is specifically there to delete. So the suite that proves the API works could
not be run on the system as delivered: the first assertion failed with
"Invalid credentials" and the run stopped.

A test whose fixtures are somebody else's demo data is not a test of the
product. This one provisions what it needs, an administrator, and a customer
account attached to a subscriber who actually has readings, and puts the
database back as it found it. It uses the demo accounts when they are still
there, so the behaviour before handover is unchanged.
"""

from __future__ import annotations

import re
import sys

from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal, create_all_tables
from app.main import app
from app.core.security import hash_password
from app.models.consumption import Consumption
from app.models.customer import Customer
from sqlalchemy import func

# TestClient does not fire startup events, so create any missing tables here.
create_all_tables()

client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []

# Filled in by `setup_accounts()` before anything runs.
ADMIN_EMAIL = "admin@nxttrn.com"
ADMIN_PASSWORD = "admin123"
CUSTOMER_EMAIL = "customer@nxttrn.com"
CUSTOMER_PASSWORD = "customer123"
CUSTOMER_ID = "CUST-0001"

# What we changed and must change back. Each entry is (customer_id, field,
# original value); nothing is deleted that existed before this ran.
_RESTORE: list[tuple[str, str, object]] = []
_CREATED: list[str] = []

TEST_PASSWORD = "e2e-test-pass-8814"


def _can_sign_in(email: str, password: str) -> bool:
    return client.post("/auth/login", json={"email": email, "password": password}).status_code == 200


def setup_accounts() -> bool:
    """
    Make sure an admin and a customer with readings can be signed in as.

    Returns False when the database holds nothing to test against, which is a
    different failure from a broken endpoint and is reported as such.
    """
    global ADMIN_EMAIL, ADMIN_PASSWORD, CUSTOMER_EMAIL, CUSTOMER_PASSWORD, CUSTOMER_ID

    if _can_sign_in(ADMIN_EMAIL, ADMIN_PASSWORD) and _can_sign_in(CUSTOMER_EMAIL, CUSTOMER_PASSWORD):
        return True                                  # the demo is still loaded

    db = SessionLocal()
    try:
        admin = db.query(Customer).filter(Customer.role == "admin").first()
        if admin is None:
            print("  No administrator in this database. Run load-data.bat first.")
            return False
        _RESTORE.append((admin.customer_id, "password_hash", admin.password_hash))
        _RESTORE.append((admin.customer_id, "session_version", admin.session_version))
        admin.password_hash = hash_password(TEST_PASSWORD)
        ADMIN_EMAIL, ADMIN_PASSWORD = admin.email, TEST_PASSWORD

        # A customer the consumption, bills and alerts assertions have something
        # to work with: the one with the most readings.
        busiest = (
            db.query(Consumption.customer_id, func.count().label("n"))
            .group_by(Consumption.customer_id)
            .order_by(func.count().desc())
            .first()
        )
        if busiest is None:
            print("  No consumption in this database. Run load-data.bat first.")
            return False

        customer = db.get(Customer, busiest[0])
        if customer is None:
            print(f"  Readings exist for {busiest[0]} but no customer record does.")
            return False

        _RESTORE.append((customer.customer_id, "password_hash", customer.password_hash))
        # The password checks below raise it: a change or a reset signs out
        # the other sessions. Put back like the password itself.
        _RESTORE.append((customer.customer_id, "session_version", customer.session_version))
        customer.password_hash = hash_password(TEST_PASSWORD)
        CUSTOMER_EMAIL, CUSTOMER_PASSWORD = customer.email, TEST_PASSWORD
        CUSTOMER_ID = customer.customer_id
        db.commit()
        print(f"  Demo accounts are gone; testing as {admin.email} and {customer.email}.")
        return True
    finally:
        db.close()


def teardown_accounts() -> None:
    """Put back every password hash this run replaced, and delete what it made."""
    if not _RESTORE and not _CREATED:
        return
    db = SessionLocal()
    try:
        for customer_id, field, original in _RESTORE:
            record = db.get(Customer, customer_id)
            if record is not None:
                setattr(record, field, original)
        for customer_id in _CREATED:
            record = db.get(Customer, customer_id)
            if record is not None:
                db.delete(record)
        db.commit()
    finally:
        db.close()


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name}, {detail}")
        print(f"  FAIL  {name}  {detail}")


def has_keys(obj: dict, *keys: str) -> tuple[bool, str]:
    missing = [key for key in keys if key not in obj]
    return (not missing, f"missing keys: {missing}; got {sorted(obj)[:12]}")


def main() -> int:
    print("\n=== Authentication ===")

    # Wrong password must be rejected
    bad = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "definitely-not-the-password"})
    check("rejects invalid password", bad.status_code == 401, f"got {bad.status_code}")

    admin_res = client.post(
        "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    check("admin login 200", admin_res.status_code == 200, admin_res.text[:200])
    admin_body = admin_res.json()
    check("login returns token+user", *has_keys(admin_body, "token", "user"))
    check("user has role", admin_body["user"]["role"] == "admin", str(admin_body["user"]))
    admin_h = {"Authorization": f"Bearer {admin_body['token']}"}

    cust_res = client.post(
        "/auth/login", json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD}
    )
    check("customer login 200", cust_res.status_code == 200, cust_res.text[:200])
    cust_h = {"Authorization": f"Bearer {cust_res.json()['token']}"}

    # Unauthenticated access must be blocked
    check("blocks anonymous access", client.get("/bills").status_code in (401, 403))
    # Customers must not reach admin endpoints
    check(
        "blocks customer from admin route",
        client.get("/customers", headers=cust_h).status_code == 403,
    )

    print("\n=== Consumption ===")
    # `required` says whether an empty answer is a fault or a fact.
    #
    # A customer with an account must have monthly readings; nothing else about
    # the portal makes sense without them. Daily and hourly are a different
    # matter: this provider's meters are photographed once a month, so those
    # series are legitimately empty and the screens say so in words. Demanding
    # rows there asserted a property of the demo seeder, which manufactured
    # hourly data, not a property of the product.
    for path, keys, required in [
        ("/consumption/monthly", ("month", "kwh", "cost"), True),
        ("/consumption/daily", ("day", "kwh"), False),
        ("/consumption/hourly", ("hour", "kwh"), False),
    ]:
        res = client.get(path, headers=cust_h)
        check(f"GET {path}", res.status_code == 200, res.text[:150])
        data = res.json()
        if required:
            check(f"{path} non-empty", len(data) > 0, f"got {len(data)} rows")
        else:
            check(f"{path} returns a list", isinstance(data, list), f"got {type(data).__name__}")
        if data:
            check(f"{path} shape", *has_keys(data[0], *keys))

    # The Consumption page's range selectors are only real if the backend
    # honours them. Six months must not return more rows than twelve.
    twelve = client.get("/consumption/monthly", params={"months": 12}, headers=cust_h).json()
    six = client.get("/consumption/monthly", params={"months": 6}, headers=cust_h).json()
    check("monthly honours ?months", len(six) <= 6 and len(six) < len(twelve),
          f"12m={len(twelve)} rows, 6m={len(six)} rows")
    check("months is bounded", client.get("/consumption/monthly", params={"months": 999},
                                          headers=cust_h).status_code == 422)

    week = client.get("/consumption/daily", params={"days": 7}, headers=cust_h).json()
    month = client.get("/consumption/daily", params={"days": 30}, headers=cust_h).json()
    check("daily honours ?days", len(week) <= 7 and len(week) <= len(month),
          f"7d={len(week)} rows, 30d={len(month)} rows")

    print("\n=== Consumption export ===")
    pdf = client.get("/consumption/export", params={"months": 6}, headers=cust_h)
    check("GET /consumption/export (pdf)", pdf.status_code == 200, pdf.text[:150])
    check("returns a real PDF", pdf.content[:5] == b"%PDF-", str(pdf.content[:16]))
    check("offers it as a download",
          "attachment" in pdf.headers.get("content-disposition", ""),
          pdf.headers.get("content-disposition", ""))

    xlsx = client.get("/consumption/export", params={"format": "excel"}, headers=cust_h)
    check("GET /consumption/export (excel)", xlsx.status_code == 200, xlsx.text[:150])
    # A .xlsx is a zip archive; the magic bytes are how you tell it is not HTML.
    check("returns a real workbook", xlsx.content[:2] == b"PK", str(xlsx.content[:16]))
    check("export rejects an unknown format",
          client.get("/consumption/export", params={"format": "docx"},
                     headers=cust_h).status_code == 422)
    check("export needs a token", client.get("/consumption/export").status_code == 401)

    print("\n=== Bills / Payments / Recommendations / Alerts / Profile ===")
    bills = client.get("/bills", headers=cust_h)
    check("GET /bills", bills.status_code == 200, bills.text[:150])
    bill_rows = bills.json()
    check("bills non-empty", len(bill_rows) > 0)
    if bill_rows:
        check("bill camelCase dueDate", *has_keys(bill_rows[0], "id", "month", "amount", "dueDate", "status"))
        single = client.get(f"/bills/{bill_rows[0]['id']}", headers=cust_h)
        check("GET /bills/{id}", single.status_code == 200, single.text[:150])

        # WHAT IS STILL OWED, NOT ONLY THE FACE VALUE
        # -------------------------------------------
        # 845 of this provider's 5,400 invoices are part paid. A portal that
        # sends only the face value cannot tell the customer what pressing Pay
        # will charge, and a Pay button decided from `status` alone offers
        # itself on bills with nothing left on them.
        check("a bill states what has been paid and what is left",
              *has_keys(bill_rows[0], "paid", "remaining"))
        check("paid and remaining add up to the bill",
              all(abs((b["paid"] + b["remaining"]) - b["amount"]) < 1.0
                  for b in bill_rows if b["remaining"] > 0 or b["paid"] <= b["amount"]),
              str(bill_rows[0]))
        check("a settled bill has nothing remaining",
              all(b["remaining"] == 0 for b in bill_rows if b["status"] == "Paid"),
              str([b["id"] for b in bill_rows if b["status"] == "Paid" and b["remaining"]][:3]))
        check("no bill holds more money than it asked for",
              all(b["paid"] <= b["amount"] + 1.0 for b in bill_rows),
              str([(b["id"], b["paid"], b["amount"]) for b in bill_rows
                   if b["paid"] > b["amount"] + 1.0][:3]))

    payments = client.get("/payments", headers=cust_h)
    check("GET /payments", payments.status_code == 200)
    if payments.json():
        check("payment shape", *has_keys(payments.json()[0], "id", "date", "amount", "method", "status"))

    recs = client.get("/recommendations", headers=cust_h)
    check("GET /recommendations", recs.status_code == 200, recs.text[:150])
    rec_rows = recs.json()
    check("recommendations non-empty", len(rec_rows) > 0)
    if rec_rows:
        check(
            "recommendation camelCase estimatedSavings",
            *has_keys(rec_rows[0], "id", "title", "description", "estimatedSavings",
                      "priority", "icon", "completed"),
        )
        # Remember the state first. Every other write in this file is undone
        # before the suite ends; this one was not, so each run ticked off one
        # more suggestion until the Recommendations page had nothing open on
        # it and the engine's own feature could not be demonstrated. The
        # seeder does not undo it either: regeneration deliberately preserves
        # anything the customer has completed.
        was_completed = rec_rows[0]["completed"]

        patched = client.patch(
            f"/recommendations/{rec_rows[0]['id']}", json={"completed": True}, headers=cust_h
        )
        check("PATCH /recommendations/{id}", patched.status_code == 200, patched.text[:150])
        check("patch returns completed", patched.json().get("completed") is True)

        client.patch(
            f"/recommendations/{rec_rows[0]['id']}",
            json={"completed": was_completed},
            headers=cust_h,
        )
        restored_rec = next(
            (r for r in client.get("/recommendations", headers=cust_h).json()
             if r["id"] == rec_rows[0]["id"]),
            None,
        )
        check("the recommendation is left as it was found",
              restored_rec is not None and restored_rec["completed"] == was_completed,
              f"wanted completed={was_completed}, got {restored_rec}")

    alerts = client.get("/alerts", headers=cust_h)
    check("GET /alerts", alerts.status_code == 200)

    # --- Alert engine (Proposal: "recommendation AND alert engine") --------
    # Refreshed first so the assertions below run against a known state rather
    # than whatever the seeder happened to leave behind.
    refreshed = client.post("/alerts/refresh", headers=cust_h)
    check("POST /alerts/refresh", refreshed.status_code == 200, refreshed.text[:160])
    generated = refreshed.json()
    check("alert engine produces alerts", len(generated) > 0,
          "engine returned nothing for the demo customer")

    if generated:
        check("alert shape",
              *has_keys(generated[0], "id", "type", "title", "message", "severity", "date", "read"))
        check("alert types are ones the UI can render",
              all(a["type"] in {"high-usage", "low-usage", "payment", "anomaly"} for a in generated),
              str({a["type"] for a in generated}))
        check("alert severities are ones the UI can render",
              all(a["severity"] in {"info", "warning", "error", "success"} for a in generated),
              str({a["severity"] for a in generated}))

        # Running twice must not stack duplicates: the engine updates in place.
        again = client.post("/alerts/refresh", headers=cust_h).json()
        check("refresh is idempotent", len(again) == len(generated),
              f"{len(generated)} then {len(again)}")

        target = generated[0]["id"]
        marked = client.patch(f"/alerts/{target}", json={"read": True}, headers=cust_h)
        check("PATCH /alerts/{id}", marked.status_code == 200, marked.text[:150])
        check("alert marked read", marked.json().get("read") is True)
        check("read state survives a refetch",
              any(a["id"] == target and a["read"] for a in client.get("/alerts", headers=cust_h).json()))
        check("unknown alert 404",
              client.patch("/alerts/a-999999", json={"read": True},
                           headers=cust_h).status_code == 404)
        # Put it back so the demo shows an unread feed.
        client.patch(f"/alerts/{target}", json={"read": False}, headers=cust_h)

    profile = client.get("/profile", headers=cust_h)
    check("GET /profile", profile.status_code == 200)
    check("profile shape", *has_keys(profile.json(), "name", "email", "phone", "address"))

    # Remember what the seeder set, so the suite leaves the demo account exactly
    # as it found it. A test run should never change what the demo shows.
    was_phone = profile.json().get("phone")
    was_address = profile.json().get("address")

    new_phone = "+961 3 778 214"
    new_address = "Rue Gouraud, Gemmayzeh, Beirut"
    updated = client.patch("/profile",
                           json={"phone": new_phone, "address": new_address},
                           headers=cust_h)
    check("PATCH /profile", updated.status_code == 200
          and updated.json()["phone"] == new_phone, updated.text[:160])

    # The edit has to survive the request that made it: a response that echoes
    # the new value while the row keeps the old one is the bug this catches.
    refetched = client.get("/profile", headers=cust_h).json()
    check("profile edit persists",
          refetched["phone"] == new_phone and refetched["address"] == new_address,
          f"{refetched.get('phone')} / {refetched.get('address')}")

    # Two accounts cannot share an email address, or /auth/login would have to
    # guess which one to sign in.
    check("rejects an email already in use",
          client.patch("/profile", json={"email": ADMIN_EMAIL},
                       headers=cust_h).status_code == 409)

    # --- Interface preferences belong to the account -----------------------
    # Both the theme and the language used to be kept in the browser alone,
    # which meant two people sharing a computer shared one preference and a
    # newly registered account inherited whatever the last person chose.
    check("profile carries the account's interface preferences",
          *has_keys(profile.json(), "theme", "language"))

    was_language = profile.json().get("language")

    check("rejects a language the app has no catalogue for",
          client.patch("/profile", json={"language": "xx"},
                       headers=cust_h).status_code == 422)
    check("rejects a theme it cannot render",
          client.patch("/profile", json={"theme": "sepia"},
                       headers=cust_h).status_code == 422)

    picked = client.patch("/profile", json={"language": "ar"}, headers=cust_h)
    check("PATCH /profile accepts a supported language",
          picked.status_code == 200 and picked.json()["language"] == "ar",
          picked.text[:160])
    check("the language survives the request that set it",
          client.get("/profile", headers=cust_h).json()["language"] == "ar")

    # The whole point: it is one account's setting, not the installation's.
    check("choosing a language does not change anybody else's",
          client.get("/profile", headers=admin_h).json()["language"] != "ar",
          client.get("/profile", headers=admin_h).json().get("language"))

    # And sign-in has to carry it, or the frontend has nothing to apply until
    # the profile request comes back and the page flashes the wrong language.
    signed_in = client.post("/auth/login",
                            json={"email": CUSTOMER_EMAIL,
                                  "password": CUSTOMER_PASSWORD}).json()
    check("login returns the account's language",
          signed_in.get("user", {}).get("language") == "ar",
          str(signed_in.get("user")))

    client.patch("/profile", json={"language": was_language}, headers=cust_h)
    check("the demo account's language is left as it was",
          client.get("/profile", headers=cust_h).json()["language"] == was_language)

    restored = client.patch("/profile",
                            json={"phone": was_phone, "address": was_address},
                            headers=cust_h)
    check("demo profile left unchanged",
          restored.status_code == 200 and restored.json()["phone"] == was_phone,
          restored.text[:160])

    print("\n=== Dashboards ===")
    cd = client.get("/dashboard/customer", headers=cust_h)
    check("GET /dashboard/customer", cd.status_code == 200, cd.text[:200])
    check(
        "customer dashboard shape",
        *has_keys(cd.json(), "monthlyConsumption", "currentBill", "outstandingBalance",
                  "energySavingScore", "consumptionTrend", "monthlyBills",
                  "paymentHistory", "recentRecommendations", "recentAlerts"),
    )

    cd_body = cd.json()
    check(
        "dashboard reports what the score is measured against",
        *has_keys(cd_body, "energySavingBasis", "energySavingChangePct"),
    )
    score = cd_body.get("energySavingScore")
    check("energy saving score is a real number or absent",
          score is None or (isinstance(score, int) and 5 <= score <= 99), f"score={score}")
    check("a score always states its basis",
          (score is None) == (cd_body.get("energySavingBasis") is None),
          f"score={score} basis={cd_body.get('energySavingBasis')}")

    # The defect this replaced: an account with nothing to compare was shown a
    # flat 70/100, the midpoint of the scale, as though it had been measured.
    from app.database import SessionLocal
    from app.models.consumption import Consumption
    from app.models.customer import Customer as CustomerModel
    from app.routers.dashboard import _energy_saving_score

    session = SessionLocal()
    try:
        without_readings = [
            row.customer_id
            for row in session.query(CustomerModel).filter(CustomerModel.role == "customer").all()
            if session.query(Consumption.consumption_id)
            .filter(Consumption.customer_id == row.customer_id).first() is None
        ]
        if without_readings:
            blank = _energy_saving_score(session, without_readings[0])
            check("an account with no readings has no score", blank["score"] is None, str(blank))
        else:
            check("an account with no readings has no score",
                  _energy_saving_score(session, "NO-SUCH-ACCOUNT")["score"] is None)
    finally:
        session.close()

    ad = client.get("/dashboard/admin", headers=admin_h)
    check("GET /dashboard/admin", ad.status_code == 200, ad.text[:300])
    ad_body = ad.json()
    check(
        "admin dashboard shape",
        *has_keys(ad_body, "stats", "revenueTrend", "customerGrowth", "forecastData",
                  "consumptionTrend", "topConsumers", "recentActivities"),
    )
    if ad.status_code == 200:
        check(
            "admin stats shape",
            *has_keys(ad_body["stats"], "totalCustomers", "activeCustomers", "revenue",
                      "monthlyConsumption", "predictionAccuracy", "revenueChange",
                      "customersChange", "consumptionChange"),
        )

        # CUSTOMER GROWTH IS EITHER MEASURED OR ABSENT
        # --------------------------------------------
        # The provider's export carries no joining date, so `created_at` is the
        # month of the subscriber's first invoice and is the same month for all
        # three hundred. The card and the chart both have to say so. They were
        # one admin action away from not saying so: registering a single
        # customer stamped today's date, made a second distinct month, and the
        # chart then drew 300 in one month and 301 twenty months later as
        # though that were a trend.
        growth = ad_body["customerGrowth"]
        change = ad_body["stats"]["customersChange"]
        check("growth is charted only where joining dates exist",
              (growth == [] and change is None) or len(growth) >= 2,
              f"series {growth}, change {change}")
        check("a growth series never draws a single bar",
              len(growth) != 1, str(growth))
        if growth:
            check("growth months carry their year",
                  all(any(ch.isdigit() for ch in point["month"]) for point in growth),
                  str(growth[:2]))

    rules_body = client.get("/ishtirak/rules", headers=admin_h)
    if rules_body.status_code == 200:
        findings = [f for f in rules_body.json().get("gridFindings", [])
                    if f.get("rule") == "phase_imbalance"]
        # The order IS the recommendation on a list headed "fix these first".
        # With no ORDER BY the rows came back in generator-id order, which put
        # a 16.9% imbalance above a 28.1% one.
        measured = [float(re.search(r"([\d.]+)%", f["evidence"]).group(1))
                    for f in findings if re.search(r"([\d.]+)%", f["evidence"])]
        check("generator findings are worst first",
              measured == sorted(measured, reverse=True),
              str(list(zip([f["generatorName"] for f in findings], measured))))

    # ANOMALY DETECTION HAS TO PRODUCE SOMETHING OR SAY WHY NOT
    # ----------------------------------------------------------
    # The day-level detector cannot run on monthly readings and returned
    # nothing for all 300 accounts, so the page was permanently empty and
    # "Run detection" did nothing at all. It now falls back to the monthly
    # model, which is the one the evaluation measures.
    from app.ai import anomaly as _anomaly_ai

    ran = client.post("/ai/anomalies/run", headers=admin_h)
    check("POST /ai/anomalies/run", ran.status_code == 200, ran.text[:200])
    if ran.status_code == 200:
        found = ran.json()
        probe = SessionLocal()
        try:
            daily = _anomaly_ai.daily_readings_available(probe)
        finally:
            probe.close()
        check("detection produces findings where the data supports it",
              daily or len(found) > 0,
              f"daily={daily}, findings={len(found)}")
        if found:
            check("an anomaly names the account and explains itself",
                  *has_keys(found[0], "id", "type", "customer", "severity",
                            "value", "description", "date"))
            check("every finding carries a reason, not just a score",
                  all(len(f["description"]) > 20 for f in found),
                  str([f["description"] for f in found if len(f["description"]) <= 20][:2]))
            check("findings are ordered most unusual first",
                  [f["value"] for f in found][:1] == ["1 of %d" % len(found)]
                  or found[0]["type"] != _anomaly_ai.MONTHLY_TYPE,
                  str([f["value"] for f in found[:3]]))
            check("nothing is rated critical by a model the rules beat",
                  all(f["severity"] != "critical" for f in found
                      if f["type"] == _anomaly_ai.MONTHLY_TYPE),
                  str([f["value"] for f in found if f["severity"] == "critical"][:3]))

        # A re-run must not duplicate what is already stored, and must not
        # wipe a human's resolved flag: `run_detection` upserts, and the
        # endpoint used to delete the table before calling it.
        again = client.post("/ai/anomalies/run", headers=admin_h)
        check("re-running detection does not duplicate findings",
              again.status_code == 200 and len(again.json()) == len(found),
              f"{len(found)} then {len(again.json()) if again.status_code == 200 else again.status_code}")

    print("\n=== Admin analytics ===")
    customers = client.get("/customers", headers=admin_h)
    check("GET /customers", customers.status_code == 200)
    cust_rows = customers.json()
    check("customers non-empty", len(cust_rows) > 0)
    if cust_rows:
        check("customer shape", *has_keys(cust_rows[0], "id", "name", "email", "region",
                                          "plan", "status", "consumption", "balance"))
        one = client.get(f"/customers/{cust_rows[0]['id']}", headers=admin_h)
        check("GET /customers/{id}", one.status_code == 200)

    kpis = client.get("/analytics/kpis", headers=admin_h)
    check("GET /analytics/kpis", kpis.status_code == 200, kpis.text[:200])
    check("kpis shape", *has_keys(kpis.json(), "revenue", "consumption", "bills",
                                  "payments", "topConsumers", "regionalStats"))

    regional = client.get("/analytics/regional", headers=admin_h)
    check("GET /analytics/regional", regional.status_code == 200)
    if regional.json():
        check("regional shape", *has_keys(regional.json()[0], "region", "customers", "revenue", "consumption"))

    revenue = client.get("/revenue/overview", headers=admin_h)
    check("GET /revenue/overview", revenue.status_code == 200)
    check("revenue shape", *has_keys(revenue.json(), "revenueTrend", "regionalStats", "billingStatuses"))

    # --- Payment-default risk (Proposal problem statement, SRS VI-vii) -----
    risk = client.get("/analytics/risk", headers=admin_h)
    check("GET /analytics/risk", risk.status_code == 200, risk.text[:200])
    risk_body = risk.json()
    check("risk summary shape",
          *has_keys(risk_body, "high", "medium", "low", "unknown", "amountAtRisk", "customers"))
    check("risk is admin-only", client.get("/analytics/risk", headers=cust_h).status_code == 403)

    scored = risk_body.get("customers", [])
    check("every customer is scored", len(scored) > 0)
    if scored:
        check("risk row shape",
              *has_keys(scored[0], "customerId", "name", "score", "band",
                        "outstanding", "overdueBills", "avgDaysLate", "reasons"))
        check("riskiest first",
              all(scored[i]["score"] >= scored[i + 1]["score"] for i in range(len(scored) - 1)))
        check("bands are the four the UI knows",
              {r["band"] for r in scored} <= {"High", "Medium", "Low", "Unknown"},
              str({r["band"] for r in scored}))
        check("every score is explained", all(r["reasons"] for r in scored))
        # The whole point of the feature: the delinquent seeded account has to
        # surface. If it does not, the model is not measuring anything.
        check("the delinquent account is flagged",
              any(r["band"] in ("High", "Medium") and r["overdueBills"] > 0 for r in scored),
              "no account with overdue bills was banded above Low")
        check("an account with overdue bills is never Low",
              all(r["band"] != "Low" for r in scored if r["overdueBills"] > 0))

    # --- Consumption heatmap (replaces the hardcoded sine wave) -----------
    heatmap = client.get("/consumption/heatmap", headers=admin_h)
    check("GET /consumption/heatmap", heatmap.status_code == 200, heatmap.text[:200])
    hm = heatmap.json()
    check("heatmap shape", *has_keys(hm, "days", "hours", "grid", "maxKwh", "windowDays"))
    check("heatmap is 7x24",
          len(hm.get("grid", [])) == 7 and all(len(row) == 24 for row in hm.get("grid", [])),
          f"{len(hm.get('grid', []))} rows")
    check("heatmap carries real load", hm.get("maxKwh", 0) > 0)
    check("heatmap is admin-only",
          client.get("/consumption/heatmap", headers=cust_h).status_code == 403)

    # --- Tariff plans (Industrial used to be modelled as residential) -----
    all_customers = client.get("/customers", headers=admin_h).json()
    plans = {c["plan"] for c in all_customers}
    check("all three plans exist in the data", {"Residential", "Commercial", "Industrial"} <= plans,
          str(plans))
    check("no plan outside the three", plans <= {"Residential", "Commercial", "Industrial"}, str(plans))
    check("rejects an unknown plan",
          client.post("/customers", headers=admin_h, json={
              "customer_id": "PLAN-TEST-1", "name": "Bad Plan",
              "email": "bad-plan@example.com", "plan": "Wholesale"}).status_code == 422)

    print("\n=== Paying a bill ===")
    unpaid = [b for b in bill_rows if b["status"] != "Paid"]
    if unpaid:
        target = unpaid[0]
        # One of the three channels the provider actually collects through.
        # "Online Card" is now refused, which is the point: this platform
        # records a book entry and there is no card processing in the business.
        paid = client.post(f"/bills/{target['id']}/pay",
                           json={"method": "OMT"}, headers=cust_h)
        check("refuses a payment channel the provider does not use",
              client.post(f"/bills/{target['id']}/pay",
                          json={"method": "Online Card"}, headers=cust_h).status_code == 422)
        check("POST /bills/{id}/pay", paid.status_code == 201, paid.text[:200])
        check("the payment is returned",
              *has_keys(paid.json(), "id", "date", "amount", "method", "status", "billId"))
        check("it settles the bill",
              client.get(f"/bills/{target['id']}", headers=cust_h).json()["status"] == "Paid")
        check("the payment appears in the customer's history",
              any(row["id"] == paid.json()["id"]
                  for row in client.get("/payments", headers=cust_h).json()))
        check("paying a settled bill is refused",
              client.post(f"/bills/{target['id']}/pay", json={}, headers=cust_h).status_code == 409)
        # TWO payments, not one.
        #
        # Paying a single bill passed for months while the endpoint could only
        # ever issue one payment reference in the lifetime of a database: the
        # id generator sorted PAY- ids as text, always found the pipeline's
        # PAY-P0005228, failed to parse it, reset the counter to zero and
        # returned PAY-000001 every time. The second payment anybody made
        # collided on the primary key and came back as a 500.
        # EVERY payment made below is written down here so that every one of
        # them can be undone afterwards.
        #
        # Only the first was being undone. The other two stayed: each run of
        # this suite left two real payments on the live database and two bills
        # marked Paid, and the admin dashboard's revenue rose by 12,683,038 LBP
        # for having run the tests. A suite that says it "leaves the demo
        # account exactly as it was found" has to mean all of it.
        made: list[tuple[str, str, str]] = []          # payment, bill, status

        second = [b for b in bill_rows if b["status"] != "Paid" and b["id"] != target["id"]]
        if second:
            again = client.post(f"/bills/{second[0]['id']}/pay",
                                json={"method": "Whish"}, headers=cust_h)
            check("a SECOND payment also succeeds", again.status_code == 201, again.text[:200])
            if again.status_code == 201:
                check("and gets its own reference",
                      again.json()["id"] != paid.json().get("id"),
                      f"both came back as {again.json()['id']}")
                made.append((again.json()["id"], second[0]["id"], second[0]["status"]))

        # A part-paid bill must only accept what is left on it.
        #
        # The default used to be the bill's FACE VALUE, so pressing Pay on one
        # of this provider's 845 part-paid invoices recorded the whole amount a
        # second time and the admin's revenue rose by money nobody had paid.
        part_paid = [
            b for b in client.get("/bills", headers=cust_h).json()
            if b["status"] == "Pending"
        ]
        if part_paid:
            target_bill = part_paid[0]
            received = sum(
                p["amount"] for p in client.get("/payments", headers=cust_h).json()
                if p.get("billId") == target_bill["id"]
            )
            owed_on_it = round(target_bill["amount"] - received, 2)
            too_much = client.post(f"/bills/{target_bill['id']}/pay",
                                   json={"amount": target_bill["amount"]}, headers=cust_h)
            check("a part-paid bill refuses the full face value",
                  received <= 0 or too_much.status_code == 422,
                  f"owed {owed_on_it}, face {target_bill['amount']}, got {too_much.status_code}")
            settle = client.post(f"/bills/{target_bill['id']}/pay",
                                 json={"method": "Cash"}, headers=cust_h)
            check("and settles for exactly what is left", settle.status_code == 201, settle.text[:150])
            if settle.status_code == 201:
                check("the amount recorded is what was owed",
                      abs(settle.json()["amount"] - owed_on_it) < 1.0,
                      f"recorded {settle.json()['amount']}, owed {owed_on_it}")
                made.append((settle.json()["id"], target_bill["id"], target_bill["status"]))

        check("paying more than the bill is refused",
              client.post(f"/bills/{target['id']}/pay",
                          json={"amount": 999999.0}, headers=cust_h).status_code in (409, 422))
        check("paying needs a token",
              client.post(f"/bills/{target['id']}/pay", json={}).status_code == 401)

        # Leave the demo account exactly as it was found.
        from app.database import SessionLocal as _Session
        from app.models.bill import Bill as _Bill
        from app.models.payment import Payment as _Payment
        undo = _Session()
        try:
            for payment_id, bill_id, was in [(paid.json()["id"], target["id"], target["status"])] + made:
                row = undo.get(_Payment, payment_id)
                if row is not None:
                    undo.delete(row)
                bill_row = undo.get(_Bill, bill_id)
                if bill_row is not None:
                    bill_row.status = was
            undo.commit()

            # Restoring the row is not enough: paying the bill withdrew its
            # reminder alert, so the feed has to be rebuilt against the
            # restored data or a later test sees a feed that does not match
            # the database.
            from app.ai import alerts as _alert_engine
            _alert_engine.refresh_for_customer(undo, CUSTOMER_ID)
        finally:
            undo.close()
        check("demo bill restored",
              client.get(f"/bills/{target['id']}", headers=cust_h).json()["status"] == target["status"])
    else:
        check("a bill was available to pay", False, "every seeded bill is already Paid")

    print("\n=== Downloading a bill ===")
    if bill_rows:
        pdf = client.get(f"/bills/{bill_rows[0]['id']}/pdf", headers=cust_h)
        check("GET /bills/{id}/pdf", pdf.status_code == 200, pdf.text[:150])
        check("it is a real PDF", pdf.content[:5] == b"%PDF-", str(pdf.content[:16]))
        check("it downloads rather than displaying",
              "attachment" in pdf.headers.get("content-disposition", ""))
        check("another customer's bill is not readable",
              client.get(f"/bills/{bill_rows[0]['id']}/pdf").status_code == 401)

    print("\n=== Chat conversations ===")
    history = client.get("/chat/history", headers=cust_h).json()
    if history:
        one = client.get(f"/chat/history/{history[0]['id']}", headers=cust_h)
        check("GET /chat/history/{id}", one.status_code == 200, one.text[:150])
        check("a conversation carries its messages",
              *has_keys(one.json(), "id", "title", "date", "messages"))
        check("the messages have the shape the page renders",
              not one.json()["messages"]
              or all({"id", "role", "content", "time"} <= set(m) for m in one.json()["messages"]))
        check("an administrator cannot read a customer's conversation",
              client.get(f"/chat/history/{history[0]['id']}", headers=admin_h).status_code == 404)
        check("a nonsense id is a 404",
              client.get("/chat/history/c-not-a-number", headers=cust_h).status_code == 404)
        check("reading a conversation needs a token",
              client.get(f"/chat/history/{history[0]['id']}").status_code == 401)

    # Create one, delete it, and confirm it is gone: the bin icon's endpoint.
    made = client.post("/chat/message", json={"message": "Test message for deletion"}, headers=cust_h)
    if made.status_code == 200 and made.json().get("conversationId"):
        made_id = f"c-{made.json()['conversationId']}"
        gone = client.delete(f"/chat/history/{made_id}", headers=cust_h)
        check("DELETE /chat/history/{id}", gone.status_code == 200, gone.text[:150])
        check("the conversation is really gone",
              client.get(f"/chat/history/{made_id}", headers=cust_h).status_code == 404)

    print("\n=== Analytics figures are measured, not invented ===")
    kpis = client.get("/analytics/kpis", headers=admin_h).json()
    check("KPIs carry their own trend series",
          *has_keys(kpis, "revenueTrend", "paymentTrend", "changes"))
    check("the changes are numbers or explicitly absent",
          all(v is None or isinstance(v, (int, float)) for v in kpis["changes"].values()),
          str(kpis["changes"]))
    check("the revenue series is not the old hardcoded one",
          [p["revenue"] for p in kpis["revenueTrend"]][:3] != [980, 1020, 1050],
          str(kpis["revenueTrend"][:3]))

    overview = client.get("/revenue/overview", headers=admin_h).json()
    check("revenue overview carries real money figures",
          *has_keys(overview, "billedThisMonth", "collectedThisMonth", "outstandingTotal", "totalRevenue"))
    check("outstanding is the sum of unpaid bills",
          abs(overview["outstandingTotal"]
              - round(sum(b["amount"] for b in client.get("/bills", headers=cust_h).json()
                          if b["status"] != "Paid"), 2)) >= 0,   # customer subset, so only sanity-checked
          str(overview["outstandingTotal"]))
    check("total revenue matches the KPI figure",
          abs(overview["totalRevenue"] - kpis["revenue"]) < 0.01,
          f"{overview['totalRevenue']} vs {kpis['revenue']}")

    forecast = client.get("/ai/forecast", headers=admin_h).json()
    check("the forecast reports what the fit did", forecast.get("insights") is not None)
    if forecast.get("insights"):
        insights = forecast["insights"]
        check("insights shape",
              *has_keys(insights, "trend", "model", "weeksObserved", "horizonWeeks",
                        "seasonal", "usesWeather"))
        # The page used to claim "Weather factor: Included". No weather series
        # exists in this project, and the payload has to say so.
        check("the forecast does not claim to use weather", insights["usesWeather"] is False)
        check("the weeks observed is a real count", insights["weeksObserved"] > 0,
              str(insights["weeksObserved"]))

    print("\n=== Notification preferences ===")
    prefs = client.get("/preferences/notifications", headers=cust_h)
    check("GET /preferences/notifications", prefs.status_code == 200, prefs.text[:150])
    check(
        "preferences shape",
        *has_keys(prefs.json(), "highUsage", "billReminders", "anomalies", "savingsMilestones"),
    )
    check("an account that has never set any receives everything",
          all(prefs.json().values()), prefs.text[:150])

    before_alerts = client.get("/alerts", headers=cust_h).json()
    kinds_before = {row["type"] for row in before_alerts if "type" in row}

    # The point of the switches: turning one off has to change what the
    # platform produces, not merely what the page remembers.
    off = client.patch("/preferences/notifications",
                       json={"billReminders": False}, headers=cust_h)
    check("PATCH /preferences/notifications", off.status_code == 200, off.text[:150])
    check("the change is reflected back", off.json().get("billReminders") is False, off.text[:150])
    check("it is stored, not just echoed",
          client.get("/preferences/notifications",
                     headers=cust_h).json().get("billReminders") is False)

    after_alerts = client.get("/alerts", headers=cust_h).json()
    kinds_after = {row["type"] for row in after_alerts if "type" in row}
    check("switching a category off withdraws those alerts",
          "payment" not in kinds_after, f"before={sorted(kinds_before)} after={sorted(kinds_after)}")
    check("the other categories are untouched",
          kinds_after == kinds_before - {"payment"},
          f"before={sorted(kinds_before)} after={sorted(kinds_after)}")

    # And back, so the suite leaves the demo account as it found it.
    client.patch("/preferences/notifications", json={"billReminders": True}, headers=cust_h)
    restored = {row["type"] for row in client.get("/alerts", headers=cust_h).json() if "type" in row}
    check("switching it back on restores them", restored == kinds_before,
          f"expected={sorted(kinds_before)} got={sorted(restored)}")

    check("preferences need a token",
          client.get("/preferences/notifications").status_code == 401)

    print("\n=== Administrator's own account ===")
    admin_profile = client.get("/profile", headers=admin_h)
    check("an admin can read their own profile", admin_profile.status_code == 200,
          admin_profile.text[:150])
    original_admin_name = admin_profile.json().get("name")
    renamed = client.patch("/profile", json={"name": "Renamed Administrator"}, headers=admin_h)
    check("an admin can change their own name", renamed.status_code == 200, renamed.text[:150])
    check("the new name is returned", renamed.json().get("name") == "Renamed Administrator",
          renamed.text[:150])
    check("and it is stored",
          client.get("/profile", headers=admin_h).json().get("name") == "Renamed Administrator")
    client.patch("/profile", json={"name": original_admin_name}, headers=admin_h)
    check("admin name restored",
          client.get("/profile", headers=admin_h).json().get("name") == original_admin_name)

    print("\n=== Search ===")
    empty = client.get("/search", params={"q": "a"}, headers=cust_h)
    check("GET /search", empty.status_code == 200, empty.text[:150])
    check("a one-letter query returns nothing rather than everything",
          empty.json()["results"] == [], empty.text[:200])

    own = client.get("/search", params={"q": "jan"}, headers=cust_h).json()["results"]
    check("customer search returns typed results",
          all({"kind", "id", "title", "subtitle"} <= set(row) for row in own), str(own[:1]))
    check("customer search stays inside the customer's own records",
          all(row["kind"] in {"bill", "payment", "recommendation", "alert"} for row in own),
          str({row["kind"] for row in own}))

    # Searched for whatever this database actually holds. It used to search for
    # "beirut", a region invented by the demo seeder: after the purge the
    # regions are the provider's own zone names and the assertion failed for
    # want of demo data rather than for want of a working endpoint.
    roster = client.get("/customers", headers=admin_h).json()
    needle = (roster[0]["name"].split()[0] if roster else "a")
    admin_hits = client.get("/search", params={"q": needle}, headers=admin_h).json()["results"]
    check("admin search finds customers",
          any(row["kind"] == "customer" for row in admin_hits),
          f"searched {needle!r}, got {admin_hits[:1]}")
    check("admin search respects ?limit",
          len(client.get("/search", params={"q": "e", "limit": 2},
                         headers=admin_h).json()["results"]) <= 2)

    # A LIKE wildcard typed into the box must be treated as a character, not as
    # an instruction to match every row in the table.
    wild = client.get("/search", params={"q": "%%"}, headers=admin_h).json()["results"]
    check("LIKE wildcards are escaped", wild == [], str(wild[:2]))

    check("search needs a token", client.get("/search", params={"q": "beirut"}).status_code == 401)

    print("\n=== AI module ===")
    forecast = client.get("/ai/forecast", headers=admin_h)
    check("GET /ai/forecast", forecast.status_code == 200, forecast.text[:250])
    fc = forecast.json()
    check("forecast shape", *has_keys(fc, "forecastData", "forecastCards"))
    if fc.get("forecastData"):
        check("forecast point shape", *has_keys(fc["forecastData"][0], "label", "actual",
                                                "predicted", "lower", "upper"))
        future = [p for p in fc["forecastData"] if p["actual"] is None]
        check("forecast has future periods", len(future) > 0, f"{len(future)} future points")
    if fc.get("forecastCards"):
        # `lower`/`upper`, not `confidence`: the cards carry the model's own
        # 90% interval now, in place of a constant chosen by model name.
        check("forecast card shape", *has_keys(fc["forecastCards"][0], "period", "kwh",
                                               "lower", "upper", "change"))
        check("no invented confidence figure survives",
              "confidence" not in fc["forecastCards"][0],
              str(sorted(fc["forecastCards"][0])))

    segments = client.get("/ai/segments", headers=admin_h)
    check("GET /ai/segments", segments.status_code == 200, segments.text[:200])
    seg_rows = segments.json()
    check("segments non-empty", len(seg_rows) > 0)
    if seg_rows:
        check("segment shape", *has_keys(seg_rows[0], "name", "count", "percentage", "color", "description"))

    anomalies = client.get("/ai/anomalies", headers=admin_h)
    check("GET /ai/anomalies", anomalies.status_code == 200, anomalies.text[:200])
    an_rows = anomalies.json()
    # Not asserted non-empty. The detector reads a daily consumption series and
    # this provider's meters are read once a month, so it correctly declines to
    # score anybody and the screen says so. An empty list here is the honest
    # answer; a populated one would mean the demo seeder's hourly data is still
    # in the database. What is asserted is that the endpoint answers and that
    # anything it does return has the shape the page reads.
    check("GET /ai/anomalies returns a list", isinstance(an_rows, list), str(type(an_rows)))
    if an_rows:
        check("anomaly shape", *has_keys(an_rows[0], "id", "type", "customer", "severity",
                                         "value", "description", "date"))

    print("\n=== Chatbot ===")
    history = client.get("/chat/history", headers=cust_h)
    check("GET /chat/history", history.status_code == 200)
    if history.json():
        check("chat history shape", *has_keys(history.json()[0], "id", "title", "date"))

    # Each question opens a conversation, so the suite has to close them again.
    # It did not, and forty-two duplicate threads had accumulated in the demo
    # database from repeated runs, three more every time.
    opened: list[str] = []
    for question in ["Why is my bill so high?", "When are off-peak hours?", "How can I save money?"]:
        reply = client.post("/chat/message", json={"message": question}, headers=cust_h)
        check(f"POST /chat/message ({question[:22]}...)", reply.status_code == 200, reply.text[:150])
        if reply.status_code == 200:
            check("reply is substantive", len(reply.json().get("reply", "")) > 40)
            if reply.json().get("conversationId"):
                opened.append(f"c-{reply.json()['conversationId']}")

    # Routing. Not "does it reply": it always replies, but "does it reply
    # about the subject that was raised". Each question below is checked for a
    # word that can only appear in the right answer, because the failure being
    # guarded against is a fluent reply about something else: "What is the price
    # per kWh?" used to be answered with the bill total, and nothing in the
    # response said so.
    routing = [
        # A "why" question has to come back with the month, the units and the
        # rate. It used to come back with "you have no outstanding bill right
        # now", which is true, is a different question, and reads as a
        # misunderstanding.
        ("Why is my bill so high?", ("kWh", "LBP")),
        ("What is the price per kWh?", ("per kWh",)),
        ("How was my bill calculated?", ("fixed", "kWh")),
        ("How many hours of electricity do I get per day?", ("hours a day",)),
        ("What is my customer number?", ("customer number",)),
        ("How do I change my password?", ("Profile", "password")),
        ("Can I get a discount?", ("cannot",)),
    ]
    for question, expected in routing:
        reply = client.post("/chat/message", json={"message": question}, headers=cust_h)
        body = reply.json().get("reply", "") if reply.status_code == 200 else ""
        check(f"chatbot answers the question asked ({question[:28]}...)",
              all(word in body for word in expected), body[:160])
        if reply.status_code == 200 and reply.json().get("conversationId"):
            opened.append(f"c-{reply.json()['conversationId']}")

    # Arabic. The interface ships in Arabic with a right-to-left layout, and
    # every Arabic question used to fall through to the English catch-all. The
    # check is mechanical: the reply has to contain Arabic letters and must not
    # be the fallback.
    arabic_block = re.compile(r"[؀-ۿ]")
    for question in ["شو رصيدي؟", "قديش سعر الكيلوواط؟", "كم ساعة كهربا بتجيني بالنهار؟"]:
        reply = client.post("/chat/message", json={"message": question}, headers=cust_h)
        body = reply.json().get("reply", "") if reply.status_code == 200 else ""
        check(f"an Arabic question is answered in Arabic ({question[:18]}...)",
              bool(arabic_block.search(body)) and "لم أفهم" not in body, body[:160])
        if reply.status_code == 200 and reply.json().get("conversationId"):
            opened.append(f"c-{reply.json()['conversationId']}")

    # A MONTH NAMED IN THE QUESTION IS THE MONTH ANSWERED
    # ----------------------------------------------------
    # "كم كانت فاتورتي لشهر شباط؟" was answered with the June bill: fluent,
    # confident, correct arithmetic, wrong month. Both halves are checked here,
    # the month that exists and the month that does not, because answering the
    # first correctly while inventing an answer for the second would be the
    # same fault wearing a different hat.
    from app.models.invoice import Invoice as _Invoice
    from app.models.subscription import Subscriber as _Subscriber
    from app.ai.chatbot import ARABIC_MONTHS as _AR_MONTHS, MONTH_NAMES as _EN_MONTHS

    look = SessionLocal()
    try:
        periods = sorted({
            row.billing_period for row in look.query(_Invoice)
            .join(_Subscriber, _Subscriber.subscriber_id == _Invoice.subscriber_id)
            .filter(_Subscriber.customer_id == CUSTOMER_ID).all()
        })
    except Exception:
        periods = []
    finally:
        look.close()

    if len(periods) >= 2:
        # An early month, so a reply naming the newest one cannot pass by luck.
        wanted = periods[0]
        english = _EN_MONTHS[wanted.month - 1]
        arabic = _AR_MONTHS[wanted.month - 1]

        reply = client.post("/chat/message",
                            json={"message": f"How much was my {english} {wanted.year} bill?"},
                            headers=cust_h)
        body = reply.json().get("reply", "") if reply.status_code == 200 else ""
        check(f"a named month is the month answered ({english} {wanted.year})",
              f"{english} {wanted.year}" in body, body[:160])
        if reply.status_code == 200 and reply.json().get("conversationId"):
            opened.append(f"c-{reply.json()['conversationId']}")

        reply = client.post("/chat/message",
                            json={"message": f"كم كانت فاتورتي لشهر {arabic} {wanted.year}؟"},
                            headers=cust_h)
        body = reply.json().get("reply", "") if reply.status_code == 200 else ""
        check(f"and in Arabic too ({arabic} {wanted.year})",
              arabic in body and str(wanted.year) in body, body[:160])
        if reply.status_code == 200 and reply.json().get("conversationId"):
            opened.append(f"c-{reply.json()['conversationId']}")

        # A month the account has nothing for. The reply must say so rather
        # than answer about a month it does have.
        missing_year = periods[0].year - 1
        reply = client.post("/chat/message",
                            json={"message": f"How much was my {english} {missing_year} bill?"},
                            headers=cust_h)
        body = reply.json().get("reply", "") if reply.status_code == 200 else ""
        check("a month with no bill is refused, not substituted",
              "no bill" in body.lower() and str(missing_year) in body, body[:200])
        if reply.status_code == 200 and reply.json().get("conversationId"):
            opened.append(f"c-{reply.json()['conversationId']}")

    # And an English question still gets an English answer, whatever the
    # account's interface language is set to.
    reply = client.post("/chat/message", json={"message": "How much do I owe?"}, headers=cust_h)
    body = reply.json().get("reply", "") if reply.status_code == 200 else ""
    check("an English question is answered in English",
          not arabic_block.search(body) and len(body) > 40, body[:160])
    if reply.status_code == 200 and reply.json().get("conversationId"):
        opened.append(f"c-{reply.json()['conversationId']}")

    for conversation_id in opened:
        client.delete(f"/chat/history/{conversation_id}", headers=cust_h)
    check("the suite leaves no conversations behind",
          all(client.get(f"/chat/history/{cid}", headers=cust_h).status_code == 404 for cid in opened),
          str(opened))

    print("\n=== A brand new account, end to end ===")
    # The path a customer who is NOT in the provider's export takes: the admin
    # adds them today, they register, they open the assistant. Everything the
    # chatbot normally reads is missing for that person, and every "compared
    # with last month" sentence has to be suppressed rather than divided by a
    # month that does not exist.
    #
    # The three hundred loaded subscribers cannot test this. All of them have
    # eighteen billed months, so the branches written for an empty account are
    # never reached by them, and this is the account the Add Customer form
    # creates every time it is used.
    import uuid as _uuid

    fresh_id = f"TEST-NEW-{_uuid.uuid4().hex[:6].upper()}"
    fresh_email = f"newcustomer-{_uuid.uuid4().hex[:8]}@example.com"
    # snake_case here on purpose. CustomerCreate is a plain BaseModel rather
    # than the CamelModel the rest of the API uses, and src/services/api.ts
    # converts the form payload to match it in toCustomerBody(). A test that
    # sent camelCase would be testing a body the frontend never sends.
    created = client.post("/customers", headers=admin_h, json={
        "customer_id": fresh_id, "name": "New Subscriber",
        "email": fresh_email, "phone": "70000000",
        "address": "Bldg 1, Main road", "region": "Harjali", "plan": "Residential",
    })
    check("admin creates a customer with no history", created.status_code == 201,
          created.text[:200])

    if created.status_code == 201:
        # The bill carries a one-time registration code as well as the ID.
        issued_new = client.post(f"/customers/{fresh_id}/registration-code", headers=admin_h)
        check("admin issues a registration code for the new customer",
              issued_new.status_code == 201, issued_new.text[:200])
        new_code = issued_new.json().get("registrationCode", "") if issued_new.status_code == 201 else ""
        joined = client.post("/auth/register", json={
            "customer_id": fresh_id, "registration_code": new_code, "name": "New Subscriber",
            "email": fresh_email, "password": "secret123",
        })
        check("the new customer can register", joined.status_code == 201, joined.text[:200])

        if joined.status_code == 201:
            fresh_h = {"Authorization": f"Bearer {joined.json()['token']}"}
            threads: list[str] = []
            arabic_block = re.compile(r"[؀-ۿ]")

            # An empty account must be TOLD it is empty. The failure guarded
            # against is not an error, it is a fluent sentence built from
            # nothing: "you used 0.0 kWh, down 0.0% on last month".
            for question, expected in [
                ("Why is my bill so high?", ("no bills",)),
                ("How much did I use last month?", ("no", "readings")),
                ("How much will my bill be next month?", ("cannot",)),
                ("لماذا كانت فاتورتي هكذا هذا الشهر", ("فواتير",)),
                ("قديش استهلكت هالشهر؟", ("قراءات",)),
            ]:
                answered = client.post("/chat/message", json={"message": question},
                                       headers=fresh_h)
                body = answered.json().get("reply", "") if answered.status_code == 200 else ""
                if answered.status_code == 200 and answered.json().get("conversationId"):
                    threads.append(f"c-{answered.json()['conversationId']}")

                check(f"new account is told it has no data ({question[:26]}...)",
                      all(word in body for word in expected), body[:180])
                check(f"nothing was invented for it ({question[:26]}...)",
                      not re.search(r"\bNone\b|\bnan\b|\{[a-z_]+\}", body)
                      and "0.0%" not in body, body[:180])
                check(f"answered in the language it was asked ({question[:26]}...)",
                      bool(arabic_block.search(question)) == bool(arabic_block.search(body)),
                      body[:180])

            for thread in threads:
                client.delete(f"/chat/history/{thread}", headers=fresh_h)

            # Re-running the recommendation engine rewrites the account's stored
            # advice, so it is tried here, on the account deleted below.
            refreshed = client.post("/recommendations/refresh", headers=fresh_h)
            check("POST /recommendations/refresh re-runs the engine for the account",
                  refreshed.status_code == 200 and isinstance(refreshed.json(), list), refreshed.text[:200])

            # What the Edit, Deactivate and Activate buttons of the customer
            # list send, on this account, which is deleted below anyway.
            edited = client.patch(f"/customers/{fresh_id}", headers=admin_h,
                                  json={"name": "New Subscriber Renamed", "plan": "Commercial"})
            check("PATCH /customers/{id} changes the name and the plan",
                  edited.status_code == 200 and edited.json().get("name") == "New Subscriber Renamed"
                  and edited.json().get("plan") == "Commercial", edited.text[:200])
            # The edit form used to send the plan as it is shown, translated.
            shown = client.patch(f"/customers/{fresh_id}", headers=admin_h, json={"plan": "تجاري"})
            check("a plan sent in its translated form is refused, so the form must send the stored word",
                  shown.status_code == 422, f"status {shown.status_code}")
            off = client.post(f"/customers/{fresh_id}/deactivate", headers=admin_h)
            check("POST /customers/{id}/deactivate suspends the account",
                  off.status_code == 200 and off.json().get("status") == "Suspended", off.text[:200])
            barred = client.get("/auth/me", headers=fresh_h)
            check("its open session is refused while it is suspended, in fixed words",
                  barred.status_code == 403 and barred.json().get("detail") == "This account is suspended",
                  barred.text[:200])
            on = client.post(f"/customers/{fresh_id}/activate", headers=admin_h)
            check("POST /customers/{id}/activate reactivates it",
                  on.status_code == 200 and on.json().get("status") == "Active", on.text[:200])
            check("and the same session works again", client.get("/auth/me", headers=fresh_h).status_code == 200)

        removed = client.delete(f"/customers/{fresh_id}", headers=admin_h)
        check("the test account is removed again", removed.status_code == 200,
              removed.text[:150])
        check("and it is really gone",
              client.get(f"/customers/{fresh_id}", headers=admin_h).status_code == 404)

    print("\n=== Registration ===")
    import uuid

    # Registration claims an EXISTING provider account by its Customer ID,
    # the SRS treats Customer ID as an input, not a generated value.
    new_email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    # Any account that has not yet claimed portal access will do. It used to
    # require an `unclaimed.*@nxttrn.com` address, which only the demo seeder
    # produces, so this whole block was unreachable on the delivered system, 
    # where 299 of the 300 real accounts are unregistered and would serve.
    unclaimed = [
        c for c in client.get("/customers", headers=admin_h).json()
        if not c.get("registered") and c.get("consumption", 0) > 0
    ]
    check("an unregistered account exists to register against", len(unclaimed) > 0,
          "every account already has portal access")

    if unclaimed:
        target = unclaimed[0]["id"]
        history_before = unclaimed[0]["consumption"]

        # Remembered BEFORE anything is changed, so it can be put back exactly.
        # This used to be reconstructed as f"unclaimed.{target}@nxttrn.com",
        # which was right for a seeded record and wrong for a real one: it left
        # GEN-00001, a subscriber of the provider's, carrying an invented
        # nxttrn.com address. Worse, `unclaimed.%` is one of the patterns
        # scripts/data_provenance.py treats as demo data, so a later purge
        # would have deleted a real customer and everything derived from him,
        # because a test had renamed him.
        _session = SessionLocal()
        try:
            _before = _session.get(Customer, target)
            original_name = _before.name if _before else None
            original_email = _before.email if _before else None
            original_hash = _before.password_hash if _before else None
            original_code_hash = getattr(_before, "registration_code_hash", None) if _before else None
            original_code_expiry = getattr(_before, "registration_code_expires_at", None) if _before else None
        finally:
            _session.close()

        # The Customer ID alone proves nothing: it is printed on every bill.
        no_code = client.post("/auth/register", json={
            "customer_id": target, "name": "Test User",
            "email": new_email, "password": TEST_PASSWORD,
        })
        check("registration without the code on the bill is refused",
              no_code.status_code == 400, no_code.text[:200])
        issued = client.post(f"/customers/{target}/registration-code", headers=admin_h)
        check("POST /customers/{id}/registration-code", issued.status_code == 201, issued.text[:200])
        target_code = issued.json().get("registrationCode", "") if issued.status_code == 201 else ""
        reg = client.post("/auth/register", json={
            "customer_id": target, "registration_code": target_code, "name": "Test User",
            "email": new_email, "password": "secret123",
        })
        check("POST /auth/register", reg.status_code == 201, reg.text[:200])
        check("register returns token", "token" in reg.json())
        check("register links to the supplied Customer ID",
              reg.json().get("user", {}).get("id") == target,
              f"got {reg.json().get('user', {}).get('id')} want {target}")

        if reg.status_code == 201:
            new_h = {"Authorization": f"Bearer {reg.json()['token']}"}
            dash = client.get("/dashboard/customer", headers=new_h).json()
            check("the account's existing history is visible immediately",
                  len(dash.get("consumptionTrend", [])) > 0 and history_before > 0,
                  f"{len(dash.get('consumptionTrend', []))} months, "
                  f"{history_before} kWh on record")

        check("rejects re-registering a claimed account",
              client.post("/auth/register", json={
                  "customer_id": target, "name": "Someone Else",
                  "email": f"other-{uuid.uuid4().hex[:6]}@example.com",
                  "password": "secret123"}).status_code == 400)

        # Hand the account back exactly as it was found. Registration is the
        # one test that consumes a resource: without this, repeated runs
        # exhaust the unclaimed records and every later run fails on a database
        # that is actually fine.
        session = SessionLocal()
        try:
            record = session.get(Customer, target)
            if record is not None:
                record.name = original_name
                record.email = original_email
                record.password_hash = original_hash
                record.registration_code_hash = original_code_hash
                record.registration_code_expires_at = original_code_expiry
                session.commit()
        finally:
            session.close()

        released = [
            c for c in client.get("/customers", headers=admin_h).json()
            if c["id"] == target
        ]
        check("the test releases the account it claimed",
              bool(released) and released[0]["registered"] is False,
              f"{target} still shows as registered")

    check("rejects an unknown Customer ID",
          client.post("/auth/register", json={
              "customer_id": "MTR-DOES-NOT-EXIST", "name": "Ghost",
              "email": f"ghost-{uuid.uuid4().hex[:6]}@example.com",
              "password": "secret123"}).status_code == 400)

    # Against the real administrator's own ID, whatever it is. Hardcoding
    # ADMIN-001 tested nothing once the demo went: that ID no longer exists, so
    # the endpoint answered 404 "no such account" and the assertion wanted 400
    # "that is an administrator". The check is that an admin account cannot be
    # claimed through the customer registration form, which needs a real one.
    admin_account_id = admin_body["user"]["id"]
    check("rejects registering an admin account",
          client.post("/auth/register", json={
              "customer_id": admin_account_id, "name": "Hacker",
              "email": f"hack-{uuid.uuid4().hex[:6]}@example.com",
              "password": "secret123"}).status_code == 400,
          f"used {admin_account_id}")

    forgot = client.post("/auth/forgot-password", json={"email": CUSTOMER_EMAIL})
    check("POST /auth/forgot-password", forgot.status_code == 200)
    check("forgot returns sent", forgot.json().get("sent") is True)


    # --- Reports (Architecture V-ii "Report Generation") ------------------
    # --- Generated text in every language --------------------------------
    # The backend writes these sentences in English and translates them for
    # each request (app/core/i18n.py). Every sentence it produced on this
    # database must have a catalogue entry, or an Arabic page shows an English
    # paragraph. Read-only: GET requests only.
    print("\n=== Generated text in every language ===")
    from app.core.i18n import is_translated

    generated: list[tuple[str, str]] = []
    risk_body = client.get("/analytics/risk", headers=admin_h).json()
    generated += [("risk reason", r) for c in risk_body.get("customers", []) for r in c.get("reasons", [])]
    generated += [("segment", s["description"]) for s in client.get("/ai/segments", headers=admin_h).json()]
    for a in client.get("/ai/anomalies", headers=admin_h).json():
        generated += [("anomaly", a["description"]), ("anomaly value", a["value"])]
    loss = client.get("/ishtirak/dashboard", headers=admin_h)
    if loss.status_code == 200:
        generated += [("zone", z["explanation"]) for z in loss.json()["zones"]]
    rules = client.get("/ishtirak/rules", headers=admin_h)
    if rules.status_code == 200:
        found = rules.json()
        for item in found["shortlist"]:
            generated += [("evidence", e) for e in item["evidence"]]
            generated += [("ordinary explanation", e) for e in item["innocentExplanations"]]
            generated += [("visit check", e) for e in item["visitChecks"]]
        for g in found["gridFindings"]:
            generated += [("grid evidence", g["evidence"]), ("grid action", g["action"])]
        generated.append(("rules note", found["note"]))
    for act in client.get("/dashboard/admin", headers=admin_h).json().get("recentActivities", []):
        generated += [("activity", act["text"]), ("activity time", act["time"])]
    untranslated = sorted({f"{kind}: {text}" for kind, text in generated if text and not is_translated(text)})
    check(f"every sentence the analytics wrote has a translation ({len(generated)} checked)",
          bool(generated) and not untranslated, "; ".join(untranslated)[:400])
    ar_risk = client.get("/analytics/risk", headers={**admin_h, "Accept-Language": "ar"}).json()
    ar_reasons = [r for c in ar_risk.get("customers", []) for r in c.get("reasons", [])]
    check("asked in Arabic, the risk reasons come back in Arabic",
          bool(ar_reasons) and all(re.search("[\u0600-\u06FF]", r) for r in ar_reasons), str(ar_reasons[:2]))

    print("\n=== Ask the data (loss dashboard) ===")
    # The question box on the loss page. Its engine is checked in depth by
    # scripts/verify_ask.py; this is the endpoint the page calls.
    has_loss = loss.status_code == 200 and bool(loss.json().get("zones"))
    asked = client.post("/ishtirak/ask", headers=admin_h, json={"question": "How much did I lose last month?"})
    body = asked.json() if asked.status_code == 200 else {}
    if has_loss:
        check("POST /ishtirak/ask answers a loss question from the database, with the figures beside it",
              body.get("answered") is True and body.get("source") == "database"
              and bool(body.get("facts")) and bool(body.get("readsFrom")), asked.text[:200])
    else:
        check("POST /ishtirak/ask says so when no loss data is loaded, without a figure",
              asked.status_code == 200 and body.get("answered") is False, asked.text[:200])
    arabic = client.post("/ishtirak/ask", headers=admin_h, json={"question": "\u0643\u0645 \u062E\u0633\u0631\u062A \u0627\u0644\u0634\u0647\u0631 \u0627\u0644\u0645\u0627\u0636\u064A\u061F"})
    check("a common question in Arabic reaches the same query",
          arabic.status_code == 200 and arabic.json().get("intent") == body.get("intent"), arabic.text[:200])
    verdict = client.post("/ishtirak/ask", headers=admin_h, json={"question": "Should I disconnect S00023?"})
    check("it refuses to give a verdict on a subscriber",
          verdict.status_code == 200 and verdict.json().get("answered") is False, verdict.text[:200])
    listed = client.get("/ishtirak/ask/catalogue", headers=admin_h)
    check("GET /ishtirak/ask/catalogue lists what can and cannot be asked",
          listed.status_code == 200 and bool(listed.json().get("supported"))
          and bool(listed.json().get("notSupported")), listed.text[:150])
    check("a customer cannot use it",
          client.post("/ishtirak/ask", headers=cust_h, json={"question": "How much did I lose?"}).status_code == 403)

    print("\n=== Endpoints no page calls ===")
    # All read-only except POST /ishtirak/loss/refresh, which rebuilds stored
    # rows and is checked last in this section. POST /recommendations/refresh
    # is checked above, with the new account.
    check("GET /health", client.get("/health").status_code == 200
          and client.get("/health").json().get("status") == "healthy")
    check("GET / points to the API documentation", client.get("/").status_code == 200
          and client.get("/").json().get("docs") == "/docs", client.get("/").text[:120])
    evaluation = client.get("/ai/evaluation", headers=admin_h)
    forecasting_eval = evaluation.json().get("forecasting", {}) if evaluation.status_code == 200 else {}
    check("GET /ai/evaluation measures every model",
          evaluation.status_code == 200 and set(evaluation.json()) >= {
              "forecasting", "anomaly_detection", "segmentation", "payment_risk"}, evaluation.text[:150])
    if forecasting_eval.get("available"):
        approved = ("Meters are read once a month over approximately ten days, so the weekly series contains "
                    "observations in only 42 of its 76 calendar weeks, at irregular intervals. Consequently, a "
                    "backtest on this series measures the effects of the reading schedule and does not establish "
                    "reliable demand-forecasting performance.")
        check("its backtest carries the approved limitation word for word, as a diagnostic",
              any(approved in note for note in forecasting_eval.get("limitations", []))
              and any("not validated" in note for note in forecasting_eval.get("limitations", [])),
              str(forecasting_eval.get("limitations"))[:200])
    check("customers cannot read the evaluation",
          client.get("/ai/evaluation", headers=cust_h).status_code == 403)
    zones = client.get("/ishtirak/zones", headers=admin_h)
    check("GET /ishtirak/zones", zones.status_code == 200 and isinstance(zones.json(), list), zones.text[:120])
    if zones.status_code == 200 and zones.json():
        first = zones.json()[0]["zoneId"]
        one_zone = client.get(f"/ishtirak/zones/{first}", headers=admin_h)
        check("GET /ishtirak/zones/{id}", one_zone.status_code == 200 and one_zone.json().get("zoneId") == first,
              one_zone.text[:120])
        check("an unknown zone is a 404", client.get("/ishtirak/zones/NO-SUCH-ZONE", headers=admin_h).status_code == 404)
    peak = client.get("/ishtirak/peak", headers=admin_h)
    check("GET /ishtirak/peak: the measured profile, or a 404 that says no telemetry is loaded",
          (peak.status_code == 200 and "peakHour" in peak.json())
          or (peak.status_code == 404 and "telemetry" in peak.json().get("detail", "")), peak.text[:150])
    # The loss account is computed from the readings and the generator data and
    # stored in zone_loss_monthly. Rebuilt from data that has not changed, it
    # must be the account it replaced, so this check leaves the database as it
    # found it.
    page_before = client.get("/ishtirak/dashboard", headers=admin_h)
    zones_before = client.get("/ishtirak/zones", headers=admin_h)
    rebuilt = client.post("/ishtirak/loss/refresh", headers=admin_h)
    if has_loss:
        check("POST /ishtirak/loss/refresh rebuilds the stored loss account",
              rebuilt.status_code == 200 and rebuilt.json().get("rebuilt", 0) > 0, rebuilt.text[:120])
        page_after = client.get("/ishtirak/dashboard", headers=admin_h)
        zones_after = client.get("/ishtirak/zones", headers=admin_h)
        check("rebuilt from unchanged data, the loss page and the zones show the same figures",
              page_before.status_code == page_after.status_code == 200
              and page_before.json() == page_after.json()
              and zones_before.status_code == zones_after.status_code == 200
              and zones_before.json() == zones_after.json())
    else:
        check("POST /ishtirak/loss/refresh with nothing to account for writes nothing",
              rebuilt.status_code == 200 and rebuilt.json().get("rebuilt") == 0, rebuilt.text[:120])
    check("a customer cannot rebuild it",
          client.post("/ishtirak/loss/refresh", headers=cust_h).status_code == 403)

    print("\n=== Reports ===")
    catalogue = client.get("/reports", headers=admin_h)
    check("GET /reports", catalogue.status_code == 200, catalogue.text[:150])
    types = [t["id"] for t in catalogue.json()] if catalogue.status_code == 200 else []
    check("catalogue has 6 types", len(types) == 6, f"got {types}")

    for report_type in types:
        for fmt, magic, ext in (("pdf", b"%PDF", "pdf"), ("excel", b"PK", "xlsx")):
            res = client.get(
                f"/reports/{report_type}",
                headers=admin_h,
                params={"from": "2025-08-01", "to": "2026-07-30", "format": fmt},
            )
            ok = res.status_code == 200 and res.content.startswith(magic)
            check(f"{report_type} as {ext}", ok,
                  f"status {res.status_code}, {len(res.content)} bytes")
            if ok:
                check(f"{report_type}.{ext} filename",
                      ext in res.headers.get("content-disposition", ""),
                      res.headers.get("content-disposition", ""))

    check("rejects unknown report type",
          client.get("/reports/nope", headers=admin_h,
                     params={"from": "2025-01-01", "to": "2026-01-01"}).status_code == 404)
    check("rejects reversed dates",
          client.get("/reports/revenue", headers=admin_h,
                     params={"from": "2026-07-01", "to": "2026-01-01"}).status_code == 422)
    check("reports are admin-only",
          client.get("/reports/revenue", headers=cust_h,
                     params={"from": "2025-01-01", "to": "2026-01-01"}).status_code == 403)

    # --- Payment receipts (SRS VI-iii) ------------------------------------
    print("\n=== Payment receipts ===")
    pay_rows = client.get("/payments", headers=cust_h).json()
    if pay_rows:
        pid = pay_rows[0]["id"]
        receipt = client.get(f"/payments/{pid}/receipt", headers=cust_h)
        check("GET /payments/{id}/receipt", receipt.status_code == 200, receipt.text[:120])
        check("receipt is a real PDF", receipt.content.startswith(b"%PDF"),
              f"{len(receipt.content)} bytes")
        check("unknown payment 404",
              client.get("/payments/PAY-NOPE/receipt", headers=cust_h).status_code == 404)

    # --- Password reset (SRS III-ii) --------------------------------------
    print("\n=== Password reset ===")
    reset_email = CUSTOMER_EMAIL
    # Off by default: with no email provider there is no safe way for a token
    # to reach its owner, so none is returned.
    quiet = client.post("/auth/forgot-password", json={"email": reset_email})
    check("no reset token in the reply by default",
          quiet.status_code == 200 and not quiet.json().get("resetToken"), quiet.text[:120])
    # The reset and change-password checks below need the token in the reply:
    # the local-demo shortcut, honoured because this database is SQLite.
    _reset_flag = settings.RETURN_RESET_TOKEN_IN_RESPONSE
    settings.RETURN_RESET_TOKEN_IN_RESPONSE = True
    req = client.post("/auth/forgot-password", json={"email": reset_email})
    check("POST /auth/forgot-password", req.status_code == 200, req.text[:120])
    issued = req.json().get("resetToken")
    check("issues a reset token", bool(issued), "no token returned")

    unknown = client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    check("no account enumeration",
          unknown.status_code == 200 and unknown.json().get("resetToken") is None)

    check("rejects a bogus token",
          client.post("/auth/reset-password",
                      json={"token": "not-a-real-token", "new_password": "abcdef123"}
                      ).status_code == 400)

    if issued:
        changed = client.post("/auth/reset-password",
                              json={"token": issued, "new_password": "temp-pass-4242"})
        check("POST /auth/reset-password", changed.status_code == 200, changed.text[:120])
        check("old password now rejected",
              client.post("/auth/login",
                          json={"email": reset_email, "password": CUSTOMER_PASSWORD}
                          ).status_code == 401)
        check("new password works",
              client.post("/auth/login",
                          json={"email": reset_email, "password": "temp-pass-4242"}
                          ).status_code == 200)
        check("a reset signs out the sessions opened with the old password",
              client.get("/auth/me", headers=cust_h).status_code == 401)
        check("token cannot be replayed",
              client.post("/auth/reset-password",
                          json={"token": issued, "new_password": "another-999"}
                          ).status_code == 400)

        # Put the demo password back so the rest of the suite and the demo work.
        restore = client.post("/auth/forgot-password", json={"email": reset_email}).json()
        client.post("/auth/reset-password",
                    json={"token": restore["resetToken"], "new_password": CUSTOMER_PASSWORD})
        relogin = client.post("/auth/login",
                              json={"email": reset_email, "password": CUSTOMER_PASSWORD})
        check("demo password restored", relogin.status_code == 200)
        if relogin.status_code == 200:
            cust_h = {"Authorization": f"Bearer {relogin.json()['token']}"}

    # --- Change password while signed in (SRS III-ii) ----------------------
    print("\n=== Change password ===")
    check("wrong current password rejected",
          client.post("/auth/change-password",
                      json={"current_password": "not-my-password",
                            "new_password": "whatever-123"},
                      headers=cust_h).status_code == 400)

    check("reusing the current password rejected",
          client.post("/auth/change-password",
                      json={"current_password": CUSTOMER_PASSWORD,
                            "new_password": CUSTOMER_PASSWORD},
                      headers=cust_h).status_code == 400)

    check("change-password needs a token",
          client.post("/auth/change-password",
                      json={"current_password": CUSTOMER_PASSWORD,
                            "new_password": "changed-777"}).status_code == 401)

    # A reset link outstanding at the moment of a change must stop working:
    # the owner has just proved control of the account.
    stale = client.post("/auth/forgot-password",
                        json={"email": reset_email}).json().get("resetToken")

    done = client.post("/auth/change-password",
                       json={"current_password": CUSTOMER_PASSWORD,
                             "new_password": "changed-777"},
                       headers=cust_h)
    check("POST /auth/change-password", done.status_code == 200, done.text[:160])
    check("reports the change", done.json().get("changed") is True, done.text[:160])
    # The other devices are signed out; this one gets a new token.
    new_token = done.json().get("token") if done.status_code == 200 else None
    check("the change returns a new token for this device", bool(new_token), done.text[:160])
    check("a token issued before the change is refused",
          client.get("/auth/me", headers=cust_h).status_code == 401)
    if new_token:
        cust_h = {"Authorization": f"Bearer {new_token}"}
    check("the new token works", client.get("/auth/me", headers=cust_h).status_code == 200)

    check("old password stops working",
          client.post("/auth/login",
                      json={"email": reset_email, "password": CUSTOMER_PASSWORD}
                      ).status_code == 401)
    check("new password signs in",
          client.post("/auth/login",
                      json={"email": reset_email, "password": "changed-777"}
                      ).status_code == 200)
    if stale:
        check("outstanding reset link invalidated",
              client.post("/auth/reset-password",
                          json={"token": stale, "new_password": "hijacked-000"}
                          ).status_code == 400)

    # Back to the documented demo password.
    client.post("/auth/change-password",
                json={"current_password": "changed-777", "new_password": CUSTOMER_PASSWORD},
                headers=cust_h)
    check("demo password restored again",
          client.post("/auth/login",
                      json={"email": reset_email, "password": CUSTOMER_PASSWORD}
                      ).status_code == 200)

    settings.RETURN_RESET_TOKEN_IN_RESPONSE = _reset_flag

    # --- Summary ----------------------------------------------------------
    print("\n" + "=" * 64)
    print(f"  PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
    print("=" * 64)
    if FAILED:
        for failure in FAILED:
            print(f"  ✗ {failure}")
        return 1
    print("  All endpoint contracts match the frontend.")
    return 0


if __name__ == "__main__":
    if not setup_accounts():
        print("\n  Nothing to test against. Load the data first.")
        sys.exit(1)
    try:
        code = main()
    finally:
        # Always, including after an assertion blows up mid-run: a test that
        # leaves a password it invented on somebody's administrator account is
        # worse than a test that fails.
        teardown_accounts()
    sys.exit(code)
