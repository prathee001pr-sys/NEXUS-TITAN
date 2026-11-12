"""Stage 170: evidence gate for offline backtest review, never live authorization."""
from dataclasses import dataclass
from .stage166_backtest_alignment import AlignmentReceipt
from .stage167_execution_fill_bounds import FillReceipt
from .stage168_trade_reconciliation import ReconciliationReceipt
from .stage169_performance_sanity import PerformanceReceipt

@dataclass(frozen=True)
class EvidenceReceipt:
    accepted_for_offline_review: bool
    blockers: tuple[str, ...]

def evaluate_backtest_evidence(*, alignment: AlignmentReceipt, fill: FillReceipt,
                               reconciliation: ReconciliationReceipt, performance: PerformanceReceipt,
                               dataset_verified: bool, live_requested: bool = False) -> EvidenceReceipt:
    checks = {'alignment': isinstance(alignment, AlignmentReceipt) and alignment.accepted,
              'fill': isinstance(fill, FillReceipt) and fill.accepted,
              'reconciliation': isinstance(reconciliation, ReconciliationReceipt) and reconciliation.accepted,
              'performance': isinstance(performance, PerformanceReceipt) and performance.accepted,
              'dataset': dataset_verified is True,
              'live trading prohibited': live_requested is False}
    blockers = tuple(name for name, passed in checks.items() if not passed)
    return EvidenceReceipt(not blockers, blockers)
