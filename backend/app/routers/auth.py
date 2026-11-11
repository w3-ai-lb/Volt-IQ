"""
Authentication router, /auth/login, /auth/register, /auth/forgot-password.

Replaces the mock credential check that currently lives in
src/context/AuthContext.tsx. Passwords are bcrypt-hashed and access is granted
via a signed JWT, per Section IX of the Software Architecture.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core import rate_limit, registration_codes
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)
from app.database import get_db
from app.models.customer import DEFAULT_LANGUAGE, Customer
from app.models.password_reset import PasswordResetToken
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    UserOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# The one answer to every failed registration. Unknown ID, administrator
# account, already registered, deactivated, missing, wrong or expired code,
# email in use: they all read the same, so the endpoint cannot be used to find
# out which Customer IDs exist or which accounts are free to take.
# Written out in full rather than built from the status, so each is a fixed
# sentence the interface can show in the reader's language (src/i18n).
ACCOUNT_BARRED = {
    "Suspended": "This account is suspended. Please contact support.",
    "Inactive": "This account is inactive. Please contact support.",
}

REGISTRATION_REFUSED = (
    "We could not verify these details. Check the Customer ID and the registration code "
    "on your bill, or contact the provider's office. If you have already registered, "
    "sign in instead."
)


def _token_for(customer: Customer) -> str:
    """A sign-in token bound to the account's current session version."""
    return create_access_token(
        subject=customer.customer_id,
        role=customer.role,
        session_version=customer.session_version or 0,
    )


