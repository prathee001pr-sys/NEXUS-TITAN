"""Stage 160: independent, fail-closed batch gate; research only."""
from __future__ import annotations
from dataclasses import dataclass
from .stage159_backtest_readiness import ReadinessReceipt

@dataclass(frozen=True)
class BatchGateReceipt:
    accepted_for_research: bool
    reasons: tuple[str, ...]

def evaluate_batch(*, readiness: ReadinessReceipt, contract_valid: bool,
                   source_license_confirmed: bool, live_trading_requested: bool = False) -> BatchGateReceipt:
    reasons = []
    if not isinstance(readiness, ReadinessReceipt) or not readiness.ready: reasons.append('backtest readiness not verified')
    if contract_valid is not True: reasons.append('contract validation not verified')
    if source_license_confirmed is not True: reasons.append('source license not confirmed')
    if live_trading_requested is not False: reasons.append('live trading prohibited')
    return BatchGateReceipt(not reasons, tuple(reasons))
