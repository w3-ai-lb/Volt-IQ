"""
Regression checks for the findings of the October 2026 code review.

    python -m tests.test_review_fixes

One section per finding, each written to fail on the code before the fix:

  F1   payment-risk scores do not change with the calendar; recency is counted
       to the newest data, and "days since payment" is never negative
  F2   a customer's monthly series ends with their newest reading, however
       long ago that was, and the PDF/Excel statement states those dates
  F3   a password change or reset signs out every other session; the device
       that changed it keeps working with the token it is given
  F4   the Forecast Report calls its figure a backtest diagnostic and carries
       the approved limitation word for word
  F6   a bill alert quotes what is still owed, and its wording does not go
       stale as the days pass
  F9   the executive dashboard states the day its figures are for, and which
       month its consumption figure covers
  F12  the sentences the server writes (alerts, recommendations, risk reasons,
       refusals) reach the reader in the language they chose
  F14  repeated failures at sign-in, registration, password reset and
       password change are answered with 429
  F15  the server refuses a placeholder signing key outside SQLite
  F16  the requirements list no package the code does not use

and two for defects found while reviewing those fixes:

  Update   the helper scripts (check-data.bat, purge-demo.bat, check-chatbot.bat
           and the rest) still run on a database created before this change,
           because they add its new columns first, as the server does
  Density  monthly figures follow how often the meter is read: a meter that
           reports every hour gets its daily chart; a meter read by hand is not
           credited with a fourth month when four readings fall inside the
           recommender's 90-day window; alert dates read "8 Jun 2026"
  Anchor   the customer segments are counted to the newest reading, like every
           other dated figure, so the "Loyal Customers" (two-year) segment does
           not fill up on its own as the calendar passes the signup dates

IT CANNOT REACH A REAL DATABASE
-------------------------------
Before anything from the application is imported, DATABASE_URL is pointed at a
new SQLite file in a temporary folder, and the run stops if the settings do not
show that file. The folder is deleted when the run ends. Every record is
synthetic: IDs start with REV-, names are invented, addresses use example.com,
and passwords are generated for this run and never printed.

Same custom runner as tests/test_api.py: PASS and FAIL lines, a summary, and
exit status 1 when anything fails.
"""

from __future__ import annotations

import atexit
import contextlib
import importlib
import io
import logging
import os
import re
import secrets
import shutil
import sys
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="review-fixes-test-")
_DB_URL = "sqlite:///" + os.path.join(_TMP, "review.db")
os.environ["DATABASE_URL"] = _DB_URL
os.environ.pop("RETURN_RESET_TOKEN_IN_RESPONSE", None)
os.environ.pop("OPENAI_API_KEY", None)
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings, settings  # noqa: E402

if settings.DATABASE_URL != _DB_URL:  # the guard this file depends on
    print("STOP: the settings do not point at the temporary test database.")
    sys.exit(2)

from app.core.security import hash_password  # noqa: E402
from app.database import SessionLocal, create_all_tables  # noqa: E402
from app.main import app  # noqa: E402
from app.models.bill import Bill  # noqa: E402
from app.models.consumption import Consumption  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.payment import Payment  # noqa: E402

create_all_tables()
client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []
BACKEND = Path(__file__).resolve().parents[1]


def check(name: str, condition: bool, observed: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}" + (f"   [observed: {observed}]" if observed else ""))


def attempt(name: str, func) -> None:
    """Run one group of checks; an exception is a failure of the group, not a crash."""
    try:
        func()
    except Exception as exc:  # noqa: BLE001 - reported, not hidden
        check(name, False, f"{type(exc).__name__}: {str(exc)[:160]}")


# ---------------------------------------------------------------------------
# A clock that can be set
# ---------------------------------------------------------------------------
_CLOCK_MODULES = ("app.ai.risk", "app.analytics.asof", "app.ai.alerts", "app.routers.consumption",
                  "app.ai.segmentation")


@contextlib.contextmanager
def wall_clock(day: str):
    """Make datetime.now() return noon UTC on `day` inside the modules that read it."""
    fixed = datetime.fromisoformat(day + "T12:00:00+00:00")

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz else fixed.replace(tzinfo=None)

    patched = []
    for name in _CLOCK_MODULES:
        module = importlib.import_module(name)
        if hasattr(module, "datetime"):
            patched.append((module, module.datetime))
            module.datetime = _Frozen
    try:
        yield
    finally:
        for module, original in patched:
            module.datetime = original


# ---------------------------------------------------------------------------
# Synthetic data: one account with eighteen months of history that ends on
# 10 June 2026, like the provider's export, and three bare accounts.
# ---------------------------------------------------------------------------
PASSWORDS: dict[str, str] = {}


