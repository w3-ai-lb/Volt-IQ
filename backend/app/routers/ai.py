"""
AI router, exposes the AI module over REST.

  GET  /ai/forecast        demand forecasting  (admin)
  GET  /ai/segments        customer segmentation (admin)
  GET  /ai/anomalies       anomaly detection results (admin)
  POST /ai/anomalies/run   re-run detection on demand (admin)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai import forecasting, segmentation
from app.ai import anomaly as anomaly_ai
from app.ai import evaluation as evaluation_ai
from app.core.deps import require_admin
from app.core.i18n import localize, request_language
from app.database import get_db
from app.models.anomaly import Anomaly
from app.models.customer import Customer
from app.schemas.ai import AnomalyOut, ForecastResponse, SegmentOut

router = APIRouter(prefix="/ai", tags=["AI Module"])


def _serialize_anomaly(record: Anomaly, name: str | None = None, lang: str = "en") -> dict:
    detected = record.detected_at
    return {
        "id": f"an-{record.anomaly_id}",
        # Not translated here: the page keys its icons on the type and
        # translates it itself.
        "type": record.type,
        # The account number AND the name. A shortlist an administrator is
        # meant to act on that identifies people only as GEN-00018 makes them
        # look every one of them up before they can do anything with it.
        "customer": f"{name} ({record.customer_id})" if name else record.customer_id,
        "severity": record.severity,
        "value": localize(record.value, lang),
        "description": localize(record.description, lang),
        "date": detected.date() if detected else None,
    }


def _with_names(db: Session, records: list[Anomaly], lang: str = "en") -> list[dict]:
    ids = {record.customer_id for record in records}
    names = {
        customer_id: name
        for customer_id, name in db.query(Customer.customer_id, Customer.name)
        .filter(Customer.customer_id.in_(ids))
        .all()
    } if ids else {}
    return [_serialize_anomaly(record, names.get(record.customer_id), lang) for record in records]


@router.get("/forecast", response_model=ForecastResponse)
def get_forecast(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """System-wide electricity demand forecast (SARIMA with fallback)."""
    result = forecasting.generate_forecast(db)
    return {
        "forecast_data": result["forecastData"],
        "forecast_cards": result["forecastCards"],
        "insights": result.get("insights"),
    }


@router.get("/segments", response_model=list[SegmentOut])
def get_segments(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """
    KMeans customer segmentation, computed on demand.

    The description is written in the reader's language; the name is not,
    because the page keys its icons on it and translates it itself.
    """
    return [
        {**segment, "description": localize(segment["description"], lang)}
        for segment in segmentation.generate_segments(db)
    ]


# Whether this process has already tried to detect anomalies. See below.
_detection_attempted = False


@router.get("/anomalies", response_model=list[AnomalyOut])
def get_anomalies(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """Stored anomaly-detection findings, newest first."""
    records = (
        db.query(Anomaly)
        .filter(Anomaly.resolved.is_(False))
        # Newest first, then most unusual first. Every finding from the
        # monthly detector carries the same date, so without the second
        # key the shortlist came back in insertion order and the worst
        # case could sit anywhere in it.
        .order_by(Anomaly.detected_at.desc(), Anomaly.score.desc())
        .limit(50)
        .all()
    )

    # ONCE PER PROCESS, NOT ONCE PER PAGE LOAD
    # ----------------------------------------
    # "Run detection once so the page is never empty" was true only on a
    # database where the detector finds something. This provider's meters are
    # read monthly, the detector needs fourteen reading-days in ninety, and no
    # account has more than four, so it finds nothing and the table stays
    # empty — which meant this branch ran a full 300-customer pandas sweep on
    # every single request to a page that was always going to be empty.
    #
    # The intent is kept and the cost is not: one attempt per process, after
    # which an empty page is an answer rather than a reason to look again. The
    # page already explains why it is empty.
    global _detection_attempted
    if not records and not _detection_attempted:
        _detection_attempted = True
        anomaly_ai.run_detection(db)
        records = (
            db.query(Anomaly)
            .filter(Anomaly.resolved.is_(False))
            .order_by(Anomaly.detected_at.desc(), Anomaly.score.desc())
            .limit(50)
            .all()
        )

    return _with_names(db, records, lang)


@router.post("/anomalies/run", response_model=list[AnomalyOut])
def run_anomaly_detection(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
    lang: str = Depends(request_language),
):
    """
    Re-scan all customers with the anomaly model.

    It used to empty the table first. `run_detection` is documented as
    idempotent precisely so that a re-run refreshes a finding in place and
    "leaves `resolved` alone", and deleting everything a line above it threw
    that away: every anomaly an administrator had worked through and marked
    resolved came back on the next press of the button, indistinguishable from
    a new one. The upsert is the whole point; let it do its job.
    """
    global _detection_attempted
    _detection_attempted = True
    anomaly_ai.run_detection(db)
    records = (
        db.query(Anomaly)
        .filter(Anomaly.resolved.is_(False))
        # Newest first, then most unusual first. Every finding from the
        # monthly detector carries the same date, so without the second
        # key the shortlist came back in insertion order and the worst
        # case could sit anywhere in it.
        .order_by(Anomaly.detected_at.desc(), Anomaly.score.desc())
        .limit(50)
        .all()
    )
    return _with_names(db, records, lang)


@router.get("/evaluation")
def model_evaluation(
    db: Session = Depends(get_db),
    _: Customer = Depends(require_admin),
):
    """
    Measured performance of every model, with its baselines and limitations.

    Separate from the endpoints that serve predictions, so the numbers cannot
    be produced by the same code that would benefit from flattering them.
    Slow on first call: the forecast backtest fits SARIMA once per held-out
    week. The result is cached against the data, so it is paid once per load.
    """
    return evaluation_ai.evaluate_all(db)
