"""
Shared FastAPI dependencies, authentication and role-based access control.

Implements "Role-Based Access Control" from Section IX of the
Software Architecture document.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.customer import Customer

# The React frontend already sends `Authorization: Bearer <token>`
# (see src/services/api.ts request interceptor), so HTTPBearer matches it exactly.
bearer_scheme = HTTPBearer(auto_error=False)

# Fixed sentences, so the interface can translate them (src/i18n).
_BARRED = {
    "Suspended": "This account is suspended",
    "Inactive": "This account is inactive",
}

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Customer:
    """Resolve the authenticated customer from the JWT, or raise 401."""
    if credentials is None or not credentials.credentials:
        raise _CREDENTIALS_ERROR

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _CREDENTIALS_ERROR

    customer_id = payload.get("sub")
    if not customer_id:
        raise _CREDENTIALS_ERROR

    user = db.get(Customer, customer_id)
    if user is None:
        raise _CREDENTIALS_ERROR

    # Issued before the last password change (or before access was revoked):
    # the session belongs to the old password and ends here. A token from
    # before this check existed carries no version and counts as 0, so nobody
    # is signed out by the upgrade itself.
    try:
        token_version = int(payload.get("sv", 0))
    except (TypeError, ValueError):
        raise _CREDENTIALS_ERROR from None
    if token_version != (user.session_version or 0):
        raise _CREDENTIALS_ERROR

    if user.status in _BARRED:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=_BARRED[user.status])

    return user


def require_admin(current_user: Customer = Depends(get_current_user)) -> Customer:
    """Guard for administrator-only endpoints."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required",
        )
    return current_user
