"""Stage125: strict offline NSE website-style option-chain CSV snapshot parser.

Unverified source, missing observation timestamp and contract metadata imply NO-GO.
This is NOT a historical market data feed or a strategy/backtest adapter.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import csv
import io
import re


class Stage125Blocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Stage125Quote:
    strike_paise: int
    side: str
    bid_paise: int | None
    ask_paise: int | None
    ltp_paise: int | None
    open_interest: int | None
    volume: int | None
    quote_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stage125Snapshot:
    underlying: str
    expiry_date: str
    raw_sha256: str
    strike_count: int
    quotes: tuple[Stage125Quote, ...]
    observed_at_ist: None = None
    provider_authenticated: bool = False
    contract_master_verified: bool = False
    licensed_for_trading: bool = False
    live_trading_enabled: bool = False
    verdict: str = "UNVERIFIED_UNTIMESTAMPED_SNAPSHOT_NO_GO"


_HEADER = ("NO TEXT", "OI", "CHNG IN OI", "VOLUME", "IV", "LTP", "CHNG", "BID QTY", "BID", "ASK", "ASK QTY", "STRIKE", "BID QTY", "BID", "ASK", "ASK QTY", "CHNG", "LTP", "IV", "VOLUME", "CHNG IN OI", "OI", "NO TEXT")
_DATE = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}\Z")


def _num(cell: str, *, money: bool, allow_missing: bool = True) -> int | None:
    if cell.strip() in ("", "-"):
        if allow_missing:
            return None
        raise Stage125Blocked("Required numeric field missing")
    cleaned = cell.strip().replace(",", "")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", cleaned):
        raise Stage125Blocked("Invalid or negative numeric cell")
    try:
        value = Decimal(cleaned) * (100 if money else 1)
    except InvalidOperation as exc:
        raise Stage125Blocked("Invalid numeric cell") from exc
    if value != value.to_integral_value() or value > 10**13:
        raise Stage125Blocked("Numeric cell out of range")
    return int(value)


def inspect_stage125_snapshot(raw: bytes, *, underlying: str, expiry_date: str) -> Stage125Snapshot:
    if type(raw) is not bytes or not 40 <= len(raw) <= 4_000_000:
        raise Stage125Blocked("Bounded CSV bytes required")
    if underlying not in ("NIFTY", "BANKNIFTY") or type(expiry_date) is not str or not _DATE.fullmatch(expiry_date):
        raise Stage125Blocked("Explicit supported underlying and ISO expiry required")
    from datetime import date
    try:
        date.fromisoformat(expiry_date)
    except ValueError as exc:
        raise Stage125Blocked("Invalid expiry date") from exc
    try:
        data = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Stage125Blocked("UTF-8 only") from exc
    if "\x00" in data:
        raise Stage125Blocked("Binary data rejected")
    try:
        reader = csv.reader(io.StringIO(data, newline=""), strict=True)
        if tuple(next(reader)) != ("CALLS", "NO TEXT", "PUTS"):
            raise Stage125Blocked("Unexpected top-level NSE export header")
        if tuple(next(reader)) != _HEADER:
            raise Stage125Blocked("Unexpected 23-column NSE export header")
        quotes = []
        strikes = set()
        for idx, row in enumerate(reader, start=3):
            if idx > 10004 or len(row) != 23:
                raise Stage125Blocked("Malformed or oversized option chain")
            strike = _num(row[11], money=True, allow_missing=False)
            if strike in strikes or strike <= 0:
                raise Stage125Blocked("Duplicate or invalid strike")
            strikes.add(strike)
            for side, b, a, l, oi, vol in (("CE",8,9,5,1,3),("PE",13,14,17,21,19)):
                bid,ask,ltp = (_num(row[k],money=True) for k in (b,a,l))
                open_interest,volume = (_num(row[k],money=False) for k in (oi,vol))
                flags = []
                if bid is None or ask is None:
                    flags.append("MISSING_BID_OR_ASK")
                elif bid > ask:
                    flags.append("CROSSED_MARKET")
                if ltp is not None and bid is not None and ask is not None and not bid <= ltp <= ask:
                    flags.append("LTP_OUTSIDE_BID_ASK_NOT_SYNCHRONIZED")
                if open_interest is None:
                    flags.append("MISSING_OI")
                quotes.append(Stage125Quote(strike,side,bid,ask,ltp,open_interest,volume,tuple(flags)))
    except (csv.Error, StopIteration) as exc:
        raise Stage125Blocked("Invalid CSV structure") from exc
    if not strikes:
        raise Stage125Blocked("Empty chain")
    return Stage125Snapshot(underlying,expiry_date,sha256(raw).hexdigest(),len(strikes),tuple(quotes))
