"""Validated, provider-independent historical candle retrieval."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from nexus_titan.data.ohlcv import CandleQuery, MarketDataSource, OHLCVCandle
from nexus_titan.data.quality import DataQualityReport, inspect_candle_batch
from nexus_titan.data.sessions import MarketCalendar


class MarketDataSourceContractError(TypeError):
    """Raised when an adapter violates the MarketDataSource return contract."""


class MarketDataValidationError(ValueError):
    """Raised when a provider returns candles that fail quality validation."""

    def __init__(self, report: DataQualityReport) -> None:
        self.report = report
        problems = []
        if report.duplicate_timestamps:
            problems.append("duplicate timestamps")
        if report.out_of_order_pairs:
            problems.append("out-of-order candles")
        if report.missing_intervals:
            problems.append("missing intervals")
        if report.outside_query:
            problems.append("candles outside query bounds")
        if report.identity_mismatches:
            problems.append("symbol/timeframe identity mismatch")
        super().__init__("market data validation failed: " + ", ".join(problems))


@dataclass(frozen=True, slots=True)
class ValidatedCandleBatch:
    """Immutable container for provider candles and their quality report."""

    candles: tuple[OHLCVCandle, ...]
    report: DataQualityReport


class MarketDataService:
    """Fetch candles through an adapter and reject invalid batches.

    This class performs no network work itself and has no broker/order methods.
    The injected source owns provider connectivity and credentials.
    """

    def __init__(
        self,
        source: MarketDataSource,
        *,
        calendar: MarketCalendar | None = None,
    ) -> None:
        if not callable(getattr(source, "fetch_candles", None)):
            raise TypeError("source must implement fetch_candles(query)")
        self._source = source
        self._calendar = calendar

    def fetch_validated(self, query: CandleQuery) -> ValidatedCandleBatch:
        received = self._source.fetch_candles(query)
        if not isinstance(received, Sequence) or isinstance(received, (str, bytes, bytearray)):
            raise MarketDataSourceContractError(
                "fetch_candles must return a sequence of OHLCVCandle objects"
            )
        candles = tuple(received)
        invalid = tuple(index for index, item in enumerate(candles) if not isinstance(item, OHLCVCandle))
        if invalid:
            raise MarketDataSourceContractError(
                f"fetch_candles returned non-OHLCVCandle items at indices: {invalid}"
            )
        report = inspect_candle_batch(candles, query, calendar=self._calendar)
        if not report.is_valid:
            raise MarketDataValidationError(report)
        return ValidatedCandleBatch(candles=candles, report=report)
