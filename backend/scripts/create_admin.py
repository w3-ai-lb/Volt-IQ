"""
Create or update an administrator account.

WHY THIS EXISTS
---------------
The only place an administrator is created today is inside the development
seeder, alongside seventeen fabricated customers. That is fine while the demo
data is the data, and useless the moment it is not: load the provider's real
dataset into a clean database and there is no administrator, no password on any
row, and therefore no way to sign in to the platform at all.

That is not a bug in the loader. `app/pipeline/ingest.py` is right to leave
every imported customer unclaimed, with an empty password hash: a record the
provider holds is not a login until a person registers for it. But somebody has
to be able to open the admin side of a real deployment, and this is what makes
that possible without seeding fake customers to get one.

    python -m scripts.create_admin --email you@nxttrn.com --name "Your Name"

The password is asked for rather than passed on the command line, because a
command line ends up in the shell history file and in the terminal scrollback.
Pass --password only for an automated setup where that is already understood.

Run it again with the same email to reset that administrator's password: the
account is matched on email, so this never creates a duplicate.
"""

from __future__ import annotations

import argparse
import getpass
import sys


from app.core.security import hash_password
from app.database import SessionLocal, create_all_tables
from app.core.accounts import find_login
from app.models.user import User

MIN_PASSWORD = 6


def _next_admin_id(db) -> str:
    """ADMIN-001, ADMIN-002, ... so a second administrator does not collide."""
    taken = {
        row[0]
        for row in db.query(User.user_id).filter(User.user_id.like("ADMIN-%")).all()
    }
    n = 1
    while f"ADMIN-{n:03d}" in taken:
        n += 1
    return f"ADMIN-{n:03d}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update an administrator account.")
    parser.add_argument("--email", required=True, help="Sign-in email for the administrator")
    parser.add_argument("--name", help="Display name (defaults to the part before the @)")
    parser.add_argument("--region", default="Beirut")
    parser.add_argument(
        "--password",
        help="Set the password without being prompted. Avoid: it lands in your shell history.",
    )
    args = parser.parse_args()

    email = args.email.lower().strip()

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat:   "):
            print("The two passwords do not match. Nothing was changed.")
            return 1

    if len(password) < MIN_PASSWORD:
        print(f"Password must be at least {MIN_PASSWORD} characters. Nothing was changed.")
        return 1

    create_all_tables()
    db = SessionLocal()
    try:
        # Stage 2: administrators live in `users`; a customer with this email is refused below.
        existing = find_login(db, email)

        if existing is not None:
            # Promoting an existing customer account to administrator would
            # silently hand that person the whole customer base. Refuse, and
            # say which account it is, rather than doing it quietly.
            if existing.role != "admin":
                print(
                    f"{email} already exists as a customer account ({existing.customer_id}).\n"
                    "Refusing to turn a customer into an administrator. Use a different email."
                )
                return 1

            existing.password_hash = hash_password(password)
            # Signs out every session opened with the old password.
            existing.session_version = (existing.session_version or 0) + 1
            if args.name:
                existing.name = args.name
            db.commit()
            print(f"Password reset for the existing administrator {existing.customer_id} ({email}).")
            return 0

        admin = User(
            user_id=_next_admin_id(db),
            name=args.name or email.split("@")[0],
            email=email,
            password_hash=hash_password(password),
            role="admin",
            region=args.region,
            status="Active",
        )
        db.add(admin)
        db.commit()
        print(f"Administrator created: {admin.customer_id}  {admin.name}  <{admin.email}>")
        print("Sign in at the portal with that email and the password you just set.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
