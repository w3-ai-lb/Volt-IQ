"""
Security checks: password verification, account claiming, password-reset tokens,
deactivated accounts, the seeder's database guard, and the two account scripts.

    python -m tests.test_security

IT CANNOT REACH A REAL DATABASE
-------------------------------
Before anything from the application is imported, DATABASE_URL is pointed at a
new SQLite file in a temporary folder, and the run stops if the settings do not
show that file. The folder is deleted when the run ends. Every account is
synthetic: IDs start with SEC-, names are invented, addresses use example.com,
and passwords and codes are generated for this run and never printed.

Same custom runner as tests/test_api.py: PASS and FAIL lines, a summary, and
exit status 1 when anything fails. A FAIL line says what was observed instead.
"""

from __future__ import annotations

import atexit
import csv
import importlib
import io
import logging
import os
import re
import secrets
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta

_TMP = tempfile.mkdtemp(prefix="security-test-")
_DB_URL = "sqlite:///" + os.path.join(_TMP, "security.db")
os.environ["DATABASE_URL"] = _DB_URL
os.environ.pop("RETURN_RESET_TOKEN_IN_RESPONSE", None)
atexit.register(lambda: shutil.rmtree(_TMP, ignore_errors=True))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import Settings, settings  # noqa: E402

if settings.DATABASE_URL != _DB_URL:  # the guard this file depends on
    print("STOP: the settings do not point at the temporary test database.")
    sys.exit(2)

from app.core.security import generate_reset_token, hash_password, verify_password  # noqa: E402
from app.database import SessionLocal, create_all_tables, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.password_reset import PasswordResetToken  # noqa: E402

create_all_tables()
client = TestClient(app)

PASSED: list[str] = []
FAILED: list[str] = []
NON_SQLITE_URL = "postgresql+psycopg2://user@db.example.invalid:5432/production"
NOW = datetime.now(UTC).replace(tzinfo=None)


def check(name: str, condition: bool, observed: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}" + (f"   [observed: {observed}]" if observed else ""))


def _pw() -> str:
    return secrets.token_urlsafe(12)


def _summary(resp) -> str:
    """Status code and the NAMES of the fields returned, never their values."""
    try:
        body = resp.json()
    except ValueError:
        return f"status {resp.status_code}, non-JSON body"
    if not isinstance(body, dict):
        return f"status {resp.status_code}"
    text = f"status {resp.status_code}, fields: {', '.join(sorted(body)) or 'none'}"
    user = body.get("user")
    if isinstance(user, dict):
        text += "; user fields with a value: " + ", ".join(sorted(k for k, v in user.items() if v))
    return text


def _status_of(cid: str) -> tuple[str, bool]:
    s = SessionLocal()
    try:
        c = s.get(Customer, cid)
        return (c.status, bool(c.password_hash)) if c else ("missing", False)
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Synthetic accounts
# ---------------------------------------------------------------------------
PASSWORDS: dict[str, str] = {}


def _account(cid: str, role: str = "customer", claimed: bool = False, status: str = "Active") -> Customer:
    PASSWORDS[cid] = _pw() if claimed else ""
    return Customer(
        customer_id=cid,
        name=f"Synthetic {cid}",
        email=f"{cid.lower()}@example.com",
        password_hash=hash_password(PASSWORDS[cid]) if claimed else "",
        role=role,
        status=status,
        phone="+000 0000 0000",
        address="1 Example Street",
        region="Test",
        plan="Residential",
    )


_session = SessionLocal()
_session.add_all([
    _account("SEC-ADMIN", role="admin", claimed=True),
    _account("SEC-0001"),                          # issued a code, then claims with it
    _account("SEC-0002", claimed=True),            # already registered
    _account("SEC-0003", status="Suspended"),      # deactivated and never registered
    _account("SEC-0004", claimed=True, status="Inactive"),
    _account("SEC-0005", status=""),               # loaded without a status
    _account("SEC-0006"),                          # holds a code that has expired
    _account("SEC-0007"),                          # target of scripts/portal_access.py
    _account("SEC-0008"),                          # target of scripts/issue_registration_codes.py
    _account("SEC-0009"),                          # claims with a code typed loosely
    _account("SEC-0010"),                          # claim attempted with the Customer ID alone
])
_session.commit()
_session.close()


