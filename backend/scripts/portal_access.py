"""
Give one of the provider's real subscribers a password, so you can sign in as
them and see the customer side on real readings.

    python -m scripts.portal_access --list
    python -m scripts.portal_access GEN-00018                         # a random password is generated
    python -m scripts.portal_access GEN-00018 --password mypassword   # or choose one

WHY THIS EXISTS ALONGSIDE THE REGISTER PAGE
-------------------------------------------
Registering on the website is the real flow and it works: a customer types
their Customer ID, their own email and a password, and the account is theirs.
But registration REPLACES the email on the record with the one typed in. Doing
that to demonstrate the product rewrites a subscriber's details in the
provider's own data, and after a few demonstrations the customer list carries
several accounts whose email is somebody's test address.

This changes one column and nothing else. The name, the email, the region, the
plan, the readings, the invoices and the payments are all left exactly as they
came from the provider. You sign in with the subscriber's OWN email address.

    Nothing here creates an account. Every one of the 300 already exists; this
    only attaches a password to one so it can be opened.

TO UNDO IT
----------
    python -m scripts.portal_access GEN-00018 --revoke

which clears the password and puts the account back to "not registered".
"""

from __future__ import annotations

import argparse
import secrets

from sqlalchemy import func

from app.core.security import hash_password
from app.database import SessionLocal, add_missing_columns
from app.models.alert import Alert
from app.models.bill import Bill
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.recommendation import Recommendation

# There is no built-in password. A fixed default gave every account opened this
# way the same password, readable by anyone with the source code or its Git
# history. Leave out --password and a random one is generated for this account
# and shown once.
_GENERATED_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
GENERATED_LENGTH = 12


def generate_password(length: int = GENERATED_LENGTH) -> str:
    return "".join(secrets.choice(_GENERATED_ALPHABET) for _ in range(length))


def _counts(db, customer_id: str) -> dict:
    def n(model, **kw):
        return (
            db.query(func.count())
            .select_from(model)
            .filter(model.customer_id == customer_id, *kw.get("extra", []))
            .scalar()
            or 0
        )

    return {
        "readings": n(Consumption),
        "bills": n(Bill),
        "unpaid": db.query(func.count()).select_from(Bill).filter(
            Bill.customer_id == customer_id, Bill.status != "Paid").scalar() or 0,
        "payments": n(Payment),
        "recommendations": n(Recommendation),
        "alerts": n(Alert),
    }


def show_candidates(db, limit: int = 10) -> None:
    """The accounts with the most to look at, so the demonstration is not empty."""
    rows = (
        db.query(Customer)
        .filter(Customer.role == "customer")
        .order_by(Customer.customer_id)
        .all()
    )
    scored = []
    for c in rows:
        k = _counts(db, c.customer_id)
        if not k["readings"]:
            continue
        scored.append((k["recommendations"] + k["alerts"] + (1 if k["unpaid"] else 0), c, k))
    scored.sort(key=lambda t: -t[0])

    print("\n  Accounts with the most to show:\n")
    print(f"  {'Customer ID':<12}{'Name':<24}{'Plan':<13}{'Readings':>9}{'Unpaid':>8}"
          f"{'Tips':>6}{'Alerts':>8}   Sign in with")
    print("  " + "-" * 104)
    for _, c, k in scored[:limit]:
        state = "" if not (c.password_hash or "") else "   (already has a password)"
        print(f"  {c.customer_id:<12}{(c.name or ''):<24}{(c.plan or ''):<13}"
              f"{k['readings']:>9}{k['unpaid']:>8}{k['recommendations']:>6}{k['alerts']:>8}"
              f"   {c.email}{state}")
    print(f"\n  Then:  python -m scripts.portal_access {scored[0][1].customer_id}\n")


def grant(db, customer_id: str, password: str, generated: bool = False) -> int:
    customer = db.get(Customer, customer_id)
    if customer is None:
        print(f"\n  No account with the ID {customer_id}.")
        print("  Run  python -m scripts.portal_access --list  to see some.\n")
        return 1
    if customer.role == "admin":
        print(f"\n  {customer_id} is an administrator account, not a subscriber.\n")
        return 1

    already = bool(customer.password_hash or "")
    # The only columns this touches: the password, and the session version,
    # which signs out anybody still signed in with a password it replaces.
    customer.password_hash = hash_password(password)
    if already:
        customer.session_version = (customer.session_version or 0) + 1
    db.commit()

    k = _counts(db, customer_id)
    print("\n  " + "=" * 62)
    print(f"  Sign in as {customer.name}")
    print("  " + "=" * 62)
    print(f"\n    Email     {customer.email}")
    print(f"    Password  {password}")
    if generated:
        print("              (generated for this account and shown only here: note it now)")
    print("\n  Open the website, choose Sign in, and use those two.")
    print("\n  What this account holds:")
    print(f"    {k['readings']} monthly readings, {k['bills']} bills "
          f"({k['unpaid']} unpaid), {k['payments']} payments")
    print(f"    {k['recommendations']} recommendations, {k['alerts']} alerts")
    if already:
        print("\n  (This account already had a password. It has been replaced, and anyone")
        print("   still signed in with the old one has been signed out.)")
    print("\n  Nothing else on the record was changed: the name, the email, the")
    print("  region, the plan and every reading are exactly as the provider sent")
    print("  them. To undo this, run the same command with --revoke.\n")
    return 0


def revoke(db, customer_id: str) -> int:
    customer = db.get(Customer, customer_id)
    if customer is None:
        print(f"\n  No account with the ID {customer_id}.\n")
        return 1
    customer.password_hash = ""
    # Ends the sessions already open, not only future sign-ins.
    customer.session_version = (customer.session_version or 0) + 1
    db.commit()
    print(f"\n  {customer_id} can no longer sign in. The account and all its data remain.\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach a password to one of the provider's real subscribers.")
    parser.add_argument("customer_id", nargs="?", help="e.g. GEN-00018")
    parser.add_argument("--list", action="store_true",
                        help="Show the accounts with the most to look at")
    parser.add_argument("--password", default=None,
                        help="Password to set, at least 6 characters. Leave it out and a random "
                             "one is generated and shown once.")
    parser.add_argument("--revoke", action="store_true",
                        help="Remove portal access from this account again")
    args = parser.parse_args()

    # Whole customer records are read below: first add any column this version
    # of the code expects, as the server does when it starts (app/database.py).
    add_missing_columns()
    db = SessionLocal()
    try:
        if args.list or not args.customer_id:
            show_candidates(db)
            return 0
        if args.revoke:
            return revoke(db, args.customer_id.upper())
        generated = args.password is None
        password = generate_password() if generated else args.password
        if len(password) < 6:
            print("\n  The password must be at least six characters.\n")
            return 1
        return grant(db, args.customer_id.upper(), password, generated=generated)
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
