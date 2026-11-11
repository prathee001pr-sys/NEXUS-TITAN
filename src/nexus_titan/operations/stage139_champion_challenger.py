from dataclasses import dataclass
from math import isfinite

from nexus_titan.operations.stage138_learning_evidence import (
    EvidenceDecision,
)


@dataclass(frozen=True)
class StrategyCandidate:
    strategy_id: str
    net_pnl: float
    profit_factor: float
    max_drawdown_pct: float
    expectancy: float


@dataclass(frozen=True)
class ChallengerDecision:
    challenger_better: bool
    promotion_authorized: bool
    reasons: tuple[str, ...]


def compare_strategies(
    champion: StrategyCandidate,
    challenger: StrategyCandidate,
    challenger_evidence: EvidenceDecision,
) -> ChallengerDecision:
    if not isinstance(champion, StrategyCandidate):
        raise TypeError("Champion candidate required")
    if not isinstance(challenger, StrategyCandidate):
        raise TypeError("Challenger candidate required")
    if not isinstance(challenger_evidence, EvidenceDecision):
        raise TypeError("Evidence decision required")

    for candidate in (champion, challenger):
        if (
            not isinstance(candidate.strategy_id, str)
            or not candidate.strategy_id.strip()
        ):
            raise ValueError("Invalid strategy ID")

        for field in (
            "net_pnl",
            "profit_factor",
            "max_drawdown_pct",
            "expectancy",
        ):
            value = getattr(candidate, field)
            if (
                type(value) not in (int, float)
                or not isfinite(value)
            ):
                raise ValueError("Invalid strategy metric")

        if (
            candidate.profit_factor < 0
            or not 0 <= candidate.max_drawdown_pct <= 100
        ):
            raise ValueError("Invalid strategy risk metrics")

    if champion.strategy_id == challenger.strategy_id:
        raise ValueError("Distinct strategies required")

    if (
        type(challenger_evidence.research_eligible) is not bool
        or type(challenger_evidence.live_authorized) is not bool
        or not isinstance(challenger_evidence.reasons, tuple)
        or any(
            not isinstance(reason, str)
            for reason in challenger_evidence.reasons
        )
    ):
        raise ValueError("Invalid evidence decision")

    reasons = []

    if (
        not challenger_evidence.research_eligible
        or challenger_evidence.reasons
    ):
        reasons.append("challenger_evidence_not_eligible")

    if challenger.net_pnl <= champion.net_pnl:
        reasons.append("net_pnl_not_improved")

    if challenger.profit_factor <= champion.profit_factor:
        reasons.append("profit_factor_not_improved")

    if challenger.expectancy <= champion.expectancy:
        reasons.append("expectancy_not_improved")

    if challenger.max_drawdown_pct > champion.max_drawdown_pct:
        reasons.append("drawdown_worsened")

    return ChallengerDecision(
        challenger_better=not reasons,
        promotion_authorized=False,
        reasons=tuple(reasons),
    )
