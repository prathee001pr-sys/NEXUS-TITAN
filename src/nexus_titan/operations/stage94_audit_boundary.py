"""Stage94: combined fail-closed read-only audit boundary; no authority promotion."""
from dataclasses import dataclass
from nexus_titan.operations.stage90_signed_valuation_history import Stage90ValuationHistoryAudit
from nexus_titan.operations.isolated_atomic_execution_book import Stage83LocalSyntheticLedgerSnapshot
from nexus_titan.operations.stage91_performance_eligibility import evaluate_stage91
from nexus_titan.operations.stage93_recovery_consistency import inspect_stage93_recovery

@dataclass(frozen=True)
class Stage94BoundaryVerdict:
    synthetic_research_readable: bool
    official_performance_allowed: bool
    broker_execution_allowed: bool
    reasons: tuple[str, ...]

def inspect_stage94_boundary(history: Stage90ValuationHistoryAudit, snapshot: Stage83LocalSyntheticLedgerSnapshot) -> Stage94BoundaryVerdict:
    performance = evaluate_stage91(history)
    recovery = inspect_stage93_recovery(history, snapshot)
    reasons = performance.reasons + recovery.reasons
    if history.real_market_evidence_verified is not False or history.independently_replayed_historical_journal is not False:
        reasons += ("UNVERIFIED_EXTERNAL_PROVENANCE",)
    return Stage94BoundaryVerdict(not reasons, False, False, reasons)
