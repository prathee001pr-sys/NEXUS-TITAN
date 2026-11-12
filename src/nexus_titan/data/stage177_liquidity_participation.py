"""Stage 177: read-only liquidity participation and quote-relative fill bounds.

Bar volume and fills MUST be in the same verified unit/contract; index volume
and derivatives contract counts cannot be silently mixed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from .stage176_quote_sanity import QuoteReceipt, parse_amount
from .stage167_execution_fill_bounds import FillReceipt


@dataclass(frozen=True, slots=True)
class LiquidityReceipt:
    accepted: bool
    participation_bps: Decimal | None
    blockers: tuple[str, ...]


def audit_liquidity_fill(
    *, side: str, fill_price: str, bid: str, ask: str,
    filled_units: str, observed_bar_units: str,
    max_participation_bps: int, max_quote_slippage_bps: int,
    units_verified: bool, quote: QuoteReceipt, fill: FillReceipt,
) -> LiquidityReceipt:
    """Reject excessively large or implausible simulated fills.

    Uses the supplied bid/ask and observed bar units; cannot verify an exchange
    order-book, actual market impact, matching engine, or real executions.
    """
    blockers: list[str] = []
    if side not in ('BUY', 'SELL'):
        blockers.append('invalid side')
    if (type(max_participation_bps) is not int or not 1 <= max_participation_bps <= 10_000
            or type(max_quote_slippage_bps) is not int or not 0 <= max_quote_slippage_bps <= 10_000):
        blockers.append('invalid limits')
    if units_verified is not True:
        blockers.append('unverified comparable units')
    if not isinstance(quote, QuoteReceipt) or quote.accepted is not True or quote.blockers:
        blockers.append('quote audit required')
    if not isinstance(fill, FillReceipt) or fill.accepted is not True or fill.errors:
        blockers.append('fill audit required')
    participation = None
    try:
        price, b, a, units, volume = (parse_amount(x) for x in (
            fill_price, bid, ask, filled_units, observed_bar_units))
        if min(price, b, a, units, volume) <= 0 or b > a:
            blockers.append('invalid price or volume')
        else:
            if (isinstance(quote, QuoteReceipt) and quote.accepted is True
                    and (quote.midpoint != (a + b) / 2
                         or quote.spread_bps != (a - b) * 10_000 / ((a + b) / 2))):
                blockers.append('quote values differ from validated quote')
            participation = units * Decimal(10_000) / volume
            if type(max_participation_bps) is int and participation > max_participation_bps:
                blockers.append('excessive market participation')
            if type(max_quote_slippage_bps) is int:
                tolerance = Decimal(max_quote_slippage_bps) / 10_000
                if side == 'BUY' and (price < b or price > a * (1 + tolerance)):
                    blockers.append('fill outside quote tolerance')
                if side == 'SELL' and (price > a or price < b * (1 - tolerance)):
                    blockers.append('fill outside quote tolerance')
    except (ValueError, InvalidOperation, ZeroDivisionError):
        blockers.append('invalid decimal inputs')
    return LiquidityReceipt(not blockers, participation, tuple(blockers))