def _account(cid: str, role: str = "customer", claimed: bool = True) -> Customer:
    PASSWORDS[cid] = secrets.token_urlsafe(12) if claimed else ""
    return Customer(
        customer_id=cid, name=f"Synthetic {cid}", email=f"{cid.lower()}@example.com",
        password_hash=hash_password(PASSWORDS[cid]) if claimed else "",
        role=role, status="Active", phone="+000 0000 0000", address="1 Example Street",
        region="Test", plan="Residential",
    )


HISTORY = "REV-0001"
MONTHS = [(2025 + (m - 1) // 12, (m - 1) % 12 + 1) for m in range(1, 19)]   # Jan 2025 .. Jun 2026
NEWEST_READING = date(2026, 6, 10)
PART_PAID_AMOUNT, PART_PAID_RECEIVED = 1_000_000.0, 400_000.0

_s = SessionLocal()
_s.add_all([_account("REV-ADMIN", role="admin"), _account(HISTORY), _account("REV-0002"),
            _account("REV-0003"), _account("REV-0004", claimed=False)])
_s.flush()
for i, (year, month) in enumerate(MONTHS):
    _s.add(Consumption(customer_id=HISTORY, timestamp=datetime(year, month, 10), kwh=100.0 + i, cost=1000.0 * (100 + i)))
    last_day = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1))
    bill_id = f"BILL-REV-{year}{month:02d}"
    label = date(year, month, 1).strftime("%b %Y")
    if (year, month) == (2025, 3):
        # Part paid and never settled: the bill the reminder is about.
        _s.add(Bill(bill_id=bill_id, customer_id=HISTORY, month=label, amount=PART_PAID_AMOUNT,
                    due_date=last_day, status="Pending"))
        _s.add(Payment(payment_id=f"PAY-REV-{year}{month:02d}", customer_id=HISTORY, bill_id=bill_id,
                       date=date(2025, 4, 5), amount=PART_PAID_RECEIVED, method="Cash", status="Partial"))
    else:
        _s.add(Bill(bill_id=bill_id, customer_id=HISTORY, month=label, amount=500_000.0,
                    due_date=last_day, status="Paid"))
        _s.add(Payment(payment_id=f"PAY-REV-{year}{month:02d}", customer_id=HISTORY, bill_id=bill_id,
                       date=last_day - timedelta(days=10), amount=500_000.0, method="Cash", status="Completed"))
_s.commit()
_s.close()


def _login(cid: str, password: str | None = None):
    return client.post("/auth/login", json={"email": f"{cid.lower()}@example.com",
                                             "password": PASSWORDS[cid] if password is None else password})


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _reset_limits() -> None:
    try:
        importlib.import_module("app.core.rate_limit").reset_all()
    except ModuleNotFoundError:
        pass


# ---------------------------------------------------------------------------
def f1_risk() -> None:
    print("\n=== F1  Payment risk does not move with the calendar")
    from app.ai import risk

    db = SessionLocal()
    try:
        with wall_clock("2026-07-01"):
            early = {r["customer_id"]: r for r in risk.portfolio_summary(db)["customers"]}
        with wall_clock("2026-12-31"):
            summary = risk.portfolio_summary(db)
            late = {r["customer_id"]: r for r in summary["customers"]}
    finally:
        db.close()
    a, b = early[HISTORY], late[HISTORY]
    check("the same data scores the same on 1 July and 31 December",
          (a["score"], a["band"], a["days_since_payment"]) == (b["score"], b["band"], b["days_since_payment"]),
          f"1 Jul: {a['score']} {a['band']} {a['days_since_payment']} days; "
          f"31 Dec: {b['score']} {b['band']} {b['days_since_payment']} days")
    # The last payment (20 June) is after the newest reading (10 June): paid
    # recently, so zero days, not minus ten and not 194 days in December.
    check("recency is counted to the newest reading, not to today",
          b["days_since_payment"] == 0, f"days since payment: {b['days_since_payment']}")
    check("days since the last payment is never negative",
          all((r["days_since_payment"] or 0) >= 0 for r in late.values()),
          str(sorted(r["days_since_payment"] for r in late.values() if r["days_since_payment"] is not None)))
    check("the summary states the date it is counted to",
          str(summary.get("as_of")) == NEWEST_READING.isoformat(), f"as_of: {summary.get('as_of')}")
    admin = _login("REV-ADMIN")
    res = client.get("/analytics/risk", headers=_headers(admin.json()["token"]))
    check("GET /analytics/risk returns asOf", res.status_code == 200 and res.json().get("asOf") == NEWEST_READING.isoformat(),
          f"status {res.status_code}, asOf {res.json().get('asOf') if res.status_code == 200 else None}")


