"""Stateless public lifecycle for the selected, risk-enforced synthetic account.

One existing Stage55 book is the sole capital/order/journal authority. The
adapter neither creates balances nor issues permits. Nonempty restart is
readable; each new OPEN/FILL still requires current independent test evidence.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexus_titan.intelligence.pipeline import PipelineStatus

from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskPermit
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticBookBlocked,
)
from nexus_titan.operations.synthetic_fo_research import SyntheticFOAssessment
from nexus_titan.operations.synthetic_option_positions import SyntheticCloseRequest, SyntheticCloseAuthorization


@dataclass(frozen=True, slots=True)
class SyntheticFOPerformanceReport:
    account_id: str
    journal_revision: int
    journal_sha256: str
    initial_cents: int
    cash_cents: int
    reserved_cents: int
    available_cents: int
    paid_premium_cents: int
    execution_fees_cents: int
    gross_committed_cents: int
    filled_units: int
    net_pnl_cents: int | None = None
    profit_factor: float | None = None
    expectancy_cents: float | None = None
    max_drawdown_percent: float | None = None
    unavailable_reason: str = 'No selected-account exits, realized P&L or independently marked equity curve'
    real_market_evidence_verified: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = 'SYNTHETIC_ACCOUNTING_ONLY_REAL_FO_SHADOW_NO_GO'
    gross_realized_pnl_cents: int = 0
    realized_net_pnl_cents: int = 0
    open_unrealized_pnl_cents: int | None = None
    current_synthetic_equity_cents: int | None = None
    closed_trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    remaining_cost_basis_cents: int = 0


class SyntheticFOExecutionGateway:
    def __init__(self, book: Stage55IsolatedSyntheticExecutionBook):
        if not isinstance(book, Stage55IsolatedSyntheticExecutionBook) or book.selected_fo_boundary_sha256 is None:
            raise Stage55SyntheticBookBlocked("Selected mandatory F&O account required")
        self._book = book
        self.snapshot()  # Replay and verify existing journal; no automatic authority.

    @property
    def boundary_sha256(self):
        return self._book.selected_fo_boundary_sha256

    def snapshot(self):
        return self._book.snapshot_local_synthetic_portfolio()

    def apply(self, operation: SyntheticFOOperation, *, risk_permit: SyntheticFORiskPermit | None = None):
        if not isinstance(operation, SyntheticFOOperation):
            raise Stage55SyntheticBookBlocked("Typed synthetic lifecycle operation required")
        if operation.kind == 'OPEN':
            return self._book.reserve_synthetic_buy(
                request_id=operation.operation_id, symbol=operation.symbol,
                quantity=operation.quantity, limit_price_cents=operation.price_cents,
                fee_buffer_cents=operation.fee_buffer_cents, risk_permit=risk_permit,
            )
        if operation.kind == 'FILL':
            return self._book.record_simulated_fill(
                order_id=operation.order_id, fill_id=operation.operation_id,
                quantity=operation.quantity, price_cents=operation.price_cents,
                fee_cents=operation.fee_cents, risk_permit=risk_permit,
                evidence_source='LOCAL_SYNTHETIC_TEST_ONLY',
            )
        if operation.kind != 'CANCEL':
            raise Stage55SyntheticBookBlocked('Unknown lifecycle operation; SELL requires explicit close authorization')
        return self._book.cancel_unfilled(
            order_id=operation.order_id, cancel_id=operation.operation_id,
            evidence_source='LOCAL_SYNTHETIC_TEST_ONLY',
        )

    def close_position(self, request: SyntheticCloseRequest, *, authorization: SyntheticCloseAuthorization):
        return self._book.record_synthetic_close(request,authorization=authorization)

    def mark_to_market(self, quotes):
        return self._book.synthetic_mark_to_market(quotes)

    def apply_assessed_open(self, operation, *, assessment, risk_permit):
        """Connect the actual research assessment to the selected risk path.

        This facade is not a process boundary. The mandatory ledger risk check
        remains authoritative even for callers using the lower-level API.
        """
        if (not isinstance(operation,SyntheticFOOperation) or operation.kind != 'OPEN'
                or not isinstance(assessment,SyntheticFOAssessment)
                or not assessment.state.quality.valid
                or assessment.state.symbol != operation.symbol
                or assessment.pipeline.status != PipelineStatus.SHADOW_CANDIDATE
                or assessment.pipeline.consensus.action != 'BUY'
                or assessment.pipeline.risk_approved is not True
                or assessment.pipeline.risk_quantity < operation.quantity
                or 'UNKNOWN' in (assessment.regime.trend,assessment.regime.volatility)):
            raise Stage55SyntheticBookBlocked('Combined synthetic market/signal/risk assessment denied')
        if self._book.selected_fo_source_contract(operation.symbol) != (
            assessment.source_stage71_sha256,assessment.source_stage72_sha256,
            assessment.stage73_review_sha256,
        ):
            raise Stage55SyntheticBookBlocked('Combined research differs from pinned F&O contract')
        return self.apply(operation,risk_permit=risk_permit)

    def performance_report(self, *, quotes=None) -> SyntheticFOPerformanceReport:
        # One snapshot for the accounting and valuation view, even with concurrent writers.
        if quotes is not None:
            snapshot,valuation=self._book.synthetic_valued_snapshot(quotes)
            return self._performance(snapshot,valuation)
        return self._performance(self.snapshot())

    @staticmethod
    def _performance(s,valuation=None):
        closed=[o for o in s.orders if o.filled_quantity>0 and o.open_quantity==0 and o.open_hold_cents==0]
        has_close=any(o.closed_quantity for o in s.orders)
        flat=not any(o.open_quantity for o in s.orders)
        unrealized=valuation.unrealized_net_pnl_cents if valuation is not None else (0 if flat else None)
        equity=valuation.total_hypothetical_equity_cents if valuation is not None else (s.cash_cents if flat else None)
        return SyntheticFOPerformanceReport(
            s.account_id,s.journal_revision,s.journal_tip,s.initial_cents,s.cash_cents,
            s.reserved_cents,s.available_cents,s.paid_notional_cents,s.paid_fees_cents,
            s.gross_entry_commitment_cents,
            sum(o.filled_quantity for o in s.orders),
            net_pnl_cents=s.realized_net_pnl_cents+unrealized if has_close and unrealized is not None else None,
            gross_realized_pnl_cents=s.realized_gross_pnl_cents,
            realized_net_pnl_cents=s.realized_net_pnl_cents,
            open_unrealized_pnl_cents=unrealized,current_synthetic_equity_cents=equity,
            closed_trade_count=len(closed),win_count=sum(o.realized_net_pnl_cents>0 for o in closed),
            loss_count=sum(o.realized_net_pnl_cents<0 for o in closed),
            breakeven_count=sum(o.realized_net_pnl_cents==0 for o in closed),
            remaining_cost_basis_cents=s.remaining_cost_basis_cents,
            unavailable_reason='Profit factor/expectancy/drawdown require an approved lifecycle and valuation-history protocol; open MTM requires signed quotes',
        )