def _to_user_out(customer: Customer) -> UserOut:
    return UserOut(
        id=customer.customer_id,
        name=customer.name,
        email=customer.email,
        role=customer.role,
        phone=customer.phone,
        address=customer.address,
        theme=customer.theme or "light",
        language=customer.language or DEFAULT_LANGUAGE,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Authenticate and return { token, user }.

    Wrong passwords are limited per address and per client
    (app/core/rate_limit.py); the right password clears the count.
    """
    email = payload.email.lower().strip()
    client = rate_limit.client_of(request)
    limits = ((rate_limit.LOGIN_PER_ACCOUNT, (client, email)), (rate_limit.LOGIN_PER_CLIENT, client))
    rate_limit.guard(*limits)

    customer = db.query(Customer).filter(func.lower(Customer.email) == email).first()

    # Same error for unknown email and wrong password: avoids leaking
    # which accounts exist.
    if customer is None or not verify_password(payload.password, customer.password_hash):
        rate_limit.record(*limits)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    rate_limit.LOGIN_PER_ACCOUNT.clear((client, email))

    # Both Suspended and Inactive accounts are barred: a deactivated account
    # that could still sign in would make the Deactivate use case meaningless.
    if customer.status in ACCOUNT_BARRED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=ACCOUNT_BARRED[customer.status],
        )

    return AuthResponse(token=_token_for(customer), user=_to_user_out(customer))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> AuthResponse:
    """
    Register for online access to an existing account.

    The customer supplies the Customer ID from their bill, which is what links
    them to their own meter readings. The SRS (Section VI-i) treats Customer ID
    as an input rather than a generated value: the provider already holds the
    account and its consumption history, and registering only adds portal
    credentials to it.

    Generating a fresh id here instead would strand the customer on an empty
    dashboard while their real readings sat under the provider's own account
    number, a duplicate record holding their data.

    The Customer ID is printed on every bill, so on its own it proves nothing.
    The claim also needs the one-time registration code the provider issued for
    this account (app/core/registration_codes.py). Every failure gets the same
    400 and the same message, and an account an administrator deactivated is
    never reactivated here.
    """
    email = payload.email.lower().strip()
    customer_id = payload.customer_id.strip().upper()
    # Refused claims are limited per Customer ID and per client: the code is
    # the only secret, and the ID beside it is printed on every bill.
    limits = (
        (rate_limit.REGISTER_PER_ACCOUNT, customer_id),
        (rate_limit.REGISTER_PER_CLIENT, rate_limit.client_of(request)),
    )
    rate_limit.guard(*limits)

    customer = db.get(Customer, customer_id)
    eligible = (
        customer is not None
        and customer.role == "customer"
        and not customer.is_claimed
        and customer.status not in ("Inactive", "Suspended")
    )
    # Exactly one bcrypt comparison on every path, so the time taken does not
    # reveal whether the Customer ID exists or whether the code was close.
    code_ok = registration_codes.matches(payload.registration_code, customer if eligible else None)
    if not (eligible and code_ok):
        rate_limit.record(*limits)
        logger.info("Registration refused for Customer ID %s", customer_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=REGISTRATION_REFUSED)

    # The email must be free, ignoring this same record's placeholder address.
    # Checked only after the code, so it cannot be used to probe which
    # addresses are registered.
    clash = (
        db.query(Customer)
        .filter(func.lower(Customer.email) == email, Customer.customer_id != customer_id)
        .first()
    )
    if clash is not None:
        rate_limit.record(*limits)
        logger.info("Registration refused for Customer ID %s (email in use)", customer_id)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=REGISTRATION_REFUSED)

    # Claim the record: attach credentials, keep every existing reading, bill
    # and payment already linked to this Customer ID.
    customer.name = payload.name.strip() or customer.name
    customer.email = email
    customer.password_hash = hash_password(payload.password)
    registration_codes.clear(customer)
    if not customer.status:
        # A record loaded from the provider's file may not have a status set.
        # Only an EMPTY status is filled in: an account an administrator
        # suspended or deactivated was refused above and stays that way.
        customer.status = "Active"
    db.commit()
    db.refresh(customer)

    logger.info("Account %s claimed by %s", customer.customer_id, email)

    # Optional demo convenience: fabricate a history for an account that has
    # none. Off by default, because readings should come from the pipeline.
    if settings.PROVISION_DEMO_DATA:
        try:
            from app.ai import recommender
            from app.pipeline.provision import provision_customer

            provision_customer(db, customer)
            recommender.refresh_for_customer(db, customer.customer_id)
        except Exception:
            logger.exception("Provisioning failed for %s", customer.customer_id)
            db.rollback()

    return AuthResponse(token=_token_for(customer), user=_to_user_out(customer))


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(
    payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> ForgotPasswordResponse:
    """
    Begin password recovery, the "Password Reset" requirement (SRS III-ii).

    Issues a single-use token that expires. Always reports success, even for an
    unknown address, so the endpoint cannot be used to discover which emails
    are registered.

    Email delivery is a future enhancement (Architecture Section XI), so there
    is no safe way yet for the token to reach its owner. It is returned in the
    response only when RETURN_RESET_TOKEN_IN_RESPONSE is true AND the database
    is SQLite, for a local demonstration (`settings.reset_token_in_response`).
    Everywhere else the token is stored and nothing is returned, which means a
    deployed system cannot offer self-service reset until email delivery exists.

    Every request counts towards a limit per address and per client, whether
    or not the address exists, so the limit itself reveals nothing either.
    """
    email = payload.email.lower().strip()
    limits = (
        (rate_limit.FORGOT_PER_EMAIL, email),
        (rate_limit.FORGOT_PER_CLIENT, rate_limit.client_of(request)),
    )
    rate_limit.guard(*limits)
    rate_limit.record(*limits)

    customer = db.query(Customer).filter(func.lower(Customer.email) == email).first()

    if customer is None:
        # Same shape of reply as the success case: no account enumeration.
        return ForgotPasswordResponse(sent=True, email=email)

    # Invalidate any tokens already outstanding for this account, so a previous
    # request cannot still be redeemed after a new one is issued.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.customer_id == customer.customer_id,
        PasswordResetToken.used.is_(False),
    ).update({"used": True}, synchronize_session=False)

    plain_token, token_hash = generate_reset_token()
    expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
        minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES
    )

    db.add(
        PasswordResetToken(
            customer_id=customer.customer_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
    )
    db.commit()

    logger.info("Password reset requested for %s", customer.customer_id)

    return ForgotPasswordResponse(
        sent=True,
        email=email,
        reset_token=plain_token if settings.reset_token_in_response else None,
        expires_in_minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES,
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)
) -> ResetPasswordResponse:
    """
    Complete password recovery: exchange a valid token for a new password.

    The token must exist, be unused, and not have expired. It is consumed on
    success so the same link cannot be replayed. Tokens that do not work are
    limited per client.
    """
    limit = ((rate_limit.RESET_PER_CLIENT, rate_limit.client_of(request)),)
    rate_limit.guard(*limit)

    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == hash_reset_token(payload.token))
        .first()
    )

    now = datetime.now(UTC).replace(tzinfo=None)
    if record is None or record.used or record.expires_at < now:
        rate_limit.record(*limit)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Please request a new one.",
        )

    customer = db.get(Customer, record.customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This reset link is invalid or has expired. Please request a new one.",
        )

    customer.password_hash = hash_password(payload.new_password)
    # A reset is what someone does when they think the password is known to
    # somebody else, so every session signed in with the old one ends.
    customer.session_version = (customer.session_version or 0) + 1
    record.used = True
    db.commit()

    logger.info("Password reset completed for %s", customer.customer_id)
    return ResetPasswordResponse(reset=True, email=customer.email)


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
) -> ChangePasswordResponse:
    """
    Change the password of the signed-in account.

    Separate from the reset flow: a reset proves ownership of the email address,
    whereas this proves knowledge of the current password. Requiring it means a
    stolen session token alone cannot lock the real owner out.

    Every other device is signed out: the session version goes up, so tokens
    issued before the change are refused (app/core/deps.py). This device gets
    a new token in the response and stays signed in.
    """
    limit = ((rate_limit.CHANGE_PER_ACCOUNT, current_user.customer_id),)
    rate_limit.guard(*limit)
    if not verify_password(payload.current_password, current_user.password_hash):
        rate_limit.record(*limit)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current password is incorrect",
        )

    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different from the current one",
        )

    current_user.password_hash = hash_password(payload.new_password)
    current_user.session_version = (current_user.session_version or 0) + 1

    # Any outstanding reset link is now stale: the owner has just proved
    # control of the account, so leaving one redeemable would be a loose end.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.customer_id == current_user.customer_id,
        PasswordResetToken.used.is_(False),
    ).update({"used": True}, synchronize_session=False)

    db.commit()
    logger.info("Password changed for %s", current_user.customer_id)
    return ChangePasswordResponse(changed=True, token=_token_for(current_user))


@router.get("/me", response_model=UserOut)
def me(current_user: Customer = Depends(get_current_user)) -> UserOut:
    """Return the authenticated user, lets the frontend validate a stored token."""
    return _to_user_out(current_user)
