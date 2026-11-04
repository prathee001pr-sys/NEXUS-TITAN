"""Stateless public lifecycle for the selected, risk-enforced synthetic account.

One existing Stage55 book is the sole capital/order/journal authority. The
adapter neither creates balances nor issues permits. Nonempty restart is
readable; each new OPEN/FILL still requires current independent test evidence.
"""
from __future__ import annotations

from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskPermit
from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticBookBlocked,
)


class SyntheticFOExecutionGateway:
    def __init__(self, book: Stage55IsolatedSyntheticExecutionBook):
        if not isinstance(book, Stage55IsolatedSyntheticExecutionBook) or book.selected_fo_boundary_sha256 is None:
            raise Stage55SyntheticBookBlocked("Selected mandatory F&O account required")
        self._book = book
        self.snapshot()  # Replay and verify existing journal; no automatic authority.

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
        return self._book.cancel_unfilled(
            order_id=operation.order_id, cancel_id=operation.operation_id,
            evidence_source='LOCAL_SYNTHETIC_TEST_ONLY',
        )