def f2_consumption() -> None:
    print("\n=== F2  The monthly series ends with the newest reading")
    from app.routers.consumption import monthly_series

    db = SessionLocal()
    try:
        with wall_clock("2026-10-13"):
            series = monthly_series(db, HISTORY, months=12)
            six = monthly_series(db, HISTORY, months=6)
            longest = monthly_series(db, HISTORY, months=24)
    finally:
        db.close()
    check("'last 12 months' holds 12 months in October 2026", len(series) == 12, f"{len(series)} months")
    check("the series ends in June 2026 and starts in July 2025",
          bool(series) and series[-1].get("period") == "2026-06" and series[0].get("period") == "2025-07",
          f"{series[0].get('period') if series else None} .. {series[-1].get('period') if series else None}")
    check("6 months are January to June 2026", [p.get("period") for p in six][:1] == ["2026-01"] and len(six) == 6,
          str([p.get("period") for p in six]))
    check("24 months stop at the 18 that exist", len(longest) == 18, f"{len(longest)} months")
    check("months keep their year (no two 'Jun' without one)",
          len({p.get("period") for p in longest}) == len(longest), str([p.get("period") for p in longest]))

    token = _login(HISTORY).json()["token"]
    with wall_clock("2026-10-13"):
        api = client.get("/consumption/monthly", params={"months": 12}, headers=_headers(token))
        sheet = client.get("/consumption/export", params={"months": 12, "format": "excel"}, headers=_headers(token))
    check("GET /consumption/monthly gives 12 months", api.status_code == 200 and len(api.json()) == 12,
          f"status {api.status_code}, {len(api.json()) if api.status_code == 200 else '-'} rows")
    period = ""
    if sheet.status_code == 200:
        from openpyxl import load_workbook

        period = str(load_workbook(io.BytesIO(sheet.content)).active["A2"].value or "")
    check("the statement covers 1 July 2025 to 10 June 2026",
          period.endswith("2025-07-01 to 2026-06-10"), f"status {sheet.status_code}, header '{period[-40:]}'")


