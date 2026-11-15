"""Stage102: bounded point-in-time CE/PE paired *synthetic* option-chain QA.

No option-chain feed, broker execution, expiry-calendar or liquidity approval.
Strict linkage to a Stage101 synthetic 1-minute bar window.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import re

from .stage101_historical_bar_preflight import Stage101DataWindow


class Stage102Blocked(ValueError):
    """Fail closed if option-chain provenance/structure cannot be established."""


@dataclass(frozen=True, slots=True)
class Stage102SyntheticQuote:
    contract_id: str
    underlying: str
    expiry_date: str
    observed_at_ist: str
    option_type: str
    strike_paise: int
    bid_paise: int
    ask_paise: int
    open_interest: int
    volume: int
    lot_size: int
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"
    currency: str = "INR"
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage102ChainReview:
    underlying: str
    expiry_date: str
    observed_at_ist: str
    currency: str
    source_window_sha256: str
    chain_sha256: str
    quote_count: int
    paired_strike_count: int
    paired_strikes_paise: tuple[int, ...]
    quote_staleness_seconds: int
    structural_chain_valid: bool
    official_option_chain_verified: bool = False
    official_expiry_calendar_verified: bool = False
    executable_liquidity_verified: bool = False
    broker_order_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SYNTHETIC_OPTION_CHAIN_STRUCTURE_ONLY_NO_GO"


_ID = re.compile(r"(NIFTY|BANKNIFTY)-(\d{4}-\d{2}-\d{2})-(CE|PE)-(\d+)\Z", re.ASCII)
_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)


def _int(name: str, number: object, *, positive: bool = False) -> int:
    if type(number) is not int or number > 10**12 or (number <= 0 if positive else number < 0):
        raise Stage102Blocked(f"Invalid {name} fixed-point quantity")
    return number


def _parse_stamp(raw: str) -> datetime:
    if type(raw) is not str or len(raw) > 40:
        raise Stage102Blocked("Invalid quote timestamp")
    try:
        timestamp = datetime.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise Stage102Blocked("Invalid ISO quote timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(hours=5, minutes=30):
        raise Stage102Blocked("Quote must use IST +05:30")
    return timestamp


def review_stage102_synthetic_chain(
    window: Stage101DataWindow,
    quotes: list[Stage102SyntheticQuote] | tuple[Stage102SyntheticQuote, ...],
    *,
    max_quote_age_seconds: int = 30,
) -> Stage102ChainReview:
    """Strict point-in-time quote consistency against one checked synthetic bar."""
    if type(window) is not Stage101DataWindow or type(quotes) not in (tuple, list):
        raise Stage102Blocked("Typed Stage101 source window and explicit quote list required")
    if (window.symbol not in ("NIFTY", "BANKNIFTY") or window.currency != "INR"
            or window.timeframe != "1m" or window.contiguous_one_minute_bars is not True
            or window.verified_trading_calendar is not False
            or window.independent_market_source_verified is not False
            or window.fifteen_year_history_verified is not False
            or window.live_trading_enabled is not False
            or window.verdict != "SYNTHETIC_ONE_SESSION_ONLY_NO_GO"
            or type(window.content_sha256) is not str
            or not _HEX.fullmatch(window.content_sha256)
            or type(window.bar_count) is not int or not 1 <= window.bar_count <= 375):
        raise Stage102Blocked("Stage101 upstream window provenance not supported")
    if type(max_quote_age_seconds) is not int or not 0 <= max_quote_age_seconds <= 60:
        raise Stage102Blocked("Invalid bounded synthetic chain quote staleness tolerance")
    if not 2 <= len(quotes) <= 100 or len(quotes) % 2:
        raise Stage102Blocked("CE/PE paired chain must contain 2–100 quotes")
    last_bar = _parse_stamp(window.last_asof_ist)
    if last_bar.isoformat() != window.last_asof_ist:
        raise Stage102Blocked("Stage101 last bar has non-canonical timestamp")
    if last_bar.date().isoformat() != window.trading_date:
        raise Stage102Blocked("Stage101 trading day and time disagree")
    pair: dict[int, set[str]] = {}
    strike_lots: dict[int, int] = {}
    seen: set[str] = set()
    expiry_day = None
    observed = None
    for quote in quotes:
        if type(quote) is not Stage102SyntheticQuote:
            raise Stage102Blocked("Expected exact synthetic option quote")
        if (type(quote.contract_id) is not str or len(quote.contract_id) > 120
                or quote.underlying != window.symbol or quote.currency != "INR"
                or quote.source != "LOCAL_SYNTHETIC_TEST_ONLY"
                or quote.live_trading_enabled is not False
                or quote.option_type not in ("CE", "PE")):
            raise Stage102Blocked("Untrusted live, non-INR or wrong-contract quote")
        match = _ID.fullmatch(quote.contract_id)
        if (not match or match.group(1) != quote.underlying
                or match.group(2) != quote.expiry_date
                or match.group(3) != quote.option_type
                or int(match.group(4)) != quote.strike_paise):
            raise Stage102Blocked("Synthetic contract strike, type or expiry ID mismatch")
        if quote.contract_id in seen:
            raise Stage102Blocked("Duplicate synthetic chain contract ID")
        seen.add(quote.contract_id)
        try:
            expiry = date.fromisoformat(quote.expiry_date)
        except (TypeError, ValueError) as exc:
            raise Stage102Blocked("Invalid quoted expiry date") from exc
        if expiry < last_bar.date() or (expiry_day is not None and expiry != expiry_day):
            raise Stage102Blocked("Expired or mixed-expiry option chain")
        expiry_day = expiry
        stamp = _parse_stamp(quote.observed_at_ist)
        if observed is not None and stamp != observed:
            raise Stage102Blocked("Asynchronous option-chain quote times")
        observed = stamp
        # Allow a small lag from the last source bar, but never future or old feed.
        age = int((last_bar - stamp).total_seconds())
        if stamp > last_bar or age < 0 or age > max_quote_age_seconds:
            raise Stage102Blocked("Future or stale synthetic option-chain mark")
        for name in ("strike_paise", "ask_paise", "lot_size", "open_interest"):
            _int(name, getattr(quote, name), positive=True)
        for name in ("bid_paise", "volume"):
            _int(name, getattr(quote, name))
        if quote.bid_paise > quote.ask_paise or quote.lot_size > 10000:
            raise Stage102Blocked("Crossed quote or unreasonable lot size")
        if (quote.ask_paise - quote.bid_paise) * 100 > quote.ask_paise * 50:
            raise Stage102Blocked("Wide synthetic quote: research-quality gate failed")
        if quote.strike_paise in strike_lots and strike_lots[quote.strike_paise] != quote.lot_size:
            raise Stage102Blocked("Paired strike must share the same lot size")
        strike_lots[quote.strike_paise] = quote.lot_size
        side = pair.setdefault(quote.strike_paise, set())
        if quote.option_type in side:
            raise Stage102Blocked("Repeated CE or PE at identical strike")
        side.add(quote.option_type)
    if any(sides != {"CE", "PE"} for sides in pair.values()):
        raise Stage102Blocked("Missing CE/PE counterpart at a strike")
    if observed is None or expiry_day is None:
        raise Stage102Blocked("No quote timestamp or expiry")
    payload = json.dumps([asdict(q) for q in quotes], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return Stage102ChainReview(
        underlying=window.symbol, expiry_date=expiry_day.isoformat(),
        observed_at_ist=observed.isoformat(), currency="INR",
        source_window_sha256=window.content_sha256,
        chain_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        quote_count=len(quotes), paired_strike_count=len(pair),
        paired_strikes_paise=tuple(sorted(pair)),
        quote_staleness_seconds=int((last_bar - observed).total_seconds()),
        structural_chain_valid=True,
    )
