"""Stage 192: equity and closed-trade drawdown audit bound to the Stage 191 ledger.

No mark-to-market or exchange margin inference; numbers are synthetic and net of
only the fees included in earlier receipts.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json

from .stage176_quote_sanity import parse_amount
from .stage191_portfolio_replay_ledger import (
    ClosedReplay, PortfolioReplayLedgerReceipt, audit_portfolio_replay_ledger,
)


@dataclass(frozen=True, slots=True)
class EquityDrawdownReceipt:
    accepted: bool
    ledger_sha256: str
    ending_equity: Decimal | None
    max_drawdown_bps: Decimal | None
    equity_sha256: str
    blockers: tuple[str, ...]


def audit_equity_drawdown(trades: tuple[ClosedReplay, ...], *, ledger: PortfolioReplayLedgerReceipt,
                          opening_equity: str, max_drawdown_bps: int) -> EquityDrawdownReceipt:
    errors: list[str] = []
    verified = audit_portfolio_replay_ledger(trades)
    if (not isinstance(ledger, PortfolioReplayLedgerReceipt) or not verified.accepted
            or verified != ledger):
        errors.append('Stage 191 ledger does not match input trades')
    if type(max_drawdown_bps) is not int or not 0 <= max_drawdown_bps <= 10000:
        errors.append('invalid drawdown budget')
    try:
        start = parse_amount(opening_equity)
        if start <= 0 or start.adjusted() > 20 or start.as_tuple().exponent < -8:
            raise ValueError('invalid opening equity')
    except (ValueError, TypeError, InvalidOperation):
        errors.append('invalid opening equity')
        start = Decimal(0)
    if errors:
        return EquityDrawdownReceipt(False, '', None, None, '', tuple(errors))
    equity = peak = start
    max_dd = Decimal(0)
    canonical = [str(equity)]
    for i, trade in enumerate(trades):
        equity += trade.receipt.net_pnl
        if equity <= 0:
            errors.append(f'trade {i}: equity depleted')
            break
        if equity > peak:
            peak = equity
        dd = (peak - equity) * Decimal(10000) / peak
        max_dd = max(max_dd, dd)
        canonical.append(str(equity))
    if not errors and max_dd > max_drawdown_bps:
        errors.append('drawdown exceeds offline policy')
    if errors:
        return EquityDrawdownReceipt(False, ledger.ledger_sha256, None, max_dd, '', tuple(errors))
    encoded = json.dumps({'ledger': ledger.ledger_sha256, 'opening_equity': str(start),
                          'equity_path': canonical}, sort_keys=True, separators=(',', ':'))
    return EquityDrawdownReceipt(True, ledger.ledger_sha256, equity, max_dd,
                                 hashlib.sha256(encoded.encode('ascii')).hexdigest(), ())
