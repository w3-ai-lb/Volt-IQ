"""
Sign-in accounts across the two tables (Stage 2, "Users").

    users      staff: admin, office staff, field employees
    customers  customers who claimed portal access

Everything that needs "the account with this email" or "is this email free"
goes through here, so the two tables behave as one list of logins: one email
can never belong to two accounts.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.user import USER_ROLES, User

logger = logging.getLogger(__name__)

Account = User | Customer


def find_login(db: Session, email: str) -> Account | None:
    """The account that signs in with this email: staff first, then customers."""
    email = (email or "").strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user is not None:
        return user
    return db.query(Customer).filter(func.lower(Customer.email) == email).first()


def get_account(db: Session, kind: str | None, account_id: str) -> Account | None:
    """Resolve a token's subject. Tokens issued before Stage 2 carry no kind: customers."""
    if kind == "user":
        return db.get(User, account_id)
    return db.get(Customer, account_id)


def email_in_use(db: Session, email: str, exclude_id: str | None = None) -> bool:
    """True when another account (staff or customer) already uses this email."""
    email = (email or "").strip().lower()
    q_user = db.query(User.user_id).filter(func.lower(User.email) == email)
    q_cust = db.query(Customer.customer_id).filter(func.lower(Customer.email) == email)
    if exclude_id:
        q_user = q_user.filter(User.user_id != exclude_id)
        q_cust = q_cust.filter(Customer.customer_id != exclude_id)
    return q_user.first() is not None or q_cust.first() is not None


def is_staff(account) -> bool:
    return getattr(account, "role", None) in USER_ROLES


# Tables whose rows belong to a customer. A staff row that owns any of them
# is kept (without a password) instead of deleted, so no history is lost.
_CUSTOMER_CHILD_TABLES = (
    "consumption", "bills", "payments", "recommendations", "chat_conversations",
    "alerts", "anomalies", "notification_preferences", "password_reset_tokens", "subscribers",
)


def move_staff_to_users(engine) -> int:
    """
    One-time move of staff logins from `customers` to `users`.

    Runs at every start-up and does nothing once there is nothing left to
    move. The user keeps the same id, so employees.account_id, invoices
    issued_by and payment collected_by still point at the right person.
    Returns how many accounts were moved.
    """
    from app.database import SessionLocal

    tables = set(inspect(engine).get_table_names())
    if "users" not in tables or "customers" not in tables:
        return 0

    moved = 0
    with SessionLocal() as db:
        staff_rows = (
            db.query(Customer)
            .filter(Customer.role.in_(USER_ROLES), Customer.password_hash != "")
            .all()
        )
        for row in staff_rows:
            if db.get(User, row.customer_id) is not None:
                continue
            if db.query(User).filter(func.lower(User.email) == row.email.lower()).first():
                continue
            db.add(User(
                user_id=row.customer_id, name=row.name, email=row.email,
                password_hash=row.password_hash, role=row.role, status=row.status,
                phone=row.phone, address=row.address, region=row.region,
                theme=row.theme or "light", language=row.language or "en",
                session_version=row.session_version or 0, created_at=row.created_at,
            ))
            db.flush()

            owns_rows = any(
                db.execute(text(f"SELECT 1 FROM {t} WHERE customer_id = :cid LIMIT 1"),
                           {"cid": row.customer_id}).first()
                for t in _CUSTOMER_CHILD_TABLES if t in tables
            )
            if owns_rows:
                # Keep the record for its history; the login now lives in users.
                row.password_hash = ""
                row.email = f"moved.{row.customer_id.lower()}@voltiq.demo"
                row.status = "Inactive"
            else:
                db.execute(text("DELETE FROM customers WHERE customer_id = :cid"),
                           {"cid": row.customer_id})
            moved += 1
        db.commit()

    if moved:
        logger.info("Stage 2 users: moved %d staff login(s) from customers to users", moved)
    return moved


def repoint_employee_accounts(engine) -> None:
    """
    On PostgreSQL, replace the old employees.account_id -> customers foreign
    key with one to users. SQLite does not enforce the old one, so nothing to do.
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        rows = conn.execute(text("""
            SELECT tc.constraint_name, ccu.table_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.table_name = 'employees' AND tc.constraint_type = 'FOREIGN KEY'
        """)).all()
        for name, target in rows:
            if target == "customers":
                conn.execute(text(f'ALTER TABLE employees DROP CONSTRAINT "{name}"'))
                conn.execute(text(
                    "ALTER TABLE employees ADD CONSTRAINT employees_account_id_users_fkey "
                    "FOREIGN KEY (account_id) REFERENCES users(user_id) ON DELETE SET NULL"
                ))
