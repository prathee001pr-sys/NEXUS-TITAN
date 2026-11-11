from dataclasses import dataclass

from nexus_titan.operations.stage144_research_acceptance import (
    ResearchAcceptance,
)


@dataclass(frozen=True)
class DashboardResearchStatus:
    market: str
    research_status: str
    research_review_eligible: bool
    human_review_required: bool
    live_trading_enabled: bool
    automatic_promotion_enabled: bool
    reasons: tuple[str, ...]


def build_dashboard_research_status(
    market: str,
    acceptance: ResearchAcceptance,
) -> DashboardResearchStatus:
    if market not in ("INDIAN_FO", "CRYPTO"):
        raise ValueError("Unsupported market")

    if not isinstance(acceptance, ResearchAcceptance):
        raise TypeError("ResearchAcceptance required")

    if (
        type(acceptance.accepted_for_review) is not bool
        or type(acceptance.human_review_required) is not bool
        or type(acceptance.promotion_authorized) is not bool
        or type(acceptance.live_authorized) is not bool
        or not isinstance(acceptance.reasons, tuple)
        or any(type(r) is not str for r in acceptance.reasons)
    ):
        raise ValueError("Invalid research acceptance")

    if acceptance.live_authorized:
        raise ValueError("Live authorization prohibited")

    if acceptance.promotion_authorized:
        raise ValueError("Automatic promotion prohibited")

    if not acceptance.human_review_required:
        raise ValueError("Human review cannot be bypassed")

    expected_status = (
        "HUMAN_REVIEW"
        if acceptance.accepted_for_review
        else "BLOCKED"
    )

    if (
        acceptance.status != expected_status
        or (
            acceptance.accepted_for_review
            and acceptance.reasons
        )
        or (
            not acceptance.accepted_for_review
            and not acceptance.reasons
        )
    ):
        raise ValueError("Inconsistent research acceptance")

    return DashboardResearchStatus(
        market=market,
        research_status=acceptance.status,
        research_review_eligible=acceptance.accepted_for_review,
        human_review_required=True,
        live_trading_enabled=False,
        automatic_promotion_enabled=False,
        reasons=acceptance.reasons,
    )
