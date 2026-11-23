"""
Security utilities, password hashing (bcrypt) and JWT tokens.

Implements two requirements from Section IX of the Software Architecture:
  * Password Hashing , bcrypt with a per-password random salt
  * JWT Authentication, signed, expiring access tokens
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# bcrypt only consumes the first 72 bytes of a password.
_BCRYPT_MAX_BYTES = 72


def _truncate(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plain password. Never store the plain value anywhere."""
    return bcrypt.hashpw(_truncate(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time comparison of a candidate password against its hash."""
    try:
        return bcrypt.checkpw(_truncate(plain_password), hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str, role: str, expires_minutes: int | None = None, session_version: int = 0
) -> str:
    """
    Build a signed JWT.

    `sub` holds the customer_id, `role` drives role-based access control, and
    `sv` the account's session version when the token was issued: a password
    change raises the version, which retires every token issued before it.
    """
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "sv": session_version,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Return the token payload, or None when invalid/expired."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Password reset tokens
# ---------------------------------------------------------------------------
def generate_reset_token() -> tuple[str, str]:
    """
    Create a password-reset token.

    Returns (plain_token, token_hash). Only the hash is stored; the plain value
    is handed to the user once and cannot be recovered afterwards, so a stolen
    database yields no usable tokens.
    """
    plain = secrets.token_urlsafe(32)
    return plain, hash_reset_token(plain)


def hash_reset_token(token: str) -> str:
    """SHA-256 of a reset token. Fast by design, the token is already high
    entropy, so password-style key stretching buys nothing here."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
