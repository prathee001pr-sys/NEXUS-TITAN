"""Provider-independent OHLCV market data contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Protocol, Sequence, runtime_checkable


def _decimal(value: Decimal | int | float | str, field: str) -> Decimal:
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a valid decimal number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class OHLCVCandle:
    """One completed or observed OHLCV candle; timestamp is candle open time."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: Decimal | int | float | str
    high: Decimal | int | float | str
    low: Decimal | int | float | str
    close: Decimal | int | float | str
    volume: Decimal | int | float | str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not isinstance(self.timeframe, str) or not self.timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        timestamp = self.timestamp.astimezone(timezone.utc)
        object.__setattr__(self, "timestamp", timestamp)

        for field in ("open", "high", "low", "close", "volume"):
            object.__setattr__(self, field, _decimal(getattr(self, field), field))

        if any(getattr(self, field) <= 0 for field in ("open", "high", "low", "close")):
            raise ValueError("OHLC prices must be greater than zero")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close and high")


@dataclass(frozen=True, slots=True)
class CandleQuery:
    """Time-bounded request; end is exclusive."""

    symbol: str
    timeframe: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty")
        for field in ("start", "end"):
            value = getattr(self, field)
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field} must be a timezone-aware datetime")
            object.__setattr__(self, field, value.astimezone(timezone.utc))
        if self.start >= self.end:
            raise ValueError("query start must be earlier than end")


@runtime_checkable
class MarketDataSource(Protocol):
    """Adapter contract implemented by historical or live market data providers."""

    def fetch_candles(self, query: CandleQuery) -> Sequence[OHLCVCandle]:
        """Return candles matching the query, ordered oldest to newest."""
        ...