def f3_sessions() -> None:
    print("\n=== F3  Changing the password signs out the other devices")
    _reset_limits()
    phone = _login("REV-0002").json()["token"]
    laptop = _login("REV-0002").json()["token"]
    new_password = secrets.token_urlsafe(12)
    res = client.post("/auth/change-password", headers=_headers(laptop),
                      json={"current_password": PASSWORDS["REV-0002"], "new_password": new_password})
    check("the change succeeds", res.status_code == 200, f"status {res.status_code}")
    PASSWORDS["REV-0002"] = new_password
    fresh = res.json().get("token") if res.status_code == 200 else None
    check("it returns a new token for the device that made it", bool(fresh))
    check("the other device is signed out", client.get("/auth/me", headers=_headers(phone)).status_code == 401)
    check("the old token on this device is retired too",
          client.get("/auth/me", headers=_headers(laptop)).status_code == 401)
    check("the new token works", bool(fresh) and client.get("/auth/me", headers=_headers(fresh)).status_code == 200)

    # A token from before session versions existed has no version and counts
    # as 0: nobody is signed out by the upgrade, only by a change after it.
    from jose import jwt

    legacy = jwt.encode({"sub": "REV-0003", "role": "customer",
                         "exp": datetime.now(UTC) + timedelta(hours=1), "iat": datetime.now(UTC)},
                        settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    check("a token without a version still works on an account never changed",
          client.get("/auth/me", headers=_headers(legacy)).status_code == 200)

    previous = settings.RETURN_RESET_TOKEN_IN_RESPONSE
    settings.RETURN_RESET_TOKEN_IN_RESPONSE = True
    try:
        signed_in = _login("REV-0003").json()["token"]
        reset_token = client.post("/auth/forgot-password", json={"email": "rev-0003@example.com"}).json().get("resetToken")
        PASSWORDS["REV-0003"] = secrets.token_urlsafe(12)
        done = client.post("/auth/reset-password", json={"token": reset_token, "new_password": PASSWORDS["REV-0003"]})
    finally:
        settings.RETURN_RESET_TOKEN_IN_RESPONSE = previous
    check("a reset succeeds", done.status_code == 200, f"status {done.status_code}")
    check("a reset signs out every session",
          client.get("/auth/me", headers=_headers(signed_in)).status_code == 401
          and client.get("/auth/me", headers=_headers(legacy)).status_code == 401)

    from scripts import portal_access

    token = _login("REV-0003").json()["token"]
    db = SessionLocal()
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            portal_access.revoke(db, "REV-0003")
    finally:
        db.close()
    check("revoking portal access ends the open session",
          client.get("/auth/me", headers=_headers(token)).status_code == 401)


def f4_forecast_report() -> None:
    print("\n=== F4  The Forecast Report names a backtest diagnostic")
    from app.reports import builder

    db = SessionLocal()
    try:
        report = builder.build(db, "forecast", date(2025, 1, 1), date(2026, 6, 30))
    finally:
        db.close()
    first_label = report.summary[0][0] if report.summary else ""
    check("the figure is labelled a backtest, not an accuracy",
          "backtest" in first_label.lower() and "not validated accuracy" in first_label.lower()
          and not first_label.lower().startswith("model accuracy"), first_label)
    limitation = ("Meters are read once a month over approximately ten days, so the weekly series contains "
                  "observations in only 42 of its 76 calendar weeks, at irregular intervals. Consequently, a "
                  "backtest on this series measures the effects of the reading schedule and does not establish "
                  "reliable demand-forecasting performance.")
    check("the report carries the approved limitation word for word", limitation in report.note, report.note[-120:])
    check("the description no longer promises accuracy", "accuracy" not in report.description.lower(), report.description)
    admin = _login("REV-ADMIN").json()["token"]
    catalogue = client.get("/reports", headers=_headers(admin))
    forecast = [r for r in catalogue.json() if r.get("id") == "forecast"] if catalogue.status_code == 200 else []
    check("GET /reports describes it the same way",
          bool(forecast) and "accuracy" not in forecast[0].get("description", "").lower(),
          str(forecast[0] if forecast else catalogue.status_code))


def f6_bill_alert() -> None:
    print("\n=== F6  The bill reminder quotes what is still owed")
    from app.ai import alerts

    db = SessionLocal()
    try:
        with wall_clock("2026-10-13"):
            first = [a for a in alerts.generate_alerts(db, HISTORY) if a["type"] == "payment"]
        with wall_clock("2026-10-20"):
            week_later = [a for a in alerts.generate_alerts(db, HISTORY) if a["type"] == "payment"]
    finally:
        db.close()
    message = first[0]["message"] if first else ""
    owed = f"{PART_PAID_AMOUNT - PART_PAID_RECEIVED:,.0f} LBP"
    check("an overdue reminder exists for the part-paid bill", bool(first), str(first))
    check("it quotes the amount still owed", owed in message, message)
    check("it does not quote the face value", f"{PART_PAID_AMOUNT:,.0f} LBP" not in message, message)
    check("it gives the due date, not a day count", "31 Mar 2025" in message and "days ago" not in message, message)
    check("a week later the stored wording is unchanged (no daily 'unread' again)",
          [a["message"] for a in first] == [a["message"] for a in week_later],
          f"{[a['message'] for a in week_later]}")


def f14_limits() -> None:
    print("\n=== F14  Repeated failures are answered with 429")
    _reset_limits()
    for _ in range(5):
        _login("REV-0002", "wrong-password")
    blocked = _login("REV-0002", "wrong-password")
    check("the sixth wrong password in 15 minutes is refused with 429", blocked.status_code == 429,
          f"status {blocked.status_code}")
    check("the refusal says when to try again", blocked.headers.get("retry-after", "").isdigit(),
          str(dict(blocked.headers).get("retry-after")))
    check("while blocked, even the right password waits", _login("REV-0002").status_code == 429)
    _reset_limits()
    for _ in range(4):
        _login("REV-0002", "wrong-password")
    check("the right password signs in after four mistakes", _login("REV-0002").status_code == 200)
    statuses = [_login("REV-0002", "wrong-password").status_code for _ in range(5)]
    check("and clears the count", statuses == [401] * 5, str(statuses))

    _reset_limits()
    refused = [client.post("/auth/register", json={
        "customer_id": "REV-0004", "registration_code": "WRONGCDE", "name": "Someone",
        "email": f"probe-{i}@example.com", "password": secrets.token_urlsafe(10)}).status_code for i in range(6)]
    check("the sixth refused registration for one Customer ID is refused with 429",
          refused[:5] == [400] * 5 and refused[5] == 429, str(refused))

    _reset_limits()
    sent = [client.post("/auth/forgot-password", json={"email": "rev-0002@example.com"}).status_code for _ in range(6)]
    check("the sixth reset request for one address in 15 minutes is refused with 429",
          sent[:5] == [200] * 5 and sent[5] == 429, str(sent))
    unknown = [client.post("/auth/forgot-password", json={"email": "nobody@example.com"}).status_code for _ in range(6)]
    check("an unknown address is limited the same way, so the limit reveals nothing",
          unknown == sent, str(unknown))

    _reset_limits()
    token = _login("REV-0002").json()["token"]
    wrong = [client.post("/auth/change-password", headers=_headers(token),
                         json={"current_password": "not-it", "new_password": secrets.token_urlsafe(10)}).status_code
             for _ in range(6)]
    check("the sixth wrong current password is refused with 429", wrong[:5] == [400] * 5 and wrong[5] == 429, str(wrong))
    _reset_limits()


def f15_signing_key() -> None:
    print("\n=== F15  A placeholder signing key is refused outside SQLite")
    # The default written in app/config.py, not whatever a local .env sets.
    placeholder = Settings.model_fields["JWT_SECRET_KEY"].default
    for key, expect_problem, label in (
        (placeholder, True, "the built-in default"),
        ("change-me-to-a-long-random-string", True, "the value in .env.example"),
        ("short-but-not-a-placeholder", True, "a key under 32 characters"),
        (secrets.token_urlsafe(48), False, "a random 64-character key"),
    ):
        problem = Settings(JWT_SECRET_KEY=key).jwt_secret_problem
        check(f"{label} is {'flagged' if expect_problem else 'accepted'}", bool(problem) == expect_problem, str(problem))

    main = importlib.import_module("app.main")
    real_url, real_key = settings.DATABASE_URL, settings.JWT_SECRET_KEY
    try:
        settings.DATABASE_URL = "postgresql+psycopg2://user@db.example.invalid:5432/production"
        settings.JWT_SECRET_KEY = placeholder
        try:
            main.check_jwt_secret()
            refused = False
        except RuntimeError:
            refused = True
        check("startup on PostgreSQL with the placeholder is refused", refused)
        settings.JWT_SECRET_KEY = secrets.token_urlsafe(48)
        main.check_jwt_secret()
        check("startup on PostgreSQL with a real key goes ahead", True)

        settings.DATABASE_URL = real_url
        settings.JWT_SECRET_KEY = placeholder
        records: list[logging.LogRecord] = []

        class _Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Collect()
        logging.getLogger("app.main").addHandler(handler)
        try:
            main.check_jwt_secret()
        finally:
            logging.getLogger("app.main").removeHandler(handler)
        check("on SQLite it starts, with a warning",
              any(r.levelno >= logging.WARNING and "JWT_SECRET_KEY" in r.getMessage() for r in records))
    finally:
        settings.DATABASE_URL, settings.JWT_SECRET_KEY = real_url, real_key


def f9_dashboard() -> None:
    print("\n=== F9  The executive dashboard says which day and month it shows")
    admin = _login("REV-ADMIN").json()["token"]
    res = client.get("/dashboard/admin", headers=_headers(admin))
    stats = res.json().get("stats", {}) if res.status_code == 200 else {}
    check("it states the day of the newest reading, not today", stats.get("asOf") == NEWEST_READING.isoformat(),
          f"status {res.status_code}, asOf {stats.get('asOf')}")
    check("the data is not presented as live", stats.get("isLive") is False, str(stats.get("isLive")))
    # The newest reading is 10 June 2026, so June is not complete: the
    # consumption card covers May, and has to say so.
    check("the consumption figure names its month: the newest complete one",
          stats.get("consumptionPeriod") == "2026-05", str(stats.get("consumptionPeriod")))
    check("and the figure is that month's", stats.get("monthlyConsumption") == 116.0, str(stats.get("monthlyConsumption")))


def f12_translation() -> None:
    print("\n=== F12  What the server writes reaches the reader in their language")
    from starlette.requests import Request

    from app.ai import alerts, recommender
    from app.core import i18n
    from app.core.i18n_messages import MESSAGES
    from app.models.alert import Alert

    def language_of(header: str | None) -> str:
        headers = [(b"accept-language", header.encode())] if header is not None else []
        return i18n.request_language(Request({"type": "http", "headers": headers}))

    cases = {"ar": "ar", "ar-LB,ar;q=0.9,en;q=0.8": "ar", "fr-CA": "fr", "zh-Hans-CN": "zh",
             "pt-BR, ja;q=0.5": "ja", "xx-YY": "en", "": "en", None: "en", "*": "en"}
    found = {header: language_of(header) for header in cases}
    check("Accept-Language gives the first language the platform has, else English", found == cases, str(found))

    i18n._compiled.cache_clear()
    try:
        i18n._compiled()
        problem = ""
    except ValueError as exc:
        problem = str(exc)
    check("every translation uses exactly the placeholders of its English", not problem, problem)
    check("every entry has all six translations",
          all(getattr(m, lang) for m in MESSAGES for lang in i18n.LANGUAGES[1:]))

    sentence = ("1 unpaid bill with 600,000 LBP still to pay. It was due on 31 Mar 2025. "
                "Please settle it to avoid a service interruption.")
    ar, de, zh = (i18n.localize(sentence, lang) for lang in ("ar", "de", "zh"))
    check("an English sentence comes back in Arabic", ar != sentence and bool(re.search("[\u0600-\u06FF]", ar)), ar)
    check("its amount is unchanged, kept left to right inside the Arabic",
          "\u2066600,000 LBP\u2069" in ar, repr(ar))
    check("its date is written in Arabic, with the Levantine month name", "31 آذار 2025" in ar, ar)
    check("in German the date is German, and nothing is isolated", "31. März 2025" in de and "\u2066" not in de, de)
    check("in Chinese the date is in Chinese order", "2025年3月31日" in zh, zh)
    check("English is returned as written", i18n.localize(sentence, "en") == sentence)
    check("a sentence with no entry is returned unchanged, not broken",
          i18n.localize("A sentence nobody wrote.", "ar") == "A sentence nobody wrote.")
    check("a language the platform does not have means English", i18n.localize(sentence, "pt") == sentence)
    forms = {n: i18n.localize(f"{n} days ago", "ar") for n in (2, 5, 11, 100)}
    check("Arabic gives a counted noun the form its number needs",
          forms == {2: "قبل يومين", 5: "قبل 5 أيام", 11: "قبل 11 يوماً", 100: "قبل 100 يوم"}, str(forms))

    db = SessionLocal()
    try:
        with wall_clock("2026-10-13"):
            written = alerts.generate_alerts(db, HISTORY)
        advice = recommender.generate_recommendations(db, HISTORY)
    finally:
        db.close()
    texts = [a["title"] for a in written] + [a["message"] for a in written] \
        + [r["title"] for r in advice] + [r["description"] for r in advice]
    missing = [text for text in texts if not i18n.is_translated(text)]
    check("every alert and recommendation written for the test account has a translation",
          bool(texts) and not missing, "; ".join(missing)[:300] or "nothing was written")

    token = _login(HISTORY).json()["token"]
    with wall_clock("2026-10-13"):
        english = client.post("/alerts/refresh", headers=_headers(token))
    arabic = client.get("/alerts", headers={**_headers(token), "Accept-Language": "ar"})
    check("GET /alerts answers in Arabic when asked",
          arabic.status_code == 200 and bool(arabic.json())
          and all(re.search("[\u0600-\u06FF]", a["message"]) for a in arabic.json()),
          str([a["message"][:60] for a in arabic.json()]) if arabic.status_code == 200 else str(arabic.status_code))
    db = SessionLocal()
    try:
        stored = {row.message for row in db.query(Alert).filter(Alert.customer_id == HISTORY)}
    finally:
        db.close()
    check("the stored alerts stay in English, so any language can be chosen later",
          english.status_code == 200 and stored == {a["message"] for a in english.json()}, str(stored)[:200])

    refused = client.post("/auth/login", json={"email": "rev-0001@example.com", "password": "not-the-password"})
    check("a refusal is a fixed sentence the interface can translate",
          refused.status_code == 401 and refused.json().get("detail") == "Invalid credentials", refused.text[:120])
    admin = _login("REV-ADMIN").json()["token"]
    duplicate = client.post("/customers", headers=_headers(admin), json={
        "customer_id": HISTORY, "name": "Someone Else", "email": "someone-else@example.com"})
    check("a duplicate Customer ID is refused in fixed words",
          duplicate.status_code == 409 and duplicate.json().get("detail") == "This Customer ID is already in use",
          duplicate.text[:160])
    _reset_limits()


# Packages used without being imported by name, and the import name of the
# ones whose distribution name differs from it.
_USED_INDIRECTLY = {
    "uvicorn": "the server that runs the app",
    "email-validator": "pydantic's EmailStr",
    "python-dotenv": "pydantic-settings reading backend/.env",
    "psycopg2-binary": "SQLAlchemy's driver for postgresql+psycopg2:// URLs",
}
_IMPORT_NAME = {"scikit-learn": "sklearn", "python-jose": "jose", "psycopg2-binary": "psycopg2",
                "pydantic-settings": "pydantic_settings", "sqlalchemy": "sqlalchemy"}


def f16_requirements() -> None:
    print("\n=== F16  Only packages the code uses")
    text = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    names = sorted({re.split(r"[\[=<>!~ ]", line.strip())[0].lower()
                    for line in text.splitlines() if line.strip() and not line.strip().startswith("#")})
    for unused in ("alembic", "joblib", "python-multipart"):
        check(f"{unused} is not required (nothing imports it)", unused not in names, ", ".join(names))
    sources = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                        for folder in ("app", "scripts", "tests") for p in (BACKEND / folder).rglob("*.py"))
    unexplained = []
    for name in names:
        if name in _USED_INDIRECTLY:
            continue
        module = _IMPORT_NAME.get(name, name.replace("-", "_"))
        if not re.search(rf"^\s*(?:import|from)\s+{re.escape(module)}\b", sources, re.M):
            unexplained.append(name)
    check("every other requirement is imported somewhere", not unexplained, ", ".join(unexplained))


