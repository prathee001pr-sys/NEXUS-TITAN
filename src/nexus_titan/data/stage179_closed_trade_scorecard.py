"""Stage 179: deterministic realized closed-trade scorecard, offline only.

Does not mark open positions to market or infer execution costs beyond the
validated settlement records passed by its caller.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from .stage173_settlement_ledger import SettlementReceipt
from .stage176_quote_sanity import parse_amount


@dataclass(frozen=True, slots=True)
class ScorecardReceipt:
    accepted: bool
    net_pnl: Decimal | None
    max_drawdown_bps: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    blockers: tuple[str, ...]


def audit_closed_trade_scorecard(
    settlements: tuple[SettlementReceipt, ...], *, opening_equity: str,
    max_drawdown_bps: int, min_trades: int = 1,
) -> ScorecardReceipt:
    """Chronological, net-of-supplied-costs scorecard; include starting equity peak."""
    blockers: list[str] = []
    if type(min_trades) is not int or not 1 <= min_trades <= 5000:
        blockers.append('invalid minimum trade count')
    if type(max_drawdown_bps) is not int or not 0 <= max_drawdown_bps <= 10_000:
        blockers.append('invalid drawdown limit')
    if not isinstance(settlements, tuple) or not 0 < len(settlements) <= 5000:
        return ScorecardReceipt(False, None, None, None, None, ('missing or oversized settlements',) + tuple(blockers))
    if type(min_trades) is int and len(settlements) < min_trades:
        blockers.append('insufficient closed trades')
    try:
        start = parse_amount(opening_equity)
        if start <= 0:
            raise ValueError('nonpositive capital')
    except ValueError:
        return ScorecardReceipt(False, None, None, None, None, ('invalid opening equity',) + tuple(blockers))
    equity = peak = start
    max_dd = Decimal(0)
    gain = loss = pnl = Decimal(0)
    for idx, row in enumerate(settlements):
        if (not isinstance(row, SettlementReceipt) or row.accepted is not True
                or row.blockers or type(row.gross_pnl) is not Decimal
                or not row.gross_pnl.is_finite() or type(row.net_pnl) is not Decimal
                or not row.net_pnl.is_finite() or abs(row.gross_pnl).adjusted() > 26
                or abs(row.net_pnl).adjusted() > 26
                or row.gross_pnl.as_tuple().exponent < -8
                or row.net_pnl.as_tuple().exponent < -8
                or row.net_pnl > row.gross_pnl):
            blockers.append(f'trade {idx}: unverified closed settlement')
            break
        trade_pnl = row.net_pnl
        pnl += trade_pnl
        if trade_pnl > 0:
            gain += trade_pnl
        elif trade_pnl < 0:
            loss -= trade_pnl
        equity += trade_pnl
        if equity <= 0:
            blockers.append(f'trade {idx}: equity depleted')
            break
        if equity > peak:
            peak = equity
        dd = (peak - equity) * Decimal(10_000) / peak
        if dd > max_dd:
            max_dd = dd
    else:
        if type(max_drawdown_bps) is int and max_dd > max_drawdown_bps:
            blockers.append('drawdown limit breached')
        return ScorecardReceipt(not blockers, pnl, max_dd,
                                gain / loss if loss else None,
                                pnl / len(settlements), tuple(blockers))
    return ScorecardReceipt(False, None, None, None, None, tuple(blockers))
