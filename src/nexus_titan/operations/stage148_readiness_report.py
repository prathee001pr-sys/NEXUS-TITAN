from dataclasses import dataclass

from nexus_titan.operations.stage145_dashboard_status import (
    DashboardResearchStatus,
)


@dataclass(frozen=True)
class ReadinessReport:
    status: str
    research_review_eligible: bool
    outstanding_gaps: tuple[str, ...]
    human_review_required: bool = True
    production_ready: bool = False
    live_authorized: bool = False


REQUIRED_GAPS = (
    "real_market_data_authenticity_unverified",
    "out_of_sample_validation_not_established",
    "realistic_broker_execution_not_verified",
    "independent_security_audit_incomplete",
    "production_operational_readiness_unverified",
)


def generate_readiness_report(
    dashboard: DashboardResearchStatus,
) -> ReadinessReport:
    if not isinstance(dashboard, DashboardResearchStatus):
        raise TypeError("DashboardResearchStatus required")

    if dashboard.market not in ("INDIAN_FO", "CRYPTO"):
        raise ValueError("Unsupported market")

    for field in (
        "research_review_eligible",
        "human_review_required",
        "live_trading_enabled",
        "automatic_promotion_enabled",
    ):
        if type(getattr(dashboard, field)) is not bool:
            raise ValueError("Invalid dashboard flag")

    if (
        dashboard.live_trading_enabled
        or dashboard.automatic_promotion_enabled
        or not dashboard.human_review_required
    ):
        raise ValueError("Unsafe dashboard permissions")

    if (
        not isinstance(dashboard.reasons, tuple)
        or any(type(r) is not str for r in dashboard.reasons)
    ):
        raise ValueError("Invalid dashboard reasons")

    expected_status = (
        "HUMAN_REVIEW"
        if dashboard.research_review_eligible
        else "BLOCKED"
    )

    if dashboard.research_status != expected_status:
        raise ValueError("Inconsistent dashboard status")

    if (
        dashboard.research_review_eligible
        and dashboard.reasons
    ):
        raise ValueError("Unexpected acceptance reasons")

    if (
        not dashboard.research_review_eligible
        and not dashboard.reasons
    ):
        raise ValueError("Missing blocking reasons")

    gaps = list(REQUIRED_GAPS)

    if not dashboard.research_review_eligible:
        gaps.insert(0, "research_validation_blocked")
        gaps.extend(dashboard.reasons)

    return ReadinessReport(
        status="RESEARCH_REVIEW_ONLY"
        if dashboard.research_review_eligible
        else "BLOCKED",
        research_review_eligible=(
            dashboard.research_review_eligible
        ),
        outstanding_gaps=tuple(dict.fromkeys(gaps)),
        human_review_required=True,
        production_ready=False,
        live_authorized=False,
    )
