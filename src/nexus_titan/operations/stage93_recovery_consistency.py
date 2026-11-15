"""Stage93: read-only restart/recovery consistency between signed history and ledger."""
from dataclasses import dataclass
from nexus_titan.operations.stage90_signed_valuation_history import Stage90ValuationHistoryAudit
from nexus_titan.operations.isolated_atomic_execution_book import Stage83LocalSyntheticLedgerSnapshot
from nexus_titan.operations.stage92_accounting_reconciliation import reconcile_stage92

@dataclass(frozen=True)
class Stage93RecoveryAudit:
    consistent: bool
    reasons: tuple[str, ...]
    orders_replayed: bool = False
    live_trading_allowed: bool = False

def inspect_stage93_recovery(history: Stage90ValuationHistoryAudit, snapshot: Stage83LocalSyntheticLedgerSnapshot) -> Stage93RecoveryAudit:
    if not isinstance(history, Stage90ValuationHistoryAudit) or not isinstance(snapshot, Stage83LocalSyntheticLedgerSnapshot):
        raise TypeError("Audited history and typed snapshot required")
    reasons = list(reconcile_stage92(snapshot).discrepancies)
    if history.checkpoint_count < 1:
        reasons.append("NO_HISTORY_HEAD")
    if history.account_id != snapshot.account_id or history.ledger_scope_sha256 != snapshot.ledger_scope_sha256:
        reasons.append("ACCOUNT_SCOPE_MISMATCH")
    if history.last_journal_revision != snapshot.journal_revision or history.last_journal_tip != snapshot.journal_tip:
        reasons.append("JOURNAL_HEAD_MISMATCH")
    if history.live_trading_enabled is not False or history.broker_orders_transmitted != 0:
        reasons.append("UNEXPECTED_LIVE_ACTIVITY")
    return Stage93RecoveryAudit(not reasons, tuple(reasons))
