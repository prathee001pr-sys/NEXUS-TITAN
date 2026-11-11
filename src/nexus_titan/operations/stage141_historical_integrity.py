from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite


@dataclass(frozen=True)
class HistoricalBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class IntegrityReport:
    accepted: bool
    bar_count: int
    reasons: tuple[str, ...]
    research_authorized: bool = False
    live_authorized: bool = False


def review_historical_bars(
    bars,
    *,
    source: str,
    interval_minutes: int = 1,
) -> IntegrityReport:
    if type(source) is not str or not source.strip():
        raise ValueError("Data source required")

    if type(interval_minutes) is not int or interval_minutes < 1:
        raise ValueError("Invalid interval")

    if not isinstance(bars, (list, tuple)) or not bars:
        raise ValueError("Nonempty bars required")

    reasons = []
    previous = None

    for bar in bars:
        if not isinstance(bar, HistoricalBar):
            raise TypeError("HistoricalBar required")

        if (
            not isinstance(bar.timestamp, datetime)
            or bar.timestamp.tzinfo is None
            or bar.timestamp.utcoffset() is None
        ):
            reasons.append("missing_timezone")
        else:
            if previous is not None:
                if bar.timestamp == previous:
                    reasons.append("duplicate_timestamp")
                elif bar.timestamp < previous:
                    reasons.append("unordered_timestamp")
                elif (
                    bar.timestamp - previous
                    != timedelta(minutes=interval_minutes)
                ):
                    reasons.append("missing_or_irregular_interval")

            previous = bar.timestamp

        prices = (bar.open, bar.high, bar.low, bar.close)

        if any(
            type(price) not in (int, float)
            or not isfinite(price)
            or price <= 0
            for price in prices
        ):
            reasons.append("invalid_price")
        elif (
            bar.high < max(bar.open, bar.close, bar.low)
            or bar.low > min(bar.open, bar.close, bar.high)
        ):
            reasons.append("invalid_ohlc")

        if type(bar.volume) is not int or bar.volume < 0:
            reasons.append("invalid_volume")

    unique_reasons = tuple(dict.fromkeys(reasons))

    return IntegrityReport(
        accepted=not unique_reasons,
        bar_count=len(bars),
        reasons=unique_reasons,
        research_authorized=False,
        live_authorized=False,
    )
