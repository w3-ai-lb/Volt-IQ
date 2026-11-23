"""
AI Module: model evaluation.

The Trello board asks the same thing of every model: report figures, compare
against a baseline, and say honestly where the model does badly. A model that
has never been measured against an alternative cannot be defended, because
"it works well" is not a claim anyone can check.

This module produces those figures. It is deliberately separate from the
serving code: the models answer requests, this measures them, and the two
should not be able to flatter each other.

What is measured, and why that measure:

  forecasting     MAE, RMSE and MAPE from a rolling-origin backtest against
                  three baselines. Rolling-origin rather than one train/test
                  split, because a single split measures one lucky or unlucky
                  week. Never a random split: this is time-series data, and
                  shuffling it lets the model see the future.

  anomaly         Precision, recall and false-positive rate against the faults
                  the seeder plants deliberately. Those faults are the only
                  ground truth available, which is exactly why they exist.

  segmentation    Silhouette score across a range of k, so the number of
                  clusters is chosen from the data rather than assumed.

  risk            Score distribution and separation. Precision and recall are
                  NOT reported, and the reason is stated rather than hidden:
                  there are no default labels to compute them against.
"""

from __future__ import annotations

import logging
import warnings
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.ai import forecasting, risk
from app.models.anomaly import Anomaly
from app.models.consumption import Consumption
from app.models.customer import Customer

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

