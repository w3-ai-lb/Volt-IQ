"""
AI Module, Electricity Demand Forecasting.

Primary model : SARIMA (statsmodels), captures the weekly/seasonal structure
                that dominates electricity demand.
Fallback      : Holt linear trend + seasonal naive, used when statsmodels is
                unavailable or history is too short to fit SARIMA.

The forecast is SYSTEM-WIDE (all customers aggregated), matching the note in
Section VII of the Software Architecture that the Forecast entity is not tied
to an individual customer.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.consumption import Consumption

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")

HISTORY_WEEKS = 8      # weeks of actuals shown on the chart
HORIZON_WEEKS = 5      # weeks predicted into the future

# What the backtest figure is worth on the supplied dataset, word for word as
# approved for the README and the academic report. Printed wherever that
# figure is (the Forecast Report, GET /ai/evaluation), so it is never shown as
# validated forecasting performance.
FORECAST_LIMITATION = (
    "Meters are read once a month over approximately ten days, so the weekly series "
    "contains observations in only 42 of its 76 calendar weeks, at irregular intervals. "
    "Consequently, a backtest on this series measures the effects of the reading schedule "
    "and does not establish reliable demand-forecasting performance."
)

# ---------------------------------------------------------------------------
# Caching
#
# Fitting SARIMA takes roughly a second and a half, and the forecast is
# system-wide, so every admin loading the dashboard was paying to compute the
# identical answer. SRS Section IV asks for dashboards in 3-4 seconds and this
# was the slowest call on the page.
#
# The cache key is a fingerprint of the consumption table: its row count and
# newest timestamp. Loading data changes both, so a stale forecast cannot
# survive an ingest; nothing has to remember to clear anything.
# ---------------------------------------------------------------------------
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
FORECAST_ARTIFACT = ARTIFACT_DIR / "forecast.json"

# In-process, so the two calls the admin dashboard makes (forecast and
# accuracy) share one read of the table instead of two.
_series_cache: tuple[str, pd.Series] | None = None


def _data_fingerprint(db: Session) -> str:
    """Cheap signature of the consumption table: row count and newest reading."""
    count, newest = db.query(
        func.count(Consumption.consumption_id),
        func.max(Consumption.timestamp),
    ).one()
    return f"{int(count or 0)}:{newest.isoformat() if newest else 'none'}"


def _read_artifact(fingerprint: str) -> dict | None:
    """Return the stored forecast if it was built from this exact data."""
    try:
        if not FORECAST_ARTIFACT.exists():
            return None
        stored = json.loads(FORECAST_ARTIFACT.read_text(encoding="utf-8"))
        if stored.get("fingerprint") != fingerprint:
            return None
        payload = stored.get("payload")
        if not isinstance(payload, dict):
            return None

        # The fingerprint covers the DATA, not the code. An artifact written by
        # an older version of this module has an older SHAPE, and serving it
        # produces a 500 from response validation, which is what happened
        # twice: once when `insights` was added, and again when the forecast
        # cards stopped carrying an invented `confidence` and started carrying
        # the model's real interval.
        #
        # Checking for one key by name fixes only the change you just made.
        # Validating against the response model checks every field there is,
        # and keeps checking when somebody adds the next one.
        from app.schemas.ai import ForecastResponse

        try:
            ForecastResponse.model_validate(payload)
        except Exception:
            logger.info("Discarding a forecast artifact written by an older build")
            return None
        return payload
    except Exception:
        # A corrupt or unreadable artifact must never break the endpoint,
        # the worst case is that the forecast is recomputed.
        logger.warning("Ignoring unreadable forecast artifact", exc_info=True)
        return None


def _write_artifact(fingerprint: str, payload: dict) -> None:
    try:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        FORECAST_ARTIFACT.write_text(
            json.dumps({"fingerprint": fingerprint, "payload": payload}),
            encoding="utf-8",
        )
    except Exception:
        logger.warning("Could not persist forecast artifact", exc_info=True)


def invalidate_cache() -> None:
    """Drop every cache. Called after a data load."""
    global _series_cache, _accuracy_cache
    _series_cache = None
    _accuracy_cache = None
    try:
        FORECAST_ARTIFACT.unlink(missing_ok=True)
    except Exception:
        logger.warning("Could not remove forecast artifact", exc_info=True)


def _weekly_series_cached(db: Session, fingerprint: str) -> pd.Series:
    global _series_cache
    if _series_cache is not None and _series_cache[0] == fingerprint:
        return _series_cache[1]
    series = _load_weekly_series(db)
    _series_cache = (fingerprint, series)
    return series


def _load_weekly_series(db: Session) -> pd.Series:
    """
    Aggregate every consumption record into a weekly total-kWh series.

    The final bucket is dropped when it is still in progress: "today" almost
    never lands on a week boundary, so the last bucket would otherwise hold a
    partial week and read as a sudden collapse in demand, which the model
    would faithfully extrapolate into nonsense.
    """
    rows = db.query(Consumption.timestamp, Consumption.kwh).all()
    if not rows:
        return pd.Series(dtype="float64")

    df = pd.DataFrame(rows, columns=["timestamp", "kwh"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    weekly = df.set_index("timestamp")["kwh"].resample("W").sum()
    weekly = weekly[weekly > 0]

    # resample("W") labels each bucket with its week-ENDING date. If that date
    # is later than the last reading we hold, the week is incomplete.
    if len(weekly) > 1 and weekly.index[-1] > df["timestamp"].max():
        weekly = weekly.iloc[:-1]

    return weekly


def _is_plausible(forecast: np.ndarray, series: pd.Series) -> bool:
    """
    Reject a diverging fit.

    An over-parameterised SARIMA on a short series can oscillate and explode
    (alternating huge positive and negative values). Electricity demand is
    strictly positive and changes gradually, so a forecast that goes negative
    or leaves the historical envelope is wrong regardless of how well the
    model fitted in-sample.
    """
    if not np.all(np.isfinite(forecast)):
        return False
    if np.any(forecast <= 0):
        return False

    history_max = float(series.max())
    history_min = float(series.min())
    if np.any(forecast > history_max * 2.0) or np.any(forecast < history_min * 0.4):
        return False

    # Week-on-week swings beyond 60% are not physical at system level.
    steps = np.diff(np.concatenate([[float(series.iloc[-1])], forecast]))
    if np.any(np.abs(steps) > float(series.mean()) * 0.6):
        return False

    return True


def _fit_sarima(series: pd.Series, horizon: int):
    """
    Fit SARIMA and return (mean, lower, upper, name), or None to fall back.

    Seasonal period is chosen from the amount of history available: a yearly
    cycle (52 weeks) needs at least two full years, otherwise a short monthly
    cycle is used, which is far more stable on limited data.
    """
    if len(series) < 24:
        return None

    seasonal_period = 52 if len(series) >= 130 else 4

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        model = SARIMAX(
            series,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, seasonal_period),
            enforce_stationarity=True,
            enforce_invertibility=True,
        )
        fitted = model.fit(disp=False, maxiter=200)
        result = fitted.get_forecast(steps=horizon)
        conf = result.conf_int(alpha=0.10)  # 90% confidence interval

        mean = np.asarray(result.predicted_mean, dtype=float)
        if not _is_plausible(mean, series):
            logger.warning("SARIMA produced an implausible forecast, using fallback model")
            return None

        lower = np.clip(np.asarray(conf.iloc[:, 0], dtype=float), 0, None)
        upper = np.asarray(conf.iloc[:, 1], dtype=float)
        return mean, lower, upper, "SARIMA"
    except Exception as exc:  # pragma: no cover - model fitting is best-effort
        logger.warning("SARIMA fit failed, using fallback model: %s", exc)
        return None


def _fallback_forecast(series: pd.Series, horizon: int):
    """
    Damped linear trend on the recent window + residual-based confidence band.

    The trend is damped (each step further out contributes less) so the
    forecast flattens instead of running away, and it is floored at 40% of the
    recent mean because system-wide demand never approaches zero.
    """
    values = series.to_numpy(dtype=float)
    window = values[-12:] if len(values) >= 12 else values

    if len(window) >= 2:
        x = np.arange(len(window))
        slope, intercept = np.polyfit(x, window, 1)
        last_fitted = slope * (len(window) - 1) + intercept

        # Damping factor 0.85: cumulative trend contribution converges.
        damping = np.cumsum(0.85 ** np.arange(1, horizon + 1))
        mean = last_fitted + slope * damping

        residual_std = float(np.std(window - (slope * x + intercept))) or float(np.std(window))
    else:
        mean = np.repeat(window.mean() if len(window) else 0.0, horizon)
        residual_std = float(np.std(values)) if len(values) else 0.0

    floor = float(np.mean(window)) * 0.4 if len(window) else 0.0
    mean = np.clip(mean, floor, None)

    # Uncertainty widens the further out we predict.
    spread = residual_std * 1.64 * np.sqrt(np.arange(1, horizon + 1))
    return mean, np.clip(mean - spread, 0, None), mean + spread, "Damped-Trend"


def generate_forecast(db: Session) -> dict:
    """
    Produce the payload consumed by GET /ai/forecast.

    Returns { forecastData: [...], forecastCards: [...] } exactly as the
    DemandForecast page expects.

    Served from the artifact cache when the consumption table has not changed
    since the last fit, see the note on caching at the top of this module.
    """
    fingerprint = _data_fingerprint(db)

    cached = _read_artifact(fingerprint)
    if cached is not None:
        return cached

    series = _weekly_series_cached(db, fingerprint)

    if series.empty:
        return {"forecastData": [], "forecastCards": [], "insights": None}

    fit = _fit_sarima(series, HORIZON_WEEKS)
    if fit is None:
        mean, lower, upper, model_name = _fallback_forecast(series, HORIZON_WEEKS)
    else:
        mean, lower, upper, model_name = fit

    history = series.tail(HISTORY_WEEKS)
    points: list[dict] = []

    # Past weeks: actual + in-sample "predicted" (3-week rolling mean).
    smoothed = history.rolling(window=3, min_periods=1).mean()
    for i, (_, actual) in enumerate(history.items(), start=1):
        fitted_value = float(smoothed.iloc[i - 1])
        points.append(
            {
                "label": f"Week {i}",
                "actual": round(float(actual), 1),
                "predicted": round(fitted_value, 1),
                "lower": round(fitted_value * 0.94, 1),
                "upper": round(fitted_value * 1.06, 1),
            }
        )

    # Future weeks: prediction only (actual = None -> null in JSON).
    offset = len(points)
    for i in range(HORIZON_WEEKS):
        points.append(
            {
                "label": f"Week {offset + i + 1}",
                "actual": None,
                "predicted": round(float(mean[i]), 1),
                "lower": round(float(lower[i]), 1),
                "upper": round(float(upper[i]), 1),
            }
        )

    # --- Summary cards -----------------------------------------------------
    weekly_avg = float(history.mean()) if len(history) else 0.0
    next_week = float(mean[0])
    next_month = float(np.sum(mean[: min(4, len(mean))]))
    # Extrapolate a quarter from the average weekly prediction (13 weeks).
    next_quarter = float(np.mean(mean) * 13)

    def pct_change(new: float, base: float) -> float:
        return round(((new - base) / base) * 100, 1) if base else 0.0

    # The model's own bounds, aggregated over the weeks each card covers. A
    # quarter is thirteen weeks and the fit is five, so its interval is scaled
    # by the same factor as its central estimate: the extrapolation and its
    # uncertainty have to travel together, or the card promises a precision the
    # forecast does not have.
    weeks_fitted = max(1, len(mean))
    month_weeks = min(4, len(mean))
    quarter_scale = 13.0 / weeks_fitted

    def band(scale_from: int | None = None, factor: float = 1.0) -> tuple[float, float]:
        if scale_from is None:
            low = float(np.sum(lower)) * factor
            high = float(np.sum(upper)) * factor
        else:
            low = float(np.sum(lower[:scale_from]))
            high = float(np.sum(upper[:scale_from]))
        return round(low, 0), round(high, 0)

    week_low, week_high = round(float(lower[0]), 0), round(float(upper[0]), 0)
    month_low, month_high = band(month_weeks)
    quarter_low, quarter_high = band(None, quarter_scale)

    cards = [
        {
            "period": "Next Week",
            "kwh": round(next_week, 0),
            "lower": week_low,
            "upper": week_high,
            "change": pct_change(next_week, weekly_avg),
        },
        {
            "period": "Next Month",
            "kwh": round(next_month, 0),
            "lower": month_low,
            "upper": month_high,
            "change": pct_change(next_month / 4 if next_month else 0, weekly_avg),
        },
        {
            "period": "Next Quarter",
            "kwh": round(next_quarter, 0),
            "lower": quarter_low,
            "upper": quarter_high,
            "change": pct_change(next_quarter / 13 if next_quarter else 0, weekly_avg),
        },
    ]

    # --- What the model actually did ---------------------------------------
    # The Forecast page printed six fixed strings under "Forecast Insights":
    # Trend Increasing, Peak Week 7-8, Model accuracy 94.2%, Data points used
    # 8,760 hours, Seasonal adjustment Applied, Weather factor Included. None
    # was computed, and the last one was untrue: no weather series is used
    # anywhere in this project. These are the same six facts, measured.
    future = [p for p in points if p["actual"] is None]
    peak = max(future, key=lambda p: p["predicted"], default=None)

    first_prediction = float(mean[0]) if len(mean) else 0.0
    last_prediction = float(mean[-1]) if len(mean) else 0.0
    if weekly_avg and abs(last_prediction - first_prediction) / max(weekly_avg, 1e-9) < 0.02:
        trend = "Flat"
    elif last_prediction > first_prediction:
        trend = "Increasing"
    else:
        trend = "Decreasing"

    insights = {
        "trend": trend,
        "peak_period": peak["label"] if peak else None,
        "peak_kwh": peak["predicted"] if peak else None,
        "model": model_name,
        "weeks_observed": int(len(series)),
        "horizon_weeks": int(HORIZON_WEEKS),
        # SARIMA here carries a 52-week seasonal term; the fallback does not.
        "seasonal": model_name == "SARIMA",
        # Stated so the page can say it plainly rather than claim otherwise.
        "uses_weather": False,
    }

    payload = {"forecastData": points, "forecastCards": cards, "insights": insights}
    _write_artifact(fingerprint, payload)
    logger.info("Forecast fitted with %s and cached", model_name)
    return payload


# Backtest results, cached like the forecast: measuring costs eight SARIMA
# fits, and the answer only changes when the data does.
_accuracy_cache: tuple[str, float] | None = None


def model_accuracy(db: Session) -> float | None:
    """
    The backtest figure of the model actually being served: 100 - MAPE,
    measured by rolling-origin backtest. A diagnostic, not validated forecasting
    accuracy (FORECAST_LIMITATION above says why). None when there is not
    enough history to measure.

    Feeds the `predictionAccuracy` stat on the admin dashboard, which the card
    labels Forecast backtest (the field keeps its name so the API does not
    change).

    WHY None AND NOT 0.0
    --------------------
    It returned 0.0 when the backtest could not run, and the dashboard printed
    it as "0%". A reader cannot tell that apart from a model that is wrong
    every single time, and it is the first number an evaluator looks at. A
    dataset of under 32 weeks is the ordinary case for a first real load, so
    this was going to be the first thing the platform said about itself.
    None means "not measured"; the page says so in words.

    This used to compute the MAPE of `series.shift(1)`: next week equals this
    week. That is the naive baseline, not the model. The dashboard was
    reporting how well a model nobody was running would have done, under a
    label claiming it was the forecast's accuracy. On the seeded data the two
    differ by roughly half a percentage point in the baseline's favour, so the
    figure was not only mislabelled but flattering.
    """
    global _accuracy_cache

    fingerprint = _data_fingerprint(db)
    if _accuracy_cache is not None and _accuracy_cache[0] == fingerprint:
        return _accuracy_cache[1]

    # Imported here rather than at module scope: evaluation imports this
    # module, and measuring the forecaster is not the forecaster's job.
    from app.ai import evaluation

    report = evaluation.backtest_forecast(db)
    if not report.get("available"):
        return None

    accuracy = float(report["results"]["model"]["accuracy"])
    _accuracy_cache = (fingerprint, accuracy)
    return accuracy


def total_system_consumption(db: Session) -> float:
    """Total kWh across all customers (used by the KPI tiles)."""
    return float(db.query(func.coalesce(func.sum(Consumption.kwh), 0.0)).scalar() or 0.0)
