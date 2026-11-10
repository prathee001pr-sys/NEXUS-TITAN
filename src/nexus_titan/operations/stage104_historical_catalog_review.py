"""Stage104: bounded multi-session synthetic F&O minute-bar catalog preflight.

Only Stage101 checked *synthetic* windows are accepted. This is neither a
licensed market feed nor a claim that a holiday calendar or 15-year coverage
was checked. Catalog hashes are local fingerprints, not external attestations.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from hashlib import sha256
import json
import re
from .stage101_historical_bar_preflight import Stage101DataWindow

_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)

class Stage104Blocked(ValueError):
    pass

@dataclass(frozen=True, slots=True)
class Stage104Catalog:
    symbol: str
    currency: str
    first_date: str
    last_date: str
    session_count: int
    minute_bar_count: int
    source_window_hashes: tuple[str, ...]
    catalog_sha256: str
    complete_trading_calendar_verified: bool = False
    independent_data_provider_verified: bool = False
    historical_15y_coverage_verified: bool = False
    strategy_signal_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SYNTHETIC_CATALOG_STRUCTURE_ONLY_NO_GO"


def review_stage104_catalog(windows: list[Stage101DataWindow] | tuple[Stage101DataWindow, ...]) -> Stage104Catalog:
    """Check ordered, bounded, non-overlapping windows without inferring holidays."""
    if type(windows) not in (list, tuple) or not 1 <= len(windows) <= 20:
        raise Stage104Blocked("1 to 20 explicit synthetic source windows required")
    hashes: list[str] = []
    days: list[str] = []
    symbol: str | None = None
    total = 0
    last_date: date | None = None
    for w in windows:
        if type(w) is not Stage101DataWindow:
            raise Stage104Blocked("Exact Stage101 window type required")
        if (w.symbol not in ("NIFTY", "BANKNIFTY") or w.currency != "INR"
            or w.timeframe != "1m" or w.contiguous_one_minute_bars is not True
            or w.verified_trading_calendar is not False or w.independent_market_source_verified is not False
            or w.fifteen_year_history_verified is not False or w.live_trading_enabled is not False
            or w.verdict != "SYNTHETIC_ONE_SESSION_ONLY_NO_GO"):
            raise Stage104Blocked("Unsupported market, currency, or data authenticity claim")
        if type(w.content_sha256) is not str or not _HEX.fullmatch(w.content_sha256):
            raise Stage104Blocked("Invalid source-window hash")
        if type(w.bar_count) is not int or not 1 <= w.bar_count <= 375:
            raise Stage104Blocked("Invalid bounded minute-bar count")
        if (type(w.min_close_paise) is not int or type(w.max_close_paise) is not int
            or not 0 < w.min_close_paise <= w.max_close_paise <= 10**12):
            raise Stage104Blocked("Invalid bounded close range")
        if symbol is None: symbol = w.symbol
        if w.symbol != symbol:
            raise Stage104Blocked("Mixed underlyings not supported")
        try:
            d = date.fromisoformat(w.trading_date)
            first = datetime.fromisoformat(w.first_asof_ist)
            last = datetime.fromisoformat(w.last_asof_ist)
        except (TypeError, ValueError, AttributeError) as exc:
            raise Stage104Blocked("Malformed source-window clock") from exc
        ist = timedelta(hours=5, minutes=30)
        if (d.isoformat() != w.trading_date or d.weekday() > 4
            or first.utcoffset() != ist or last.utcoffset() != ist
            or first.isoformat() != w.first_asof_ist or last.isoformat() != w.last_asof_ist
            or first.date() != d or last.date() != d
            or not time(9, 15) <= first.time() <= last.time() < time(15, 30)
            or first.second != 0 or last.second != 0
            or first.microsecond != 0 or last.microsecond != 0
            or (last - first) != timedelta(minutes=w.bar_count - 1)):
            raise Stage104Blocked("Minute catalog clock/count mismatch")
        if last_date is not None and d <= last_date:
            raise Stage104Blocked("Duplicate, reversed, or overlapping trading session")
        last_date = d
        days.append(w.trading_date)
        hashes.append(w.content_sha256)
        total += w.bar_count
    assert symbol is not None
    payload = ["STAGE104_SYNTHETIC_CATALOG_V1", symbol, days, hashes,
               [w.bar_count for w in windows]]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage104Catalog(symbol, "INR", days[0], days[-1], len(days), total,
                           tuple(hashes), digest)