def _login(email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def _register(cid: str, code: str | None = None, email: str | None = None):
    body = {
        "customer_id": cid,
        "name": "Synthetic Claimant",
        "email": email or f"claimant-{secrets.token_hex(4)}@example.com",
        "password": _pw(),
    }
    if code is not None:
        body["registration_code"] = code
    return client.post("/auth/register", json=body)


def _store_code(cid: str, code: str, expires_at: datetime) -> bool:
    """Put a code on an account directly, as if it had been issued earlier."""
    if not hasattr(Customer, "registration_code_hash"):
        return False
    from app.core import registration_codes

    s = SessionLocal()
    try:
        c = s.get(Customer, cid)
        c.registration_code_hash = hash_password(registration_codes.normalize(code))
        c.registration_code_expires_at = expires_at
        s.commit()
        return True
    finally:
        s.close()


def _issue(cid: str, headers: dict) -> tuple[object, str | None]:
    r = client.post(f"/customers/{cid}/registration-code", headers=headers)
    code = None
    if r.status_code in (200, 201):
        try:
            code = r.json().get("registrationCode")
        except ValueError:
            code = None
    return r, code


def main() -> int:
    # --- Password verification --------------------------------------------
    print("\n=== Password verification ===")
    check("an empty stored hash never verifies", verify_password(_pw(), "") is False)
    check("a bare bcrypt prefix never verifies", verify_password(_pw(), "$2b$12$") is False)
    check("a malformed hash never verifies", verify_password(_pw(), "not-a-bcrypt-hash") is False)
    r = _login("sec-0010@example.com", _pw())
    check("signing in to a never-registered account is refused (401)", r.status_code == 401, _summary(r))

    admin = _login("sec-admin@example.com", PASSWORDS["SEC-ADMIN"])
    check("the synthetic administrator signs in", admin.status_code == 200, _summary(admin))
    admin_h = {"Authorization": f"Bearer {admin.json().get('token', '')}"}
    cust = _login("sec-0002@example.com", PASSWORDS["SEC-0002"])
    cust_h = {"Authorization": f"Bearer {cust.json().get('token', '')}"}

    # --- Claiming an account ----------------------------------------------
    print("\n=== Claiming an account ===")
    only_id = _register("SEC-0010")
    check("a claim with only the Customer ID is refused (400)", only_id.status_code == 400, _summary(only_id))
    body = only_id.json() if only_id.headers.get("content-type", "").startswith("application/json") else {}
    check("a refused claim returns no account details", not body.get("user"), _summary(only_id))
    status, claimed = _status_of("SEC-0010")
    check("the account stays unregistered after that attempt", not claimed, "the account now has a password")

    r, code = _issue("SEC-0001", admin_h)
    check("an administrator can issue a one-time registration code (201)", r.status_code == 201 and bool(code), _summary(r))
    check("the code is 8 characters long", bool(code) and len(code) == 8, f"length {len(code) if code else 0}")
    s = SessionLocal()
    try:
        c = s.get(Customer, "SEC-0001")
        stored = getattr(c, "registration_code_hash", None)
        expires = getattr(c, "registration_code_expires_at", None)
    finally:
        s.close()
    check("the code is stored as a bcrypt hash, never in plain text",
          bool(stored) and bool(code) and code not in stored and stored.startswith("$2"),
          "nothing stored" if not stored else "stored value is not a bcrypt hash")
    check("the code expires 30 days after issue",
          expires is not None and timedelta(days=29, hours=23) < expires - NOW <= timedelta(days=30, minutes=5),
          f"expires {expires - NOW} from now" if expires else "no expiry stored")

    wrong_code = "ABCDEFGH" if code != "ABCDEFGH" else "HGFEDCBA"
    wrong = _register("SEC-0001", code=wrong_code)
    check("a wrong code is refused (400)", wrong.status_code == 400, _summary(wrong))
    missing = _register("SEC-0001")
    check("a missing code is refused (400)", missing.status_code == 400, _summary(missing))
    ok = _register("SEC-0001", code=code or "NOCODE00", email="claimed-0001@example.com")
    check("the correct code claims the account (201)", bool(code) and ok.status_code == 201,
          _summary(ok) if code else f"no code could be issued; the claim itself gave {_summary(ok)}")
    check("the claim signs the customer in to that account",
          bool(code) and ok.status_code == 201 and ok.json().get("user", {}).get("id") == "SEC-0001")
    reuse = _register("SEC-0001", code=code or "NOCODE00")
    check("the same code cannot be used a second time (400)", reuse.status_code == 400, _summary(reuse))
    s = SessionLocal()
    try:
        after = getattr(s.get(Customer, "SEC-0001"), "registration_code_hash", "not supported")
    finally:
        s.close()
    check("a used code is removed from the account", after is None,
          "this version has no registration codes" if after == "not supported" else "the code is still stored")

    r9, code9 = _issue("SEC-0009", admin_h)
    loose = (code9[:4].lower() + "-" + code9[4:].lower()) if code9 else "nocode-00"
    typed = _register("SEC-0009", code=loose)
    check("a code typed in lower case with a dash is accepted (201)", bool(code9) and typed.status_code == 201,
          _summary(typed) if code9 else f"no code could be issued; the claim itself gave {_summary(typed)}")

    unknown = _register("SEC-9999", code="ABCDEFGH")
    check("an unknown Customer ID is refused (400)", unknown.status_code == 400, _summary(unknown))
    check("the refusal does not repeat the Customer ID", "SEC-9999" not in unknown.text,
          "the message echoes the ID")
    registered = _register("SEC-0002", code="ABCDEFGH")
    check("an already-registered account is refused (400)", registered.status_code == 400, _summary(registered))
    admin_claim = _register("SEC-ADMIN", code="ABCDEFGH")
    check("an administrator account cannot be claimed (400)", admin_claim.status_code == 400, _summary(admin_claim))

    d_code = "K7M2QX9P"
    _store_code("SEC-0003", d_code, NOW + timedelta(days=10))
    deactivated = _register("SEC-0003", code=d_code)
    check("a deactivated account cannot be claimed, even with a valid code (400)",
          deactivated.status_code == 400, _summary(deactivated))
    status, claimed = _status_of("SEC-0003")
    check("registration never reactivates a deactivated account", status == "Suspended" and not claimed,
          f"status is now {status}, registered: {claimed}")

    e_code = "P9XQ2M7K"
    _store_code("SEC-0006", e_code, NOW - timedelta(minutes=1))
    expired = _register("SEC-0006", code=e_code)
    check("an expired code is refused (400)", expired.status_code == 400, _summary(expired))

    r5, code5 = _issue("SEC-0005", admin_h)
    clash = _register("SEC-0005", code=code5 or "NOCODE00", email="sec-0002@example.com")
    check("an email already used by another account is refused (400)", clash.status_code == 400, _summary(clash))
    fine5 = _register("SEC-0005", code=code5 or "NOCODE00", email="claimed-0005@example.com")
    check("after that refusal the same code still works with a free email (201)",
          bool(code5) and fine5.status_code == 201,
          _summary(fine5) if code5 else f"no code could be issued; the claim itself gave {_summary(fine5)}")
    status, _ = _status_of("SEC-0005")
    check("an account loaded without a status becomes Active when claimed", status == "Active", f"status {status!r}")

    refusals = [only_id, wrong, missing, reuse, unknown, registered, admin_claim, deactivated, expired, clash]
    answers = {(x.status_code, x.text) for x in refusals}
    check("every refusal gives the same status and the same message", len(answers) == 1,
          f"{len(answers)} different answers; statuses {sorted({x.status_code for x in refusals})}")

    print("\n=== Issuing codes ===")
    r = client.post("/customers/SEC-0002/registration-code", headers=admin_h)
    check("no code for an account that is already registered (409)", r.status_code == 409, _summary(r))
    r = client.post("/customers/SEC-0003/registration-code", headers=admin_h)
    check("no code for a deactivated account (400)", r.status_code == 400, _summary(r))
    r = client.post("/customers/SEC-ADMIN/registration-code", headers=admin_h)
    check("no code for an administrator account (400)", r.status_code == 400, _summary(r))
    r = client.post("/customers/SEC-0010/registration-code", headers=cust_h)
    check("a customer cannot issue codes (403)", r.status_code == 403, _summary(r))
    r = client.post("/customers/SEC-0010/registration-code")
    check("issuing a code needs a sign-in (401)", r.status_code == 401, _summary(r))

    # --- Password-reset tokens --------------------------------------------
    print("\n=== Password-reset tokens ===")
    default = Settings.model_fields["RETURN_RESET_TOKEN_IN_RESPONSE"].default
    check("reset tokens are not returned in responses by default", default is False, f"the default is {default}")
    settings.RETURN_RESET_TOKEN_IN_RESPONSE = default
    r = client.post("/auth/forgot-password", json={"email": "sec-admin@example.com"})
    token = r.json().get("resetToken") if r.status_code == 200 else None
    check("forgot-password for the administrator returns no token (default settings)",
          r.status_code == 200 and not token, _summary(r))
    taken_over = False
    if token:
        new_pw = _pw()
        rr = client.post("/auth/reset-password", json={"token": token, "new_password": new_pw})
        taken_over = rr.status_code == 200 and _login("sec-admin@example.com", new_pw).status_code == 200
        if taken_over:
            PASSWORDS["SEC-ADMIN"] = new_pw
    check("nobody can take over the administrator account through password reset", not taken_over,
          "the token in the reply reset the administrator's password, and the new password signs in")

    settings.RETURN_RESET_TOKEN_IN_RESPONSE = True
    r = client.post("/auth/forgot-password", json={"email": "sec-0002@example.com"})
    check("with the demo flag on and SQLite, the token is returned (local demo only)",
          bool(r.json().get("resetToken")), _summary(r))

    real_url = settings.DATABASE_URL
    settings.DATABASE_URL = NON_SQLITE_URL
    try:
        r = client.post("/auth/forgot-password", json={"email": "sec-0002@example.com"})
        check("with the demo flag on and a non-SQLite database, no token is returned",
              not r.json().get("resetToken"), _summary(r))
        records: list[logging.LogRecord] = []

        class _Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        handler = _Collect()
        main_logger = logging.getLogger("app.main")
        main_logger.addHandler(handler)
        # A real signing key for this one call: on a non-SQLite database the
        # server now refuses to start with the placeholder, which is checked
        # in tests/test_review_fixes.py. This check is about the reset flag.
        real_key = settings.JWT_SECRET_KEY
        settings.JWT_SECRET_KEY = secrets.token_urlsafe(48)
        try:
            importlib.import_module("app.main").on_startup()
        finally:
            settings.JWT_SECRET_KEY = real_key
            main_logger.removeHandler(handler)
        warned = any(x.levelno >= logging.WARNING and "RETURN_RESET_TOKEN_IN_RESPONSE" in x.getMessage()
                     for x in records)
        check("startup warns when the flag is set against a non-SQLite database", warned,
              f"{len(records)} log lines at startup, none of them a warning about the flag")
    finally:
        settings.DATABASE_URL = real_url

    r = client.post("/auth/forgot-password", json={"email": "sec-0002@example.com"})
    token = r.json().get("resetToken")
    check("a made-up token is refused (400)",
          client.post("/auth/reset-password", json={"token": "not-a-real-token", "new_password": _pw()}).status_code == 400)
    if token:
        PASSWORDS["SEC-0002"] = _pw()
        first = client.post("/auth/reset-password", json={"token": token, "new_password": PASSWORDS["SEC-0002"]})
        check("a valid token resets the password once (200)", first.status_code == 200, _summary(first))
        again = client.post("/auth/reset-password", json={"token": token, "new_password": _pw()})
        check("the same token is refused the second time (400)", again.status_code == 400, _summary(again))
    else:
        check("a valid token resets the password once (200)", False, "no token was issued with the flag on")
    plain, digest = generate_reset_token()
    s = SessionLocal()
    try:
        s.add(PasswordResetToken(customer_id="SEC-0002", token_hash=digest, expires_at=NOW - timedelta(minutes=1)))
        s.commit()
    finally:
        s.close()
    stale = client.post("/auth/reset-password", json={"token": plain, "new_password": _pw()})
    check("an expired token is refused (400)", stale.status_code == 400, _summary(stale))
    settings.RETURN_RESET_TOKEN_IN_RESPONSE = default

    # --- Deactivated accounts ---------------------------------------------
    print("\n=== Deactivated accounts ===")
    r = _login("sec-0004@example.com", PASSWORDS["SEC-0004"])
    check("a deactivated account cannot sign in (403)", r.status_code == 403, _summary(r))
    live = _login("sec-0002@example.com", PASSWORDS["SEC-0002"])
    live_h = {"Authorization": f"Bearer {live.json().get('token', '')}"}
    s = SessionLocal()
    try:
        s.get(Customer, "SEC-0002").status = "Suspended"
        s.commit()
    finally:
        s.close()
    r = client.get("/auth/me", headers=live_h)
    check("a token stops working once its account is deactivated (403)", r.status_code == 403, _summary(r))

    # --- The seeder's database guard --------------------------------------
    print("\n=== Seeder guard ===")
    seed = importlib.import_module("app.pipeline.seed")

    class _Reached(Exception):
        pass

    touched: list[str] = []

    def _probe(name: str):
        def stop(*_a, **_k):
            touched.append(name)
            raise _Reached(name)
        return stop

    saved = (seed.create_all_tables, seed.reset_database, seed.SessionLocal, list(sys.argv))
    seed.create_all_tables, seed.reset_database, seed.SessionLocal = (
        _probe("create_all_tables"), _probe("reset_database"), _probe("SessionLocal"))
    settings.DATABASE_URL = NON_SQLITE_URL
    try:
        for argv, want in ((["seed", "--reset"], "refused"), (["seed", "--reset", "--allow-non-sqlite"], "ran")):
            touched.clear()
            sys.argv = argv
            try:
                outcome = "refused" if seed.main() == 2 else "returned"
            except _Reached:
                outcome = "ran"
            except SystemExit as exc:
                outcome = f"exited {exc.code}"
            if want == "refused":
                check("the seeder refuses a non-SQLite database, --reset included",
                      outcome == "refused" and not touched,
                      f"it {outcome}; first database step reached: {touched[0] if touched else 'none'}")
            else:
                check("--allow-non-sqlite lets it run against a disposable test database", outcome == "ran",
                      f"it {outcome}")
    finally:
        seed.create_all_tables, seed.reset_database, seed.SessionLocal, sys.argv = (
            saved[0], saved[1], saved[2], saved[3])
        settings.DATABASE_URL = real_url

    # --- scripts/portal_access.py (no built-in password) -------------------
    print("\n=== Portal-access script ===")
    pa = importlib.import_module("scripts.portal_access")
    check("the script has no built-in default password", not hasattr(pa, "DEFAULT_PASSWORD"),
          "DEFAULT_PASSWORD is still defined")

    def _run(module, argv: list[str]) -> tuple[object, str]:
        buf = io.StringIO()
        saved_argv = list(sys.argv)
        sys.argv = argv
        try:
            with redirect_stdout(buf):
                try:
                    code = module.main()
                except SystemExit as exc:
                    code = exc.code
        finally:
            sys.argv = saved_argv
        return code, buf.getvalue()

    _, helptext = _run(pa, ["portal_access", "--help"])
    check("its help text shows no default password", "default:" not in helptext.lower(),
          "the --password help still names a default")
    chosen = _pw()
    rc, _ = _run(pa, ["portal_access", "SEC-0007", "--password", chosen])
    check("a chosen password is set (exit 0)", rc == 0, f"exit {rc}")
    check("the account signs in with the chosen password",
          _login("sec-0007@example.com", chosen).status_code == 200)
    generated = []
    for _ in range(2):
        rc, out = _run(pa, ["portal_access", "SEC-0007"])
        found = re.search(r"Password\s+(\S+)", out)
        generated.append(found.group(1) if (rc == 0 and found) else None)
    first_gen = generated[0]
    check("without --password, a new random password is set and shown once (exit 0)",
          bool(first_gen) and first_gen != getattr(pa, "DEFAULT_PASSWORD", None),
          "the built-in default was used" if first_gen else "no password was shown")
    check("each run generates a different password", bool(first_gen) and generated[0] != generated[1],
          "both runs set the same password")
    check("generated passwords are at least 12 characters", bool(first_gen) and len(first_gen) >= 12,
          f"length {len(first_gen) if first_gen else 0}")
    check("the generated password signs in",
          bool(generated[1]) and _login("sec-0007@example.com", generated[1]).status_code == 200)
    rc, _ = _run(pa, ["portal_access", "SEC-0007", "--password", "abc"])
    check("a password shorter than 6 characters is refused (exit 1)", rc == 1, f"exit {rc}")

    # --- scripts/issue_registration_codes.py ------------------------------
    print("\n=== Registration-code script ===")
    try:
        irc = importlib.import_module("scripts.issue_registration_codes")
    except ImportError:
        irc = None
    check("the issuing script exists", irc is not None, "scripts/issue_registration_codes.py not found")
    if irc is not None:
        out_csv = os.path.join(_TMP, "codes.csv")
        rc, out = _run(irc, ["issue_registration_codes", "--out", out_csv, "SEC-0008", "SEC-0002", "SEC-0003"])
        rows = list(csv.DictReader(open(out_csv, encoding="utf-8-sig"))) if os.path.exists(out_csv) else []
        check("it writes a CSV with a code for each eligible account only",
              rc == 0 and [x["customer_id"] for x in rows] == ["SEC-0008"],
              f"exit {rc}, rows for {[x['customer_id'] for x in rows]}")
        starts = open(out_csv, "rb").read(3) if os.path.exists(out_csv) else b""
        check("the CSV starts with the UTF-8 mark that Excel needs to show Arabic names",
              starts == b"\xef\xbb\xbf", repr(starts))
        check("its console output contains no code",
              bool(rows) and rows[0]["registration_code"] not in out, "a code was printed")
        claim8 = _register("SEC-0008", code=rows[0]["registration_code"]) if rows else None
        check("a code from the CSV claims its account (201)",
              claim8 is not None and claim8.status_code == 201, _summary(claim8) if claim8 else "no row")
        rc, _ = _run(irc, ["issue_registration_codes", "--out", out_csv, "SEC-0010"])
        check("it will not overwrite an existing CSV without --force", rc not in (0, None), f"exit {rc}")

    print("\n" + "=" * 64)
    print(f"  PASSED: {len(PASSED)}    FAILED: {len(FAILED)}")
    print("=" * 64)
    for name in FAILED:
        print(f"  x {name}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        engine.dispose()
    sys.exit(code)
