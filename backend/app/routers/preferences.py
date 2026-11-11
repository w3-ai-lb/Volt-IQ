"""
Preferences router, the notification settings behind the Settings page.

    GET   /preferences/notifications
    PATCH /preferences/notifications

WHY THIS EXISTS
---------------
The Settings page had five notification switches and a Save button. Toggling a
switch changed React state that nothing else read, and Save raised a toast and
sent no request at all: the choice was gone on the next page load. The switches
looked like a feature and were a picture of one.

WHAT EACH SWITCH NOW CONTROLS
-----------------------------
Each maps to one signal of the alert engine (app/ai/alerts.py), so turning one
off measurably changes what the platform produces for that customer: the alert
stops being generated and any unread instance of it is withdrawn on the next
refresh. That is a promise the platform can keep.

Delivery by email, SMS or push is deliberately absent. Architecture Section XI
defers outbound email to a future version, so there is no channel to deliver
on, and a switch labelled "Email notifications" would have been the same defect
in a new coat.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.database import get_db
from app.models.customer import Customer
from app.models.notification_preference import DEFAULTS, NotificationPreference
from app.schemas.common import CamelModel

router = APIRouter(prefix="/preferences", tags=["Preferences"])


class NotificationPreferencesOut(CamelModel):
    """Which alert categories this account receives."""

    high_usage: bool
    bill_reminders: bool
    anomalies: bool
    savings_milestones: bool


class NotificationPreferencesUpdate(CamelModel):
    """
    Every field optional, so the page can send only what changed.

    Uses exclude_unset on the way out, which is why `false` is distinguishable
    from "not sent": a plain `if value:` check would silently refuse to ever
    turn a preference off.
    """

    high_usage: bool | None = None
    bill_reminders: bool | None = None
    anomalies: bool | None = None
    savings_milestones: bool | None = None


def preferences_for(db: Session, customer_id: str) -> dict:
    """
    The customer's preferences, or the defaults when they have never set any.

    Deliberately does not create the row. A GET that writes turns every
    dashboard load into a database write, and an account that has never opened
    Settings has no preference to store, only a default to apply.
    """
    row = db.get(NotificationPreference, customer_id)
    if row is None:
        return dict(DEFAULTS)
    return {
        "high_usage": row.high_usage,
        "bill_reminders": row.bill_reminders,
        "anomalies": row.anomalies,
        "savings_milestones": row.savings_milestones,
    }


@router.get("/notifications", response_model=NotificationPreferencesOut)
def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    return preferences_for(db, current_user.customer_id)


@router.patch("/notifications", response_model=NotificationPreferencesOut)
def update_notification_preferences(
    payload: NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    Store the customer's choices and re-run the alert engine straight away.

    The refresh is the point. Without it, turning off "Unusual consumption
    alerts" would leave the existing ones sitting in the feed until something
    else happened to trigger a rebuild, and the setting would look ignored.
    """
    changes = payload.model_dump(exclude_unset=True)

    row = db.get(NotificationPreference, current_user.customer_id)
    if row is None:
        row = NotificationPreference(customer_id=current_user.customer_id, **DEFAULTS)
        db.add(row)

    for field, value in changes.items():
        if value is not None:
            setattr(row, field, value)

    db.commit()
    db.refresh(row)

    # Apply the choice to the feed now, not at some unspecified later point.
    try:
        from app.ai import alerts as alert_engine

        alert_engine.refresh_for_customer(db, current_user.customer_id)
    except Exception:  # pragma: no cover, a failed rebuild must not lose the setting
        db.rollback()

    return preferences_for(db, current_user.customer_id)
