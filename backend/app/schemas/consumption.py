"""Consumption aggregation schemas, one per chart granularity."""

from app.schemas.common import CamelModel


class MonthlyConsumptionOut(CamelModel):
    """[{ month: 'Jan', period: '2026-01', kwh: 420, cost: 84 }]"""

    month: str
    # YYYY-MM. `month` alone cannot tell two Januaries apart, and the interface
    # needs the year to name the month in the reader's language.
    period: str | None = None
    kwh: float
    cost: float


class DailyConsumptionOut(CamelModel):
    """[{ day: 1, kwh: 14 }]"""

    day: int
    kwh: float


class HourlyConsumptionOut(CamelModel):
    """[{ hour: '0:00', kwh: 0.8 }]"""

    hour: str
    kwh: float


class HeatmapOut(CamelModel):
    """
    System-wide load by weekday and hour, for the admin dashboard heatmap.

    `grid[weekday][hour]` is the average kWh drawn across the whole customer
    base in that slot. `max_kwh` is supplied so the frontend can scale colour
    intensity without scanning the grid itself.
    """

    days: list[str]
    hours: list[str]
    grid: list[list[float]]
    max_kwh: float
    window_days: int