# Weeks held out of training and predicted one at a time.
BACKTEST_WEEKS = 8
# Below this there is not enough history to fit anything and still hold weeks
# back, so the backtest reports that rather than inventing numbers.
MIN_HISTORY_WEEKS = 32


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict:
    """MAE, RMSE and MAPE for one set of predictions."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    errors = predicted - actual

    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))

    # MAPE is undefined where the actual is zero, so those points are excluded
    # rather than silently producing infinity.
    nonzero = actual != 0
    mape = float(np.mean(np.abs(errors[nonzero] / actual[nonzero])) * 100) if nonzero.any() else 0.0

    return {
        "mae": round(mae, 1),
        "rmse": round(rmse, 1),
        "mape": round(mape, 2),
        "accuracy": round(max(0.0, 100.0 - mape), 1),
    }


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------
def _sarima_one_step(train: pd.Series) -> float | None:
    """Fit SARIMA on `train` and predict the single next week."""
    fit = forecasting._fit_sarima(train, 1)
    if fit is None:
        return None
    mean, _lower, _upper, _name = fit
    return float(mean[0])


def backtest_forecast(db: Session, weeks: int = BACKTEST_WEEKS) -> dict:
    """
    Rolling-origin backtest of the demand forecast.

    For each of the last `weeks` weeks: fit on everything strictly before it,
    predict that one week, and compare against what actually happened. The
    model never sees the week it is predicting, which is the whole point.

    Three baselines, because a model is only as good as what it beats:

      naive            next week equals this week. Hard to beat on a series
                       that changes slowly, and the honest bar to clear.
      seasonal naive   next week equals the same week last year, if there is
                       a year of history to look back at.
      moving average   mean of the last four weeks.
    """
    series = forecasting._load_weekly_series(db)

    if len(series) < MIN_HISTORY_WEEKS:
        return {
            "available": False,
            "reason": (
                f"{len(series)} weeks of history. A backtest needs at least "
                f"{MIN_HISTORY_WEEKS} so the model can be fitted on data that "
                "excludes the weeks being predicted."
            ),
        }

    weeks = min(weeks, len(series) - MIN_HISTORY_WEEKS + BACKTEST_WEEKS, len(series) // 4)
    split = len(series) - weeks

    actual: list[float] = []
    model_pred: list[float] = []
    naive_pred: list[float] = []
    seasonal_pred: list[float] = []
    moving_pred: list[float] = []
    sarima_fits = 0

    for step in range(weeks):
        cut = split + step
        train = series.iloc[:cut]
        truth = float(series.iloc[cut])

        prediction = _sarima_one_step(train)
        if prediction is None:
            # The serving code falls back the same way, so the backtest has to
            # measure what would actually be served, not an idealised model.
            mean, _l, _u, _n = forecasting._fallback_forecast(train, 1)
            prediction = float(mean[0])
        else:
            sarima_fits += 1

        actual.append(truth)
        model_pred.append(prediction)
        naive_pred.append(float(train.iloc[-1]))
        moving_pred.append(float(train.iloc[-4:].mean()))
        seasonal_pred.append(
            float(train.iloc[-52]) if len(train) >= 52 else float(train.iloc[-1])
        )

    actual_arr = np.asarray(actual)
    results = {
        "model": _metrics(actual_arr, np.asarray(model_pred)),
        "naive": _metrics(actual_arr, np.asarray(naive_pred)),
        "seasonal_naive": _metrics(actual_arr, np.asarray(seasonal_pred)),
        "moving_average": _metrics(actual_arr, np.asarray(moving_pred)),
    }

    model_mae = results["model"]["mae"]
    best_baseline = min(
        ("naive", "seasonal_naive", "moving_average"),
        key=lambda name: results[name]["mae"],
    )
    baseline_mae = results[best_baseline]["mae"]
    improvement = ((baseline_mae - model_mae) / baseline_mae * 100) if baseline_mae else 0.0

    return {
        "available": True,
        "weeks_tested": weeks,
        "history_weeks": len(series),
        "mean_weekly_kwh": round(float(series.mean()), 1),
        "sarima_fitted": sarima_fits,
        "fallback_used": weeks - sarima_fits,
        "results": results,
        "best_baseline": best_baseline,
        "improvement_over_best_baseline_pct": round(improvement, 1),
        "beats_baseline": model_mae < baseline_mae,
        # Said beside the figures, as the other evaluations below say theirs:
        # "accuracy" here is 100 minus the backtest's MAPE, a diagnostic.
        "limitations": [
            "A backtest diagnostic, not validated forecasting performance: each "
            "'accuracy' figure above is 100 minus that predictor's mean absolute "
            "percentage error over the weeks tested.",
            "On the supplied dataset: " + forecasting.FORECAST_LIMITATION,
        ],
    }


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------
# The faults the seeder plants, as (customer, days-ago-from, days-ago-to).
# Kept in step with _inject_anomalies in app/pipeline/seed.py.
SEEDED_FAULTS = [
    ("CUST-0007", 6, 9, "Night-time spike, faulty appliance"),
    ("CUST-0003", 10, 17, "Sustained drop, meter tampering signature"),
    ("CUST-0005", 3, 6, "Sudden sustained spike, unreported load"),
    ("CUST-0011", 2, 4, "Meter offline, no readings transmitted"),
]

# A detection counts as a hit if it lands within this many days of the fault.
# Daily aggregation and the edges of a multi-day fault both blur the boundary,
# so demanding an exact date would punish the detector for being approximately
# right, which is what detection is.
MATCH_TOLERANCE_DAYS = 2


def evaluate_anomaly(db: Session) -> dict:
    """
    Score the detector against the faults the seeder planted.

    Recall answers "did it find the real problems". Precision answers "how much
    of what it reported was worth looking at". Both matter, and the board is
    right that precision is the one usually skipped: a detector that flags
    every customer has perfect recall and is useless.

    This only works while the data comes from the seeder, which is what makes
    the planted faults ground truth. Against the supervisor's real dataset
    there are no labels, and this reports that instead of pretending.
    """
    # Anchored on the newest reading, not the wall clock. The seeder places
    # each fault a fixed number of days before the data ends, so measuring
    # against "now" would slide the windows off the faults by however long ago
    # the database was last built, and report misses that are really just the
    # calendar moving on.
    from sqlalchemy import func as sa_func

    newest = db.query(sa_func.max(Consumption.timestamp)).scalar()
    today = (newest or datetime.now(UTC)).replace(tzinfo=None)
    findings = db.query(Anomaly).all()
    customers = int(
        db.query(Customer.customer_id).filter(Customer.role == "customer").count() or 0
    )

    # Only meaningful if the seeded accounts are actually present.
    seeded_present = all(
        db.get(Customer, customer_id) is not None for customer_id, *_ in SEEDED_FAULTS
    )
    if not seeded_present or not findings:
        return {
            "available": False,
            "reason": (
                "Precision and recall need labelled faults. They exist only in "
                "seeded data. Load a dataset with known incidents, or label a "
                "sample by hand, to measure this against real readings."
            ),
            "total_findings": len(findings),
            "customers": customers,
        }

    detected: list[dict] = []
    matched_finding_ids: set[int] = set()

    for customer_id, from_days, to_days, label in SEEDED_FAULTS:
        window_start = today - timedelta(days=to_days + MATCH_TOLERANCE_DAYS)
        window_end = today - timedelta(days=from_days - MATCH_TOLERANCE_DAYS)

        hits = [
            f for f in findings
            if f.customer_id == customer_id
            and window_start <= f.detected_at.replace(tzinfo=None) <= window_end
        ]
        matched_finding_ids.update(f.anomaly_id for f in hits)
        detected.append(
            {
                "customer_id": customer_id,
                "fault": label,
                "detected": bool(hits),
                "findings": len(hits),
                "reported_as": sorted({f.type for f in hits}) if hits else [],
            }
        )

    true_positives = sum(1 for d in detected if d["detected"])
    false_negatives = len(SEEDED_FAULTS) - true_positives
    # Every finding that does not correspond to a planted fault. Some are
    # genuine noise in generated data rather than mistakes, so this is an upper
    # bound on the false-positive count, and it is reported as such.
    unmatched = [f for f in findings if f.anomaly_id not in matched_finding_ids]

    recall = true_positives / len(SEEDED_FAULTS) if SEEDED_FAULTS else 0.0
    precision = (
        len(matched_finding_ids) / len(findings) if findings else 0.0
    )
    flagged_customers = len({f.customer_id for f in findings})

    return {
        "available": True,
        "seeded_faults": len(SEEDED_FAULTS),
        "faults_detected": true_positives,
        "faults_missed": false_negatives,
        "recall": round(recall * 100, 1),
        "precision": round(precision * 100, 1),
        "total_findings": len(findings),
        "unmatched_findings": len(unmatched),
        "customers": customers,
        "customers_flagged": flagged_customers,
        "customers_flagged_pct": round(flagged_customers / customers * 100, 1) if customers else 0.0,
        "per_fault": detected,
        "note": (
            "Unmatched findings are an upper bound on false positives. Generated "
            "data contains real variation, so some are genuine outliers rather "
            "than mistakes."
        ),
    }


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------
def evaluate_segmentation(db: Session, k_range: tuple[int, ...] = (2, 3, 4, 5, 6)) -> dict:
    """
    Score the clustering across a range of k, so the number is chosen rather
    than assumed.

    Silhouette runs from -1 to 1 and measures how much better each customer
    fits its own cluster than the nearest other one. Inertia always falls as k
    rises, so on its own it would argue for one cluster per customer; the two
    together are what make a choice defensible.
    """
    from app.ai.segmentation import build_feature_frame

    frame = build_feature_frame(db)
    features = ["avg_monthly_kwh", "peak_kwh", "balance"]

    if frame.empty or len(frame) < 4:
        return {
            "available": False,
            "reason": f"{len(frame)} customers. Clustering needs at least 4 to compare values of k.",
        }

    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import silhouette_score
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        return {"available": False, "reason": "scikit-learn is not installed."}

    matrix = StandardScaler().fit_transform(frame[features].to_numpy(dtype=float))

    scores = []
    for k in k_range:
        if k >= len(frame):
            continue
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = model.fit_predict(matrix)
        if len(set(labels)) < 2:
            continue
        scores.append(
            {
                "k": k,
                "silhouette": round(float(silhouette_score(matrix, labels)), 3),
                "inertia": round(float(model.inertia_), 2),
                "sizes": sorted(np.bincount(labels).tolist(), reverse=True),
            }
        )

    if not scores:
        return {"available": False, "reason": "No value of k produced more than one cluster."}

    best = max(scores, key=lambda row: row["silhouette"])
    return {
        "available": True,
        "customers": len(frame),
        "features": features,
        "scores": scores,
        "best_k": best["k"],
        "best_silhouette": best["silhouette"],
        "k_in_use": 3,
        "note": (
            "The platform uses k=3 because the three segments carry business "
            "meaning the dashboard is built around: high, average and low "
            "consumers. Where the silhouette prefers a different k, that is "
            "recorded here rather than hidden, and the business reason for "
            "keeping three is the justification."
        ),
    }


# ---------------------------------------------------------------------------
# Payment-default risk
# ---------------------------------------------------------------------------
def evaluate_risk(db: Session) -> dict:
    """
    Describe what the risk score separates, and state plainly what cannot be
    measured.

    Precision and recall are absent on purpose. Both need to know who actually
    defaulted, and this dataset records no defaults: a customer is late, or
    overdue, or neither. Reporting a precision figure computed against
    "currently overdue" would be measuring the model against one of its own
    inputs, which would look like validation and be worth nothing.
    """
    scored = risk.score_all(db)
    if not scored:
        return {"available": False, "reason": "No customers to score."}

    known = [row for row in scored if row["band"] != "Unknown"]
    with_overdue = [row for row in known if row["overdue_bills"] > 0]
    without_overdue = [row for row in known if row["overdue_bills"] == 0]

    def mean_score(rows: list[dict]) -> float:
        return round(sum(r["score"] for r in rows) / len(rows), 1) if rows else 0.0

    bands: dict[str, int] = {}
    for row in scored:
        bands[row["band"]] = bands.get(row["band"], 0) + 1

    return {
        "available": True,
        "customers_scored": len(scored),
        "bands": bands,
        "score_range": [
            round(min(r["score"] for r in scored), 1),
            round(max(r["score"] for r in scored), 1),
        ],
        "mean_score_with_overdue": mean_score(with_overdue),
        "mean_score_without_overdue": mean_score(without_overdue),
        "separation": round(mean_score(with_overdue) - mean_score(without_overdue), 1),
        "thresholds": {"high": risk.BAND_HIGH, "medium": risk.BAND_MEDIUM},
        "limitations": [
            "No default labels exist in this dataset, so precision and recall "
            "cannot be computed. Any figure quoted for them would be invented.",
            "The band thresholds are chosen for how staff would use the list, "
            "not fitted to data: High means intervene now, Medium means worth a "
            "reminder. They should be revisited once real outcomes are known.",
            "An account holding a bill against which nothing at all has been "
            "paid is never banded Low, whatever its score. That is a policy "
            "rule, not something the model learned. It is deliberately keyed "
            "on a bill nobody has paid anything towards rather than on any "
            "unpaid bill: 292 of the 300 subscribers carry some arrears, so "
            "the wider rule promoted 281 accounts and separated nobody.",
            "The score is a weighted sum of four measured signals, not a trained "
            "classifier. It is transparent and explainable, and it cannot "
            "discover a pattern nobody thought to encode.",
        ],
    }


# ---------------------------------------------------------------------------
def evaluate_all(db: Session) -> dict:
    """Every model measured, for GET /ai/evaluation and the metrics report."""
    return {
        "forecasting": backtest_forecast(db),
        "anomaly_detection": evaluate_anomaly(db),
        "segmentation": evaluate_segmentation(db),
        "payment_risk": evaluate_risk(db),
    }