def old_database() -> None:
    print("\n=== Update  The helper scripts work on a database from before this change")
    import sqlite3
    import subprocess

    # The current schema with the three customer columns this change adds taken
    # away again: a database as it stood before the update, which the server
    # has not opened since.
    old = os.path.join(_TMP, "before-the-update.db")
    shutil.copyfile(_DB_URL.removeprefix("sqlite:///"), old)
    added = ("session_version", "registration_code_hash", "registration_code_expires_at")
    con = sqlite3.connect(old)
    try:
        for column in added:
            con.execute(f"ALTER TABLE customers DROP COLUMN {column}")
        con.commit()
    finally:
        con.close()
    # The child process is pointed at the copy by DATABASE_URL, which takes
    # precedence over anything in backend/.env (pydantic-settings).
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + old, "PYTHONDONTWRITEBYTECODE": "1"}
    run = subprocess.run([sys.executable, "-m", "scripts.data_provenance"], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=300)
    check("the data report (check-data.bat, purge-demo.bat) runs on it", run.returncode == 0,
          (run.stderr or run.stdout)[-200:])
    con = sqlite3.connect(old)
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(customers)")}
    finally:
        con.close()
    check("and first adds the columns the code expects, as the server does", set(added) <= columns,
          str(sorted(set(added) - columns)))

    # Every script that reads whole customer records does the same, so the
    # next one written cannot forget it unnoticed.
    reads = re.compile(r"\.query\(Customer\)|\.get\(Customer,")
    forgetful = [p.name for p in sorted((BACKEND / "scripts").glob("*.py"))
                 if reads.search(text := p.read_text(encoding="utf-8"))
                 and "add_missing_columns()" not in text and "create_all_tables()" not in text]
    check("every script that reads customer records adds the new columns first", not forgetful,
          ", ".join(forgetful))


