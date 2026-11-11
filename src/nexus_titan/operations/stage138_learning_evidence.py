from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class LearningEvidence:
    historical_trades: int
    out_of_sample_trades: int
    paper_trades: int
    profit_factor: float
    max_drawdown_pct: float
    data_leakage_detected: bool
    costs_included: bool


@dataclass(frozen=True)
class EvidenceDecision:
    research_eligible: bool
    reasons: tuple[str, ...]
    live_authorized: bool = False


def evaluate_learning_evidence(
    evidence: LearningEvidence,
) -> EvidenceDecision:
    if not isinstance(evidence, LearningEvidence):
        raise TypeError("LearningEvidence required")

    counts = (
        evidence.historical_trades,
        evidence.out_of_sample_trades,
        evidence.paper_trades,
    )

    if any(
        type(count) is not int or count < 0
        for count in counts
    ):
        raise ValueError("Invalid trade count")

    if (
        type(evidence.profit_factor) not in (int, float)
        or not isfinite(evidence.profit_factor)
        or evidence.profit_factor < 0
        or type(evidence.max_drawdown_pct) not in (int, float)
        or not isfinite(evidence.max_drawdown_pct)
        or not 0 <= evidence.max_drawdown_pct <= 100
    ):
        raise ValueError("Invalid performance metrics")

    if (
        type(evidence.data_leakage_detected) is not bool
        or type(evidence.costs_included) is not bool
    ):
        raise ValueError("Invalid evidence flags")

    reasons = []

    if evidence.historical_trades < 100:
        reasons.append("insufficient_historical_trades")

    if evidence.out_of_sample_trades < 30:
        reasons.append("insufficient_out_of_sample_trades")

    if evidence.paper_trades < 30:
        reasons.append("insufficient_paper_trades")

    if evidence.profit_factor < 1.2:
        reasons.append("profit_factor_below_threshold")

    if evidence.max_drawdown_pct > 15:
        reasons.append("drawdown_above_threshold")

    if evidence.data_leakage_detected:
        reasons.append("data_leakage_detected")

    if not evidence.costs_included:
        reasons.append("transaction_costs_missing")

    return EvidenceDecision(
        research_eligible=not reasons,
        reasons=tuple(reasons),
        live_authorized=False,
    )
