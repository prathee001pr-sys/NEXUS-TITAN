"""Configurable exchange session calendar with no embedded holiday assumptions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class TradingSession:
    """A local exchange session; open is inclusive and close is exclusive."""

    opens: time
    closes: time

    def __post_init__(self) -> None:
        if self.opens.tzinfo is not None or self.closes.tzinfo is not None:
            raise ValueError("session times must be local wall-clock times without timezone")
        if self.opens >= self.closes:
            raise ValueError("session open must be earlier than session close")


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    """Weekly sessions plus explicit full-day holidays and date overrides.

    Weekday keys use datetime.weekday(): Monday=0 through Sunday=6.
    A date override replaces the weekly schedule; an empty tuple closes that day.
    """

    timezone_name: str
    weekly_sessions: dict[int, tuple[TradingSession, ...]]
    holidays: frozenset[date] = frozenset()
    special_sessions: dict[date, tuple[TradingSession, ...]] | None = None

    def __post_init__(self) -> None:
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {self.timezone_name}") from exc
        for weekday, sessions in self.weekly_sessions.items():
            if weekday not in range(7):
                raise ValueError("weekday keys must be between 0 and 6")
            self._validate_sessions(sessions)
        for day, sessions in (self.special_sessions or {}).items():
            if not isinstance(day, date):
                raise ValueError("special session keys must be dates")
            self._validate_sessions(sessions)

    @staticmethod
    def _validate_sessions(sessions: tuple[TradingSession, ...]) -> None:
        ordered = sorted(sessions, key=lambda session: session.opens)
        if tuple(ordered) != sessions:
            raise ValueError("sessions must be ordered by opening time")
        for previous, current in zip(ordered, ordered[1:]):
            if current.opens < previous.closes:
                raise ValueError("sessions on the same day cannot overlap")

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def sessions_for_date(self, day: date) -> tuple[TradingSession, ...]:
        if day in self.holidays:
            return ()
        overrides = self.special_sessions or {}
        if day in overrides:
            return overrides[day]
        return self.weekly_sessions.get(day.weekday(), ())

    def is_trading_day(self, day: date) -> bool:
        return bool(self.sessions_for_date(day))

    def is_open(self, timestamp: datetime) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        local = timestamp.astimezone(self.zone)
        return any(
            session.opens <= local.timetz().replace(tzinfo=None) < session.closes
            for session in self.sessions_for_date(local.date())
        )


def nse_equity_derivatives_baseline(
    *,
    holidays: frozenset[date] = frozenset(),
    special_sessions: dict[date, tuple[TradingSession, ...]] | None = None,
) -> MarketCalendar:
    """Configurable regular-session baseline; callers must supply official holidays."""
    regular = (TradingSession(time(9, 15), time(15, 30)),)
    return MarketCalendar(
        timezone_name="Asia/Kolkata",
        weekly_sessions={weekday: regular for weekday in range(5)},
        holidays=holidays,
        special_sessions=special_sessions,
    )