def readings_by_density() -> None:
    print("\n=== Density  Monthly figures follow how often the meter is read")
    from app.ai import alerts, recommender
    from app.analytics import asof
    from app.models.alert import Alert
    from app.models.recommendation import Recommendation

    # Two more synthetic accounts, removed again at the end so no other section
    # sees them. REV-0005 reports every hour for forty days; REV-0006 is read by
    # hand once a month, on whatever day the reader came, and its newest
    # reading is on the 8th.
    hourly, monthly = "REV-0005", "REV-0006"
    readings = [("2025-04-10", 450), ("2025-05-09", 450), ("2025-06-08", 300), ("2025-07-09", 450),
                ("2025-08-08", 450), ("2025-09-08", 450), ("2025-10-09", 450), ("2025-11-08", 450),
                ("2025-12-09", 450), ("2026-01-09", 450), ("2026-02-09", 450), ("2026-03-12", 900),
                ("2026-04-10", 450), ("2026-05-09", 450), ("2026-06-08", 450)]
    db = SessionLocal()
    try:
        db.add_all([_account(hourly), _account(monthly)])
        db.flush()
        start = datetime(2026, 5, 2)
        db.add_all([Consumption(customer_id=hourly, timestamp=start + timedelta(hours=h), kwh=0.5, cost=500.0)
                    for h in range(40 * 24)])
        db.add_all([Consumption(customer_id=monthly, timestamp=datetime.fromisoformat(day), kwh=float(kwh),
                                cost=1000.0 * kwh) for day, kwh in readings])
        db.commit()

        check("an hourly meter counts as read daily", asof.has_daily(db, hourly) is True)
        check("a meter read once a month does not", asof.has_daily(db, monthly) is False)
        token = _login(hourly).json()["token"]
        daily = client.get("/consumption/daily", params={"days": 30}, headers=_headers(token))
        rows = daily.json() if daily.status_code == 200 else []
        check("the hourly customer gets a daily chart: 30 days of 12 kWh",
              len(rows) == 30 and all(r["kwh"] == 12.0 for r in rows),
              f"status {daily.status_code}, {len(rows)} days, first {rows[:1]}")

        # The 90-day window before 8 June holds four of REV-0006's readings
        # (12 March to 8 June). Their sum divided by three said 750 kWh a month.
        window = recommender._load_readings(db, monthly)
        check("the 90-day window holds four monthly readings", len(window) == 4, str(len(window)))
        monthly_figure = getattr(recommender, "_monthly_kwh", None)
        figure = monthly_figure(db, monthly, window) if monthly_figure else float(window["kwh"].sum()) / 3
        check("the monthly figure is the mean of the newest three readings (450 kWh)", figure == 450.0, str(figure))
        recs = recommender.generate_recommendations(db, monthly)
        titles = [r["title"] for r in recs]
        check("no 'upper consumption band' advice for 450 kWh a month",
              "Replace remaining incandescent bulbs with LEDs" not in titles, str(titles))
        check("the savings estimate is 3% of 450 kWh at 1,000 LBP (13,500 LBP)",
              [r["estimated_savings"] for r in recs] == [13500.0],
              str([(r["title"], r["estimated_savings"]) for r in recs]))
        if monthly_figure:
            hourly_figure = monthly_figure(db, hourly, recommender._load_readings(db, hourly))
            check("the hourly customer's figure is its 90 days divided by three (160 kWh)",
                  abs(hourly_figure - 40 * 24 * 0.5 / 3) < 1e-9, str(hourly_figure))

        usage = [a for a in alerts.generate_alerts(db, monthly) if a["type"] == "high-usage"]
        message = usage[0]["message"] if usage else ""
        check("the usage alert names its day as people write it (8 Jun 2026, not 08 Jun 2026)",
              "in the month to 8 Jun 2026" in message and "08 Jun" not in message, message)
    finally:
        db.rollback()
        for model in (Consumption, Alert, Recommendation):
            db.query(model).filter(model.customer_id.in_([hourly, monthly])).delete(synchronize_session=False)
        db.query(Customer).filter(Customer.customer_id.in_([hourly, monthly])).delete(synchronize_session=False)
        db.commit()
        db.close()


