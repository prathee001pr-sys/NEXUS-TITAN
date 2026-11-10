"""Stage101: bounded one-session 1-minute *synthetic* historical-bar preflight.

This is an evidence-quality gate, not licensed data import or proof of 15-year
minute coverage. Fixed-point INR paise, exact IST timestamps and SHA-256 lineage.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, time
import hashlib
import json


class Stage101Blocked(ValueError):
    """Fail closed on uncertain session or bar provenance."""


@dataclass(frozen=True, slots=True)
class Stage101SyntheticBar:
    symbol: str
    asof_ist: str
    open_paise: int
    high_paise: int
    low_paise: int
    close_paise: int
    volume: int
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"
    currency: str = "INR"
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage101DataWindow:
    symbol: str
    currency: str
    timeframe: str
    trading_date: str
    first_asof_ist: str
    last_asof_ist: str
    bar_count: int
    content_sha256: str
    min_close_paise: int
    max_close_paise: int
    contiguous_one_minute_bars: bool
    verified_trading_calendar: bool = False
    independent_market_source_verified: bool = False
    fifteen_year_history_verified: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SYNTHETIC_ONE_SESSION_ONLY_NO_GO"


def _number(name: str, value: object, *, positive: bool = False) -> int:
    if type(value) is not int or (value <= 0 if positive else value < 0) or value > 10**12:
        raise Stage101Blocked(f"{name} must be bounded integer")
    return value


def _ist(value: str) -> datetime:
    if type(value) is not str or len(value) > 40:
        raise Stage101Blocked("Invalid timestamp representation")
    try:
        x = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise Stage101Blocked("Invalid ISO-8601 bar timestamp") from exc
    if (x.tzinfo is None or x.utcoffset() != timedelta(hours=5, minutes=30)
            or x.isoformat() != value or x.second != 0 or x.microsecond != 0):
        raise Stage101Blocked("Minute bars require exact IST +05:30 minute boundary")
    if x.weekday() > 4 or not (time(9, 15) <= x.time() < time(15, 30)):
        raise Stage101Blocked("Not inside provisional regular Indian cash-market session")
    return x


def review_stage101_synthetic_window(bars: list[Stage101SyntheticBar] | tuple[Stage101SyntheticBar, ...]) -> Stage101DataWindow:
    """Reject gaps/duplicates/mismatches, including unknown holiday authenticity.

    Weekday bounds are only provisional; no official NSE holiday calendar is
    supplied, so the result cannot be treated as exchange-verified data.
    """
    if type(bars) not in (tuple, list) or not 1 <= len(bars) <= 375:
        raise Stage101Blocked("Provide 1–375 explicit one-session synthetic minute bars")
    prior: datetime | None = None
    closes: list[int] = []
    source_date = None
    symbol = None
    for bar in bars:
        if type(bar) is not Stage101SyntheticBar:
            raise Stage101Blocked("Expected exact immutable bar type")
        if (bar.symbol not in ("NIFTY", "BANKNIFTY") or type(bar.symbol) is not str
                or bar.source != "LOCAL_SYNTHETIC_TEST_ONLY"
                or bar.currency != "INR" or bar.live_trading_enabled is not False):
            raise Stage101Blocked("Untrusted, live or non-INR bar provenance")
        ts = _ist(bar.asof_ist)
        if symbol is None:
            symbol, source_date = bar.symbol, ts.date()
        if bar.symbol != symbol or ts.date() != source_date:
            raise Stage101Blocked("Mixed symbol or trading day is not one coherent window")
        if prior is not None and ts - prior != timedelta(minutes=1):
            raise Stage101Blocked("Duplicate, missing or unordered one-minute bar")
        prior = ts
        for field in ("open_paise", "high_paise", "low_paise", "close_paise"):
            _number(field, getattr(bar, field), positive=True)
        _number("volume", bar.volume)
        if bar.low_paise > min(bar.open_paise, bar.close_paise, bar.high_paise):
            raise Stage101Blocked("Bar low exceeds open/close/high")
        if bar.high_paise < max(bar.open_paise, bar.close_paise, bar.low_paise):
            raise Stage101Blocked("Bar high below open/close/low")
        closes.append(bar.close_paise)
    payload = json.dumps([asdict(b) for b in bars], sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert prior is not None and symbol is not None and source_date is not None
    return Stage101DataWindow(
        symbol=symbol, currency="INR", timeframe="1m", trading_date=source_date.isoformat(),
        first_asof_ist=bars[0].asof_ist, last_asof_ist=bars[-1].asof_ist,
        bar_count=len(bars), content_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        min_close_paise=min(closes), max_close_paise=max(closes), contiguous_one_minute_bars=True,
    )
