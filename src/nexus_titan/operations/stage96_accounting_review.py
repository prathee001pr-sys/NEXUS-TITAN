"""Stage96: fail-closed, read-only reconciliation of the Stage95 selected F&O book.

The Stage55 journal is the sole accounting authority. This module never opens,
fills, closes or signs a trade. Synthetic marks are *not* verified market prices.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re


class FOAccountingBlocked(ValueError):
    """An inconsistent or unsupported account view cannot be shown as valid."""


def _exact_int(value, *, nonnegative=False):
    if type(value) is not int or (nonnegative and value < 0) or abs(value) > 10**18:
        raise FOAccountingBlocked('Bounded integer-cent accounting required')
    return value


@dataclass(frozen=True, slots=True)
class FOAccountingReview:
    market: str
    currency: str
    account_id: str
    journal_revision: int
    journal_sha256: str
    initial_cents: int
    cash_cents: int
    remaining_cost_basis_cents: int
    realized_gross_pnl_cents: int
    realized_net_pnl_cents: int
    total_paid_execution_fees_cents: int
    unrealized_net_pnl_cents: int | None
    synthetic_equity_cents: int | None
    position_count: int
    closed_position_count: int
    net_pnl_cents: int | None
    profit_factor: float | None = None
    expectancy_cents: float | None = None
    max_drawdown_percent: float | None = None
    statistics_reason: str = 'Independent signed completed-trade series and anchored valuation history not provided'
    market_evidence_verified: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0


def reconcile_fo_snapshot(snapshot, valuation=None) -> FOAccountingReview:
    """Validate the one-journal snapshot and its optional same-head signed mark.

    Caller must obtain snapshot/valuation atomically via the *existing*
    Stage55 synthetic_valued_snapshot when positions are open. A naked market
    quote or separately fetched valuation is never considered authoritative.
    """
    s = snapshot
    for name in ('initial_cents', 'cash_cents', 'remaining_cost_basis_cents',
                 'realized_gross_pnl_cents', 'realized_net_pnl_cents',
                 'paid_fees_cents', 'journal_revision'):
        _exact_int(getattr(s, name), nonnegative=name not in ('realized_gross_pnl_cents', 'realized_net_pnl_cents'))
    if not isinstance(s.account_id, str) or not s.account_id:
        raise FOAccountingBlocked('Missing account identity')
    if not isinstance(s.journal_tip, str) or re.fullmatch(r'[0-9a-f]{64}',s.journal_tip) is None:
        raise FOAccountingBlocked('Missing checked durable journal tip')
    orders = s.orders
    if not isinstance(orders, tuple):
        raise FOAccountingBlocked('Expected immutable verified journal orders')
    if s.cash_cents + s.remaining_cost_basis_cents != s.initial_cents + s.realized_net_pnl_cents:
        raise FOAccountingBlocked('Journal cash/cost/realized conservation failed')
    open_positions = [p for p in orders if p.open_quantity > 0]
    for p in orders:
        for field in ('filled_quantity','open_quantity','remaining_premium_cents',
                      'remaining_entry_fees_cents', 'realized_net_pnl_cents'):
            _exact_int(getattr(p,field),nonnegative=field!='realized_net_pnl_cents')
        if p.open_quantity > p.filled_quantity:
            raise FOAccountingBlocked('Held quantity exceeds filled quantity')
    if sum(p.remaining_premium_cents + p.remaining_entry_fees_cents for p in orders) != s.remaining_cost_basis_cents:
        raise FOAccountingBlocked('Per-position cost basis does not match account')
    closed = sum(bool(p.filled_quantity and not p.open_quantity and not p.open_hold_cents) for p in orders)
    if valuation is None:
        unrealized = 0 if not open_positions else None
        equity = s.cash_cents if not open_positions else None
    else:
        v = valuation
        if (v.account_id != s.account_id or v.journal_revision != s.journal_revision
                or v.journal_sha256 != s.journal_tip or v.market_evidence_verified is not False
                or v.synthetic_only is not True or v.live_trading_enabled is not False):
            raise FOAccountingBlocked('Market provenance or exact journal head mismatch')
        for field in ('unrealized_net_pnl_cents','total_hypothetical_equity_cents',
                      'portfolio_exposure_cents','estimated_exit_cost_cents'):
            _exact_int(getattr(v,field), nonnegative=field in ('portfolio_exposure_cents','estimated_exit_cost_cents'))
        if (v.total_hypothetical_equity_cents != s.cash_cents + v.portfolio_exposure_cents - v.estimated_exit_cost_cents
                or v.total_hypothetical_equity_cents != s.initial_cents + s.realized_net_pnl_cents + v.unrealized_net_pnl_cents
                or v.open_quantity != sum(p.open_quantity for p in open_positions)):
            raise FOAccountingBlocked('Synthetic MTM equity/quantity does not conserve')
        unrealized, equity = v.unrealized_net_pnl_cents, v.total_hypothetical_equity_cents
    return FOAccountingReview(
        'INDIAN_FO','INR',s.account_id,s.journal_revision,s.journal_tip,
        s.initial_cents,s.cash_cents,s.remaining_cost_basis_cents,
        s.realized_gross_pnl_cents,s.realized_net_pnl_cents,s.paid_fees_cents,
        unrealized,equity,len(open_positions),closed,
        s.realized_net_pnl_cents + unrealized if unrealized is not None else None,
    )


def selected_fo_scorecard(pipeline, *, signed_quotes=None) -> dict:
    """An additive view, never a substitute for Stage95's independent gateway.

    Closed/flat reports use the replay-checked snapshot. Open valuations demand
    Stage55's exact-head *atomic* signed-quote snapshot, not two independent
    snapshot() / mark() calls that could race with fills.
    """
    from nexus_titan.operations.fo_closed_trade_pipeline import FOClosedTradePipeline

    if not isinstance(pipeline, FOClosedTradePipeline):
        raise FOAccountingBlocked('Only the selected signed F&O pipeline may supply a view')
    if signed_quotes is None:
        snapshot = pipeline.gateway.snapshot()
        valuation = None
    else:
        snapshot, valuation = pipeline.gateway._book.synthetic_valued_snapshot(signed_quotes)
    result = asdict(reconcile_fo_snapshot(snapshot, valuation))
    result['source'] = 'STAGE55_REPLAY_CHECKED_SYNTHETIC_JOURNAL'
    result['real_market_shadow_validated'] = False
    return result
