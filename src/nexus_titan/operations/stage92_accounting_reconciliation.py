"""Stage92: read-only integer-cent accounting reconciliation; no ledger writes."""
from dataclasses import dataclass
from nexus_titan.operations.isolated_atomic_execution_book import Stage83LocalSyntheticLedgerSnapshot

@dataclass(frozen=True)
class Stage92Reconciliation:
    consistent: bool
    discrepancies: tuple[str, ...]
    live_trading_allowed: bool = False

def reconcile_stage92(snapshot: Stage83LocalSyntheticLedgerSnapshot) -> Stage92Reconciliation:
    if not isinstance(snapshot, Stage83LocalSyntheticLedgerSnapshot):
        raise TypeError("Typed synthetic snapshot required")
    issues = []
    if snapshot.local_integrity_verified is not True:
        issues.append("LOCAL_INTEGRITY_UNVERIFIED")
    if snapshot.live_trading_enabled is not False or snapshot.paper_order_authorized is not False or snapshot.broker_orders_transmitted != 0:
        issues.append("UNEXPECTED_EXECUTION_AUTHORITY")
    fields = ("initial_cents", "cash_cents", "reserved_cents", "available_cents", "exit_proceeds_cents", "paid_notional_cents", "paid_fees_cents", "remaining_cost_basis_cents", "realized_net_pnl_cents")
    if any(type(getattr(snapshot, key)) is not int for key in fields):
        issues.append("INVALID_MONEY_TYPE")
    else:
        if snapshot.initial_cents <= 0 or snapshot.cash_cents < 0 or snapshot.reserved_cents < 0 or snapshot.reserved_cents > snapshot.cash_cents:
            issues.append("INVALID_BALANCE")
        if snapshot.available_cents != snapshot.cash_cents - snapshot.reserved_cents:
            issues.append("AVAILABLE_CASH_MISMATCH")
        if snapshot.initial_cents + snapshot.exit_proceeds_cents != snapshot.cash_cents + snapshot.paid_notional_cents + snapshot.paid_fees_cents:
            issues.append("CASH_FLOW_MISMATCH")
        if snapshot.cash_cents + snapshot.remaining_cost_basis_cents != snapshot.initial_cents + snapshot.realized_net_pnl_cents:
            issues.append("EQUITY_COST_BASIS_MISMATCH")
    return Stage92Reconciliation(not issues, tuple(issues))
