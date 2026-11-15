from dataclasses import dataclass

from nexus_titan.operations.stage138_learning_evidence import (
    EvidenceDecision,
)
from nexus_titan.operations.stage139_champion_challenger import (
    ChallengerDecision,
)


@dataclass(frozen=True)
class AdvisorReport:
    status: str
    recommendation: str
    reasons: tuple[str, ...]
    human_review_required: bool = True
    promotion_authorized: bool = False
    live_authorized: bool = False


def generate_advisor_report(
    evidence: EvidenceDecision,
    comparison: ChallengerDecision,
) -> AdvisorReport:
    if not isinstance(evidence, EvidenceDecision):
        raise TypeError("EvidenceDecision required")

    if not isinstance(comparison, ChallengerDecision):
        raise TypeError("ChallengerDecision required")

    if (
        type(evidence.research_eligible) is not bool
        or type(evidence.live_authorized) is not bool
        or not isinstance(evidence.reasons, tuple)
        or any(type(r) is not str for r in evidence.reasons)
        or type(comparison.challenger_better) is not bool
        or type(comparison.promotion_authorized) is not bool
        or not isinstance(comparison.reasons, tuple)
        or any(type(r) is not str for r in comparison.reasons)
    ):
        raise ValueError("Invalid decision fields")

    if evidence.live_authorized:
        raise ValueError("Unexpected live authorization")

    if comparison.promotion_authorized:
        raise ValueError("Unexpected promotion authorization")

    reasons = tuple(dict.fromkeys(
        evidence.reasons + comparison.reasons
    ))

    if not evidence.research_eligible or evidence.reasons:
        return AdvisorReport(
            status="BLOCKED",
            recommendation=(
                "Collect missing validation evidence "
                "before further strategy evaluation."
            ),
            reasons=reasons or ("evidence_not_eligible",),
        )

    if not comparison.challenger_better or comparison.reasons:
        return AdvisorReport(
            status="RESEARCH_ONLY",
            recommendation=(
                "Continue out-of-sample and paper "
                "validation. Do not promote."
            ),
            reasons=reasons or ("challenger_not_better",),
        )

    return AdvisorReport(
        status="HUMAN_REVIEW",
        recommendation=(
            "Candidate qualifies for independent "
            "risk and research review only. "
            "No automatic promotion."
        ),
        reasons=("human_approval_required",),
    )
