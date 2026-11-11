"""Authentication schemas, match the shapes expected by AuthContext.tsx."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import CamelModel


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    """
    Portal registration.

    `customer_id` is the account number printed on the customer's bill. The
    SRS (Section VI-i) lists Customer ID as an *input* to the Customer
    Management Module, not a generated value: the provider already holds the
    account, and registering claims online access to it. Without this the
    portal has no way to know which meter belongs to the person signing up.

    `registration_code` is the one-time code the provider issues with the bill.
    The Customer ID alone is not a secret, so it cannot be proof of ownership.
    The field is optional in the schema on purpose: a missing code gets the
    same refusal as a wrong one, rather than a validation error that reads
    differently.
    """

    customer_id: str = Field(min_length=1, max_length=20)
    registration_code: str = Field(default="", max_length=32)
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class RegistrationCodeOut(CamelModel):
    """A newly issued registration code. The code itself is shown this once only."""

    customer_id: str
    registration_code: str
    expires_at: datetime


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(CamelModel):
    sent: bool
    email: EmailStr
    # Present only when no email provider is configured, so the reset flow is
    # testable without one. Section XI of the Software Architecture lists email
    # notifications as a future enhancement.
    reset_token: str | None = None
    expires_in_minutes: int | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8)
    new_password: str = Field(min_length=6, max_length=128)


class ResetPasswordResponse(CamelModel):
    reset: bool
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    """
    Changing a password while signed in.

    The current password is required: a stolen session token should not be
    enough to lock the real owner out of their account.
    """

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6, max_length=128)


class ChangePasswordResponse(CamelModel):
    changed: bool
    # A new sign-in token for the device that made the change. Tokens issued
    # before it no longer work, which is what signs the other devices out.
    token: str | None = None


class UserOut(CamelModel):
    """Mirrors the `User` interface in src/context/AuthContext.tsx."""

    id: str
    name: str
    email: str
    role: str
    phone: str | None = None
    address: str | None = None
    theme: str = "light"
    language: str = "en"


class AuthResponse(BaseModel):
    """Frontend reads `{ token, user }` from /auth/login and /auth/register."""

    token: str
    user: UserOut
