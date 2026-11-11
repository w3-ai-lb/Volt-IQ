"""AI module schemas, forecast, segmentation, anomalies and chatbot."""

from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import CamelModel


# --- Demand Forecasting ----------------------------------------------------
class ForecastPoint(CamelModel):
    label: str
    actual: float | None = None   # None for future periods
    predicted: float
    lower: float
    upper: float


class ForecastCard(CamelModel):
    period: str          # 'Next Week' | 'Next Month' | 'Next Quarter'
    kwh: float
    change: float        # % vs previous period

    # The model's own 90% prediction interval for this horizon, summed over the
    # weeks the card covers.
    #
    # THIS REPLACED A FIELD CALLED `confidence`
    # -----------------------------------------
    # Which held 92, 88 and 81 when SARIMA was fitted and 84, 79 and 71 when it
    # was not. Six constants, chosen by nobody-remembers-what, printed on screen
    # as "Confidence: 84%": beside a Prediction Accuracy card on the very same
    # dashboard reporting 34.4%, which is measured by backtest. Two numbers
    # about the same model, one of them made up, and the made-up one was the
    # flattering one.
    #
    # The interval is what the model genuinely asserts, and it widens honestly
    # with the horizon: a quarter's range is wide because a quarter ahead is
    # hard, which is the thing the reader needs to know.
    lower: float
    upper: float


class ForecastInsights(CamelModel):
    trend: str                       # Increasing | Decreasing | Flat
    peak_period: str | None = None   # e.g. 'Week 9'
    peak_kwh: float | None = None
    model: str                       # SARIMA, or the fallback that was used
    weeks_observed: int
    horizon_weeks: int
    seasonal: bool
    uses_weather: bool


class ForecastResponse(CamelModel):
    forecast_data: list[ForecastPoint]
    forecast_cards: list[ForecastCard]
    # What the fit actually did, so the page can report it instead of printing
    # six fixed strings. Null when there was no data to fit.
    insights: ForecastInsights | None = None


# --- Customer Segmentation -------------------------------------------------
class SegmentOut(CamelModel):
    name: str
    count: int
    percentage: float
    color: str
    description: str


# --- Anomaly Detection -----------------------------------------------------
class AnomalyOut(CamelModel):
    id: str
    type: str
    customer: str        # customer_id, as rendered by the admin table
    severity: str
    value: str
    description: str
    date: date


# --- Chatbot ---------------------------------------------------------------
class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None


class ChatReply(CamelModel):
    reply: str
    conversation_id: int | None = None


class ChatHistoryOut(CamelModel):
    id: str
    title: str
    date: str            # 'Today' | 'Yesterday' | 'Last week' | ISO date
