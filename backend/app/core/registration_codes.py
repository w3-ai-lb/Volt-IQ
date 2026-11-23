"""
One-time registration codes: the second thing, besides the Customer ID, that a
customer needs to claim portal access to their account.

WHY A CODE
----------
A Customer ID is printed on every bill and is not a secret: anyone who has seen
a bill, or who tries numbers in sequence, can type one. Registration used to
accept the ID alone, so whoever registered first took the account, with its
readings, bills, phone number and address. The code closes that gap: the
provider issues one per account and gives it only to the account holder, on the
paper bill or at the office.

HOW IT IS KEPT
--------------
Eight characters from an alphabet without look-alikes (no 0/O, 1/I/L), about 40
bits. Only a bcrypt hash is stored, never the code, so a copy of the database
yields no usable code. A code is valid for REGISTRATION_CODE_VALID_DAYS days,
is deleted the moment it is used, and is replaced when a new one is issued.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.config import settings
from app.core.security import hash_password, verify_password

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 8


def generate() -> str:
    """A new random code. Shown to the administrator once; never stored as such."""
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def normalize(code: str | None) -> str:
    """Upper case, without the spaces and dashes people add when copying a code off paper."""
    return "".join(ch for ch in (code or "").upper() if ch not in " -\t")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def issue(customer) -> tuple[str, datetime]:
    """Give `customer` a new code, replacing any earlier one. The caller commits."""
    code = generate()
    expires_at = _now() + timedelta(days=settings.REGISTRATION_CODE_VALID_DAYS)
    customer.registration_code_hash = hash_password(code)
    customer.registration_code_expires_at = expires_at
    return code, expires_at


def has_valid_code(customer) -> bool:
    """True when the account holds a code that has not expired."""
    expires_at = customer.registration_code_expires_at
    return bool(customer.registration_code_hash) and expires_at is not None and expires_at > _now()


@lru_cache(maxsize=1)
def _decoy_hash() -> str:
    # A real bcrypt hash of a value nobody knows. Compared against when there is
    # no stored code, so refusing an unknown Customer ID takes as long as
    # refusing a wrong code, and the response time gives nothing away.
    return hash_password(secrets.token_urlsafe(16))


def matches(code: str | None, customer) -> bool:
    """
    True only when `customer` holds an unexpired code and `code` is that code.

    Always performs exactly one bcrypt comparison (constant-time in itself),
    whether or not there is a stored code to compare against.
    """
    candidate = normalize(code)
    stored = customer.registration_code_hash if customer is not None and has_valid_code(customer) else None
    if not stored or not candidate:
        verify_password(candidate or "-", _decoy_hash())
        return False
    return verify_password(candidate, stored)


def clear(customer) -> None:
    """Delete a code once it has been used, so it cannot be used again."""
    customer.registration_code_hash = None
    customer.registration_code_expires_at = None
