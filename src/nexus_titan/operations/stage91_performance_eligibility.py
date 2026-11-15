"""Stage91: conservative read-only eligibility for synthetic research reports."""
from dataclasses import dataclass
from nexus_titan.operations.stage90_signed_valuation_history import Stage90ValuationHistoryAudit

@dataclass(frozen=True)
class Stage91Eligibility:
    exploratory_drawdown_allowed: bool
    official_performance_allowed: bool
    live_trading_allowed: bool
    reasons: tuple[str, ...]

def evaluate_stage91(audit: Stage90ValuationHistoryAudit) -> Stage91Eligibility:
    if not isinstance(audit, Stage90ValuationHistoryAudit):
        raise TypeError("Stage90 audited evidence required")
    reasons = []
    if not audit.eligible_for_exploratory_synthetic_drawdown:
        reasons.append("INSUFFICIENT_SYNTHETIC_HISTORY")
    if audit.real_market_evidence_verified is not False or audit.independently_replayed_historical_journal is not False:
        reasons.append("UNSUPPORTED_EVIDENCE_CLAIM")
    if audit.live_trading_enabled is not False or audit.broker_orders_transmitted != 0:
        reasons.append("LIVE_ACTIVITY_FORBIDDEN")
    if audit.profit_factor is not None or audit.expectancy_cents is not None:
        reasons.append("OFFICIAL_METRIC_NOT_AUTHORIZED")
    if audit.eligible_for_exploratory_synthetic_drawdown and audit.exploratory_synthetic_drawdown_percent is None:
        reasons.append("MISSING_EXPLORATORY_METRIC")
    return Stage91Eligibility(not reasons and audit.eligible_for_exploratory_synthetic_drawdown, False, False, tuple(reasons))