def segments_by_anchor() -> None:
    print("\n=== Anchor  Customer segments do not move with the calendar")
    from app.ai import segmentation
    from app.models.anomaly import Anomaly  # noqa: F401 - imported so the mapper is configured

    # Two accounts whose signup dates straddle the two-year mark measured from
    # the data's newest reading (10 June 2026): REV-0007 joined 23 months
    # before it, REV-0008 25 months before it. Only REV-0008 is "Loyal".
    older, newer = "REV-0007", "REV-0008"
    db = SessionLocal()
    try:
        a, b = _account(older), _account(newer)
        a.created_at = datetime(2024, 5, 10)   # 25 months before the newest reading
        b.created_at = datetime(2024, 7, 10)   # 23 months before it
        db.add_all([a, b])
        # A reading each, so the accounts take part in the clustering.
        db.add_all([Consumption(customer_id=older, timestamp=datetime(2026, 6, 10), kwh=400.0, cost=4e5),
                    Consumption(customer_id=newer, timestamp=datetime(2026, 6, 10), kwh=400.0, cost=4e5)])
        db.commit()

        def loyal_count(day: str) -> int:
            with wall_clock(day):
                segs = {s["name"]: s["count"] for s in segmentation.generate_segments(db)}
            return segs.get("Loyal Customers", 0)

        # The newest reading is 10 June 2026, so the anchor is that day whatever
        # the wall clock. The count is the same in October and two years on.
        october = loyal_count("2026-10-18")
        two_years_on = loyal_count("2028-10-18")
        check("the Loyal Customers count does not change as the calendar moves",
              october == two_years_on, f"18 Oct 2026: {october}; 18 Oct 2028: {two_years_on}")
        # Counted to the newest reading: the 25-month account is loyal, the
        # 23-month one is not. Counted to today, both would be, years early.
        with wall_clock("2026-10-18"):
            segs = {s["name"]: s["count"] for s in segmentation.generate_segments(db)}
            frame = segmentation.build_feature_frame(db)
        tenure = dict(zip(frame["customer_id"], frame["tenure_days"]))
        check("tenure is counted to the newest reading, not to today",
              759 <= tenure[older] <= 761 and 699 <= tenure[newer] <= 701,
              f"{older}: {tenure[older]} days; {newer}: {tenure[newer]} days")
        check("only the account past two years of tenure at the anchor is Loyal",
              segs.get("Loyal Customers", 0) == 1, str(segs.get("Loyal Customers", 0)))
    finally:
        db.rollback()
        db.query(Consumption).filter(Consumption.customer_id.in_([older, newer])).delete(synchronize_session=False)
        db.query(Customer).filter(Customer.customer_id.in_([older, newer])).delete(synchronize_session=False)
        db.commit()
        db.close()


def main() -> int:
    for name, group in (("F1", f1_risk), ("F2", f2_consumption), ("F3", f3_sessions), ("F4", f4_forecast_report),
                        ("F6", f6_bill_alert), ("F9", f9_dashboard), ("F12", f12_translation),
                        ("F14", f14_limits), ("F15", f15_signing_key), ("F16", f16_requirements),
                        ("Update", old_database), ("Density", readings_by_density),
                        ("Anchor", segments_by_anchor)):
        attempt(f"{name}: the checks ran to the end", group)

    print("\n" + "=" * 64)
    print(f"  PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
    print("=" * 64)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
