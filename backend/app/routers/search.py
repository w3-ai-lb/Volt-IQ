"""
Search router, one role-aware endpoint behind the header search box.

    GET /search?q=...&limit=8

WHY IT IS ONE ENDPOINT AND NOT SEVERAL
--------------------------------------
The search box is a single control, so it needs a single round-trip. Asking
the browser to fan out to /bills, /payments, /alerts, /recommendations and
/customers on every keystroke would multiply the request count by five and
still leave the frontend to merge and rank the results.

WHAT IT SEARCHES DEPENDS ON WHO IS ASKING
-----------------------------------------
An administrator is looking for a customer. A customer is looking for one of
their own bills, payments, alerts or recommendations. The two are answered by
different queries, chosen from the caller's role, and a customer's query is
always constrained to their own customer_id, so the endpoint cannot be used to
read another account.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.i18n import localize, request_language
from app.core.money import money
from app.database import get_db
from app.models.alert import Alert
from app.models.anomaly import Anomaly
from app.models.bill import Bill
from app.models.customer import Customer
from app.models.payment import Payment
from app.models.recommendation import Recommendation
from app.schemas.common import CamelModel

router = APIRouter(prefix="/search", tags=["Search"])

MIN_QUERY_LENGTH = 2


class SearchResultOut(CamelModel):
    """
    One row in the results dropdown.

    `kind` is what the frontend maps to a route and an icon. The backend does
    not emit URLs: routing is the frontend's business, and hardcoding
    '/app/bills' here would mean a change to the router breaking the API.
    """

    kind: str          # customer | bill | payment | recommendation | alert | anomaly
    id: str
    title: str
    subtitle: str


class SearchResponseOut(CamelModel):
    query: str
    results: list[SearchResultOut]


def _like(term: str) -> str:
    """
    Escape the SQL LIKE wildcards before wrapping the term in its own.

    Without this, a query of '%' matches every row, and '_' matches any single
    character, so typing an underscore silently returns unrelated records.
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _admin_results(db: Session, term: str, limit: int, lang: str = "en") -> list[dict]:
    """Administrators search the customer base, then unresolved anomalies."""
    pattern = _like(term)
    results: list[dict] = []

    customers = (
        db.query(Customer)
        .filter(
            Customer.role == "customer",
            or_(
                Customer.customer_id.ilike(pattern, escape="\\"),
                Customer.name.ilike(pattern, escape="\\"),
                Customer.email.ilike(pattern, escape="\\"),
                Customer.region.ilike(pattern, escape="\\"),
                Customer.plan.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Customer.name)
        .limit(limit)
        .all()
    )
    for customer in customers:
        details = " · ".join(
            part for part in (customer.customer_id, customer.region, customer.plan) if part
        )
        results.append(
            {
                "kind": "customer",
                "id": customer.customer_id,
                "title": customer.name,
                "subtitle": details,
            }
        )

    remaining = limit - len(results)
    if remaining <= 0:
        return results

    anomalies = (
        db.query(Anomaly)
        .filter(
            Anomaly.resolved.is_(False),
            or_(
                Anomaly.customer_id.ilike(pattern, escape="\\"),
                Anomaly.type.ilike(pattern, escape="\\"),
                Anomaly.description.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Anomaly.detected_at.desc())
        .limit(remaining)
        .all()
    )
    for anomaly in anomalies:
        results.append(
            {
                "kind": "anomaly",
                "id": str(anomaly.anomaly_id),
                "title": localize(anomaly.type, lang),
                "subtitle": f"{anomaly.customer_id} · {anomaly.severity}",
            }
        )

    return results


def _customer_results(db: Session, customer_id: str, term: str, limit: int, lang: str = "en") -> list[dict]:
    """
    A customer searches their own records only.

    Every query below is filtered on customer_id first. That filter is the
    access control, not a convenience: without it the endpoint would return
    other people's bills to anyone who typed the right word.
    """
    pattern = _like(term)
    results: list[dict] = []

    def room() -> int:
        return limit - len(results)

    bills = (
        db.query(Bill)
        .filter(
            Bill.customer_id == customer_id,
            or_(
                Bill.bill_id.ilike(pattern, escape="\\"),
                Bill.month.ilike(pattern, escape="\\"),
                Bill.status.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Bill.due_date.desc())
        .limit(room())
        .all()
    )
    for bill in bills:
        results.append(
            {
                "kind": "bill",
                "id": bill.bill_id,
                "title": localize(f"Bill {bill.month}", lang),
                # In pounds with the unit, like every other amount on the
                # site; this was the one place still printing "11504672.00".
                # The status is translated by the search box.
                "subtitle": f"{money(bill.amount)} · {bill.status}",
            }
        )

    if room() > 0:
        payments = (
            db.query(Payment)
            .filter(
                Payment.customer_id == customer_id,
                or_(
                    Payment.payment_id.ilike(pattern, escape="\\"),
                    Payment.method.ilike(pattern, escape="\\"),
                    Payment.status.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Payment.date.desc())
            .limit(room())
            .all()
        )
        for payment in payments:
            results.append(
                {
                    "kind": "payment",
                    "id": payment.payment_id,
                    "title": localize(f"Payment {money(payment.amount)}", lang),
                    "subtitle": f"{payment.date.isoformat()} · {payment.method}",
                }
            )

    if room() > 0:
        recommendations = (
            db.query(Recommendation)
            .filter(
                Recommendation.customer_id == customer_id,
                or_(
                    Recommendation.title.ilike(pattern, escape="\\"),
                    Recommendation.description.ilike(pattern, escape="\\"),
                    Recommendation.priority.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Recommendation.estimated_savings.desc())
            .limit(room())
            .all()
        )
        for recommendation in recommendations:
            results.append(
                {
                    "kind": "recommendation",
                    "id": str(recommendation.recommendation_id),
                    "title": localize(recommendation.title, lang),
                    "subtitle": localize(f"Saves about {money(recommendation.estimated_savings)} a month", lang),
                }
            )

    if room() > 0:
        alerts = (
            db.query(Alert)
            .filter(
                Alert.customer_id == customer_id,
                or_(
                    Alert.title.ilike(pattern, escape="\\"),
                    Alert.message.ilike(pattern, escape="\\"),
                    Alert.type.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Alert.date.desc())
            .limit(room())
            .all()
        )
        for alert in alerts:
            results.append(
                {
                    "kind": "alert",
                    "id": str(alert.alert_id),
                    "title": localize(alert.title, lang),
                    "subtitle": f"{alert.date.isoformat()} · {alert.severity}",
                }
            )

    return results


@router.get("", response_model=SearchResponseOut)
def search(
    q: str = Query("", description="What to search for"),
    limit: int = Query(8, ge=1, le=25, description="Maximum results to return"),
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
    lang: str = Depends(request_language),
):
    """
    Search whatever the caller is entitled to see.

    A query shorter than two characters returns nothing rather than the first
    N rows of every table, which is what a single-letter LIKE would produce.
    """
    term = q.strip()
    if len(term) < MIN_QUERY_LENGTH:
        return {"query": term, "results": []}

    if current_user.role == "admin":
        results = _admin_results(db, term, limit, lang)
    else:
        results = _customer_results(db, current_user.customer_id, term, limit, lang)

    return {"query": term, "results": results}
