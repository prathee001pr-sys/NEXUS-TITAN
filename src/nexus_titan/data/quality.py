"""Deterministic OHLCV batch quality checks; no network or market-calendar logic."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
from nexus_titan.data.sessions import MarketCalendar


_TIMEFRAME = re.compile(r"^(\d+)(m|h|d)$")


def timeframe_duration(timeframe: str) -> timedelta:
    """Convert supported minute/hour/day intervals to a fixed duration."""
    match = _TIMEFRAME.fullmatch(timeframe)
    if match is None:
        raise ValueError("unsupported timeframe; use values such as 1m, 5m, 1h or 1d")
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError("timeframe amount must be greater than zero")
    unit = match.group(2)
    return timedelta(minutes=amount) if unit == "m" else (
        timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
    )


@dataclass(frozen=True, slots=True)
class DataQualityReport:
    """Findings for a supplied candle batch; findings never modify input data."""

    candle_count: int
    duplicate_timestamps: tuple[datetime, ...]
    out_of_order_pairs: tuple[tuple[int, int], ...]
    missing_intervals: tuple[tuple[datetime, datetime], ...]
    outside_query: tuple[datetime, ...]
    identity_mismatches: tuple[int, ...]

    @property
    def is_valid(self) -> bool:
        return not any((
            self.duplicate_timestamps,
            self.out_of_order_pairs,
            self.missing_intervals,
            self.outside_query,
            self.identity_mismatches,
        ))


def inspect_candle_batch(
    candles: tuple[OHLCVCandle, ...] | list[OHLCVCandle],
    query: CandleQuery,
    *,
    calendar: MarketCalendar | None = None,
) -> DataQualityReport:
    """Inspect order, duplicates, gaps and query identity/bounds.

    Without a calendar, gap detection assumes continuous fixed-duration
    intervals. With a calendar, an expected timestamp outside a session is
    advanced to the next configured session open, including across dates,
    weekends and explicitly configured holidays. Calendar accuracy depends on
    caller-supplied schedules; no official exchange holiday feed is embedded.
    """
    expected = timeframe_duration(query.timeframe)
    duplicates: list[datetime] = []
    seen: set[datetime] = set()
    out_of_order: list[tuple[int, int]] = []
    gaps: list[tuple[datetime, datetime]] = []
    outside: list[datetime] = []
    mismatches: list[int] = []

    def next_expected_timestamp(previous_timestamp: datetime) -> datetime | None:
        if calendar is None:
            return previous_timestamp + expected
        local_previous = previous_timestamp.astimezone(calendar.zone)
        candidate = (previous_timestamp + expected).astimezone(calendar.zone)
        # If the next interval falls outside a session, advance to the next
        # configured session open. The bounded search avoids infinite loops
        # for calendars with no future sessions.
        for offset in range(0, 367):
            day = candidate.date() + timedelta(days=offset)
            sessions = calendar.sessions_for_date(day)
            for session in sessions:
                session_open = datetime.combine(day, session.opens, tzinfo=calendar.zone)
                session_close = datetime.combine(day, session.closes, tzinfo=calendar.zone)
                if offset == 0 and session_open <= candidate < session_close:
                    return candidate.astimezone(previous_timestamp.tzinfo)
                if session_open > local_previous and session_open >= candidate:
                    return session_open.astimezone(previous_timestamp.tzinfo)
        return None

    previous: tuple[int, OHLCVCandle] | None = None
    for index, item in enumerate(candles):
        if item.symbol != query.symbol or item.timeframe != query.timeframe:
            mismatches.append(index)
        if item.timestamp < query.start or item.timestamp >= query.end:
            outside.append(item.timestamp)
        if item.timestamp in seen and item.timestamp not in duplicates:
            duplicates.append(item.timestamp)
        seen.add(item.timestamp)

        if previous is not None:
            previous_index, previous_item = previous
            if item.timestamp < previous_item.timestamp:
                out_of_order.append((previous_index, index))
            elif item.timestamp > previous_item.timestamp:
                delta = item.timestamp - previous_item.timestamp
                if delta > expected:
                    candidate = next_expected_timestamp(previous_item.timestamp)
                    if candidate is not None and item.timestamp > candidate:
                        gaps.append((candidate, item.timestamp))
        previous = (index, item)

    return DataQualityReport(
        candle_count=len(candles),
        duplicate_timestamps=tuple(duplicates),
        out_of_order_pairs=tuple(out_of_order),
        missing_intervals=tuple(gaps),
        outside_query=tuple(outside),
        identity_mismatches=tuple(mismatches),
    )
