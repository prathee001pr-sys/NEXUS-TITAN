"""Stage 176: bounded, read-only quote sanity with trusted clock inputs.

Quote integrity does not establish actual exchange feed provenance or market access.
Prices and tick sizes must be supplied by a verified external source.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re

_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,8})?\Z")


def parse_amount(value: str) -> Decimal:
    """Parse bounded nonnegative fixed-point input; never accept float/bool/NaN."""
    if not isinstance(value, str) or not _AMOUNT.fullmatch(value):
        raise ValueError('invalid bounded decimal string')
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('invalid decimal') from exc
    if not amount.is_finite():
        raise ValueError('non-finite decimal')
    return amount


@dataclass(frozen=True, slots=True)
class QuoteReceipt:
    accepted: bool
    midpoint: Decimal | None
    spread_bps: Decimal | None
    blockers: tuple[str, ...]


def audit_quote(
    *, bid: str, ask: str, tick_size: str,
    quote_at: datetime, decision_at: datetime,
    max_quote_age_ms: int, max_spread_bps: int,
) -> QuoteReceipt:
    """Validate one quote at decision instant; cannot authorize trading."""
    blockers: list[str] = []
    if (type(max_quote_age_ms) is not int or not 0 <= max_quote_age_ms <= 86_400_000
            or type(max_spread_bps) is not int or not 0 <= max_spread_bps <= 10_000):
        blockers.append('invalid limits')
    midpoint = spread = None
    try:
        b, a, tick = (parse_amount(x) for x in (bid, ask, tick_size))
        if b <= 0 or a <= 0 or tick <= 0:
            blockers.append('nonpositive quote or tick')
        elif b > a:
            blockers.append('crossed quote')
        else:
            midpoint = (b + a) / 2
            spread = (a - b) * 10_000 / midpoint
            if b % tick != 0 or a % tick != 0:
                blockers.append('off-tick quote')
            if type(max_spread_bps) is int and spread > max_spread_bps:
                blockers.append('spread exceeds limit')
    except (ValueError, InvalidOperation, ZeroDivisionError):
        blockers.append('invalid quote amounts')
    if (not isinstance(quote_at, datetime) or not isinstance(decision_at, datetime)
            or quote_at.tzinfo is None or decision_at.tzinfo is None
            or quote_at.utcoffset() is None or decision_at.utcoffset() is None):
        blockers.append('aware timestamps required')
    else:
        qt, dt = quote_at.astimezone(timezone.utc), decision_at.astimezone(timezone.utc)
        if qt > dt:
            blockers.append('future quote')
        elif type(max_quote_age_ms) is int and dt - qt > timedelta(milliseconds=max_quote_age_ms):
            blockers.append('stale quote')
    return QuoteReceipt(not blockers, midpoint, spread, tuple(blockers))
