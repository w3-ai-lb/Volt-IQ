"""
Issue one-time registration codes, and write them to a CSV for printing.

    python -m scripts.issue_registration_codes --out codes.csv --all-unregistered
    python -m scripts.issue_registration_codes --out codes.csv <customer_id> [<customer_id> ...]

A customer needs their Customer ID AND a registration code to register for the
portal (see app/core/registration_codes.py). This gives each eligible account a
new code, valid for REGISTRATION_CODE_VALID_DAYS days, and writes one row per
account: Customer ID, name, code and expiry date, ready to be printed on the
bills or handed over at the office.

Eligible means: a customer account (not an administrator), not yet registered,
and not suspended or deactivated. Anything else is listed as skipped, with the
reason, and gets no code.

THE CSV IS SENSITIVE
--------------------
It holds the codes themselves; the database holds only their hashes. Print it,
hand the codes over, then delete the file. It is never overwritten unless you
pass --force, and this script never prints a code on the screen. Issuing a new
code for an account replaces its previous one, so run it again only for
accounts that need a fresh code (--skip-existing leaves alone any account
whose code is still valid).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from app.core import registration_codes
from app.database import SessionLocal, create_all_tables
from app.models.customer import Customer


def _reason_ineligible(customer: Customer | None) -> str | None:
    if customer is None:
        return "no such Customer ID"
    if customer.role != "customer":
        return "not a customer account"
    if customer.is_claimed:
        return "already registered"
    if customer.status in ("Inactive", "Suspended"):
        return f"account is {customer.status.lower()}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue one-time registration codes for printing.")
    parser.add_argument("customer_ids", nargs="*", help="Customer IDs to issue codes for")
    parser.add_argument("--all-unregistered", action="store_true",
                        help="Every customer account that is not registered and not deactivated")
    parser.add_argument("--out", type=Path, required=True,
                        help="CSV file to write (holds the codes: delete it after printing)")
    parser.add_argument("--force", action="store_true", help="Overwrite --out if it already exists")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Leave alone accounts whose current code has not expired")
    args = parser.parse_args()

    if not args.customer_ids and not args.all_unregistered:
        parser.error("give one or more Customer IDs, or --all-unregistered")
    if args.out.exists() and not args.force:
        print(f"\n  {args.out} already exists. Pass --force to overwrite it.\n")
        return 1

    create_all_tables()
    db = SessionLocal()
    issued: list[tuple[str, str, str, str]] = []
    skipped: list[tuple[str, str]] = []
    try:
        if args.all_unregistered:
            candidates = db.query(Customer).filter(Customer.role == "customer").order_by(Customer.customer_id).all()
            targets = [(c.customer_id, c) for c in candidates]
        else:
            targets = [(cid.strip().upper(), db.get(Customer, cid.strip().upper())) for cid in args.customer_ids]

        for customer_id, customer in targets:
            reason = _reason_ineligible(customer)
            if reason is None and args.skip_existing and registration_codes.has_valid_code(customer):
                reason = "already holds a valid code (--skip-existing)"
            if reason is not None:
                skipped.append((customer_id, reason))
                continue
            code, expires_at = registration_codes.issue(customer)
            issued.append((customer.customer_id, customer.name, code, expires_at.strftime("%Y-%m-%d")))

        if issued:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            # utf-8-sig: with the byte-order mark Excel, which is what the file
            # is printed from, reads names in Arabic script correctly.
            with args.out.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["customer_id", "name", "registration_code", "valid_until_utc"])
                writer.writerows(issued)
        # Commit only after the file is safely written, so a code is never
        # issued that nobody can read.
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print(f"\n  Issued {len(issued)} registration code(s).")
    if issued:
        print(f"  Written to {args.out}. It holds the codes: print it, then delete it.")
    for customer_id, reason in skipped:
        print(f"  Skipped {customer_id}: {reason}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
