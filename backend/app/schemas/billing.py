"""Bills, payments, recommendations, alerts and profile schemas."""

from datetime import date

from pydantic import BaseModel, EmailStr

from app.schemas.common import CamelModel


# --- Bills -----------------------------------------------------------------
class BillOut(CamelModel):
    id: str
    month: str
    amount: float
    due_date: date       # serialised as "dueDate"
    status: str
    # 845 of this provider's 5,400 invoices are part paid, so the face value is
    # not what pressing Pay will charge. Both figures are sent, because a
    # screen that shows only the face value cannot tell the customer what they
    # still owe, and a Pay button decided from `status` alone offers itself on
    # bills that have nothing left to pay.
    paid: float = 0.0
    remaining: float = 0.0


# --- Payments --------------------------------------------------------------
class PaymentOut(CamelModel):
    id: str
    date: date
    amount: float
    method: str
    status: str
    # Which bill this payment settles. Null for a payment recorded against the
    # account rather than a specific bill. The Bills page needs it to state how
    # much has been paid against a bill, which it previously guessed at by
    # splitting the total into invented line items.
    bill_id: str | None = None


# --- Recommendations -------------------------------------------------------
class RecommendationOut(CamelModel):
    id: str
    title: str
    description: str
    estimated_savings: float   # -> "estimatedSavings"
    priority: str
    icon: str
    completed: bool


class RecommendationUpdate(BaseModel):
    completed: bool = True


class RecommendationUpdateOut(CamelModel):
    id: str
    completed: bool


# --- Alerts ----------------------------------------------------------------
class AlertOut(CamelModel):
    id: str
    type: str
    title: str
    message: str
    severity: str
    date: date
    read: bool = False


class AlertUpdate(BaseModel):
    read: bool = True


class AlertUpdateOut(CamelModel):
    id: str
    read: bool


# --- Profile ---------------------------------------------------------------
class ProfileOut(CamelModel):
    name: str
    email: str
    phone: str | None = None
    address: str | None = None
    theme: str = "light"
    language: str = "en"


class ProfileUpdate(BaseModel):
    """
    Editable profile fields.

    Email is included because the Profile page offers it, and it is the
    customer's login identity, so the endpoint checks it is not already taken.
    """

    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    theme: str | None = None
    language: str | None = None
