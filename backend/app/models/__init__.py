"""
ORM models.

TWO DOMAINS LIVE HERE, ON PURPOSE
---------------------------------
The original platform model, the seven entities from Section VII of the
Software Architecture plus Alert and Anomaly, describes a customer buying
electricity from a utility: who they are, what they used, what they owe.

The ishtirak model added for Project 3 describes the other half of the same
street. It has generators, zones, telemetry and a tariff that changes every
month, because the question that project asks cannot be expressed without
them: the generator sent X kWh into this neighbourhood, the meters accounted
for Y, and the difference has to be explained before anybody is accused of
taking it.

They are kept apart rather than merged. `customers` is an authentication
principal and `subscribers` is a provider record; `consumption` is kWh in a
period and `meter_readings` is the number on the dial. Names that look alike
and mean different things are the expensive kind of confusion, so each domain
keeps its own vocabulary and the two meet at the zone.

Importing this package registers every model on the shared declarative Base.
"""

from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.models.chat import ChatConversation, ChatMessage
from app.models.consumption import Consumption
from app.models.customer import Customer
from app.models.employee import Employee, EmployeeAssignment
from app.models.user import User
from app.models.explanation import SubscriberExplanation
from app.models.forecast import Forecast
from app.models.generator_metrics import GeneratorMonthMetrics
from app.models.invoice import Invoice, InvoicePayment, Tariff
from app.models.loss import ZoneLossMonthly
from app.models.network import (
    Generator,
    GeneratorAlarm,
    GeneratorTelemetry,
    SupplySession,
    UnbilledConnection,
    Zone,
    ZoneEnergyDaily,
)
from app.models.notification_preference import NotificationPreference
from app.models.password_reset import PasswordResetToken
from app.models.payment import Payment
from app.models.recommendation import Recommendation
from app.models.subscription import Meter, MeterReading, Subscriber, Subscription

__all__ = [
    # --- platform ---------------------------------------------------------
    "Alert",
    "Anomaly",
    "Bill",
    "ChatConversation",
    "ChatMessage",
    "Consumption",
    "Customer",
    "Employee",
    "EmployeeAssignment",
    "User",
    "Forecast",
    "GeneratorMonthMetrics",
    "NotificationPreference",
    "PasswordResetToken",
    "Payment",
    "Recommendation",
    # --- ishtirak: supply side --------------------------------------------
    "Generator",
    "GeneratorAlarm",
    "GeneratorTelemetry",
    "SupplySession",
    "UnbilledConnection",
    "Zone",
    "ZoneEnergyDaily",
    # --- ishtirak: demand side --------------------------------------------
    "Meter",
    "MeterReading",
    "Subscriber",
    "Subscription",
    # --- ishtirak: money ---------------------------------------------------
    "Invoice",
    "InvoicePayment",
    "SubscriberExplanation",
    "Tariff",
    # --- derived -----------------------------------------------------------
    "ZoneLossMonthly",
]
