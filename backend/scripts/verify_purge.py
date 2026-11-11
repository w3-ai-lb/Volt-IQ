"""
Prove that --purge-demo removes the seeder's rows and nothing else.

    python -m scripts.verify_purge

WHY THIS EXISTS
---------------
Because the purge deleted the wrong thing, twice, and both times the error was
the same shape: a table that used to hold only seeded rows started holding
derived ones too, and nobody updated its classification.

The first time it was `customers`: a real administrator matched `ADMIN-0%` and
was removed by the purge the instructions had just told you to create it for.
The second time it was `recommendations` and `alerts`: 592 and 527 rows computed
from the supervisor's own readings, deleted and announced as "records our seeder
invented".

Both were found by a person running the thing and noticing. That is not a test.

WHAT THIS CHECKS
----------------
It takes a census of every table before the purge, runs it on a throwaway copy,
takes another census, and asserts three things:

  1. every row belonging to a GEN- customer survives, in EVERY table that has a
     customer_id column, discovered by inspection, not by a list somebody
     remembered to update;
  2. every row of the supervisor's own data survives, to the row;
  3. the seeder's own rows are gone.

Point 1 is the important one. A new table derived from his data will be checked
the day it is created, without anybody adding it here.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

# Tables holding the supervisor's own files. Not one row may be lost.
SUPPLIED_TABLES = [
    "generators", "zones", "zone_energy_daily", "generator_telemetry",
    "generator_alarms", "supply_sessions", "unbilled_connections",
    "subscribers", "subscriptions", "meters", "meter_readings",
    "tariffs", "invoices", "invoice_payments",
]

# How the seeder's own customers are recognised, mirroring data_provenance.
SEEDED_CUSTOMER_SQL = (
    "customer_id LIKE 'CUST-%' OR customer_id LIKE 'MTR-%' "
    "OR email = 'admin@nxttrn.com' OR email LIKE 'unclaimed.%'"
)


def _census(url: str) -> dict:
    """Row counts per table, plus counts of GEN--owned rows where applicable."""
    engine = create_engine(url)
    inspector = inspect(engine)
    out: dict[str, int] = {}
    with engine.connect() as conn:
        for table in inspector.get_table_names():
            columns = {c["name"] for c in inspector.get_columns(table)}
            out[table] = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar() or 0
            # Every table keyed on a customer is checked, whether or not anybody
            # remembered to list it. This is what makes the test outlive its author.
            if "customer_id" in columns:
                out[f"{table}::GEN"] = conn.execute(
                    text(f"SELECT count(*) FROM \"{table}\" WHERE customer_id LIKE 'GEN-%'")
                ).scalar() or 0
    engine.dispose()
    return out


def main() -> int:
    source = Path("energy_analytics.db")
    if not source.exists():
        print("No energy_analytics.db here. Run this from the backend folder.")
        return 1

    passed: list[str] = []
    failed: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        (passed if ok else failed).append(name)
        print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")

    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "copy.db"
        shutil.copy(source, copy)
        url = f"sqlite:///{copy}"

        before = _census(url)
        if not before.get("customers"):
            print("The database is empty. Run load-data.bat first.")
            return 1

        # An administrator has to exist or the purge refuses, by design.
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO customers (customer_id, name, email, password_hash, role, "
                "theme, language, plan, status, consumption, balance, created_at) VALUES "
                "('ADMIN-TEST','Purge Test','purge-test@example.com','x','admin',"
                "'light','en','Residential','Active',0,0, CURRENT_TIMESTAMP)"
            ))
        engine.dispose()

        import os
        os.environ["DATABASE_URL"] = url
        for module in [m for m in list(sys.modules) if m.startswith("app.")]:
            del sys.modules[module]
        from app.database import SessionLocal
        from scripts.data_provenance import purge

        print("\n=== Running --purge-demo on a throwaway copy ===\n")
        db = SessionLocal()
        try:
            purge(db, assume_yes=True)
        finally:
            db.close()

        after = _census(url)

        print("\n=== 1. Nothing derived from HIS data was removed ===")
        gen_keys = [k for k in before if k.endswith("::GEN")]
        for key in sorted(gen_keys):
            table = key.split("::")[0]
            check(
                f"{table}: rows owned by a GEN- customer survive",
                after.get(key, -1) == before[key],
                f"{before[key]:,} before, {after.get(key, 0):,} after",
            )

        print("\n=== 2. The supervisor's own files are untouched ===")
        for table in SUPPLIED_TABLES:
            if table in before:
                check(
                    f"{table} unchanged",
                    after.get(table, -1) == before[table],
                    f"{before[table]:,} rows",
                )

        print("\n=== 3. The seeder's rows are gone ===")
        engine = create_engine(url)
        with engine.connect() as conn:
            left = conn.execute(
                text(f"SELECT count(*) FROM customers WHERE {SEEDED_CUSTOMER_SQL}")
            ).scalar() or 0
            admin_left = conn.execute(
                text("SELECT count(*) FROM customers WHERE customer_id = 'ADMIN-TEST'")
            ).scalar() or 0
        engine.dispose()
        check("no seeded customer remains", left == 0, f"{left} left")
        check("an administrator created by hand survives", admin_left == 1)

    print(f"\n  PASSED {len(passed)}   FAILED {len(failed)}")
    if failed:
        print("\n  A purge that removes something derived from the supervisor's data")
        print("  is not a tidy-up, it is data loss. Fix the classification in")
        print("  scripts/data_provenance.py before running the real thing.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
