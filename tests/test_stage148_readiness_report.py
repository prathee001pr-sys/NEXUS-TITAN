from dataclasses import replace

import pytest

from nexus_titan.operations.stage145_dashboard_status import (
    DashboardResearchStatus,
)
from nexus_titan.operations.stage148_readiness_report import (
    generate_readiness_report,
)


def dashboard(eligible=True):
    return DashboardResearchStatus(
        market="INDIAN_FO",
        research_status=(
            "HUMAN_REVIEW" if eligible else "BLOCKED"
        ),
        research_review_eligible=eligible,
        human_review_required=True,
        live_trading_enabled=False,
        automatic_promotion_enabled=False,
        reasons=() if eligible else ("bad_data",),
    )


def test_research_only_never_production_ready():
    result = generate_readiness_report(dashboard())
    assert result.status == "RESEARCH_REVIEW_ONLY"
    assert not result.production_ready
    assert not result.live_authorized
    assert result.human_review_required


def test_required_gaps_remain_visible():
    result = generate_readiness_report(dashboard())
    assert len(result.outstanding_gaps) >= 5
    assert "independent_security_audit_incomplete" in (
        result.outstanding_gaps
    )


def test_blocked_research_remains_blocked():
    result = generate_readiness_report(dashboard(False))
    assert result.status == "BLOCKED"
    assert "bad_data" in result.outstanding_gaps


def test_live_permission_rejected():
    with pytest.raises(ValueError):
        generate_readiness_report(
            replace(
                dashboard(),
                live_trading_enabled=True,
            )
        )


def test_auto_promotion_rejected():
    with pytest.raises(ValueError):
        generate_readiness_report(
            replace(
                dashboard(),
                automatic_promotion_enabled=True,
            )
        )


def test_inconsistent_status_rejected():
    with pytest.raises(ValueError):
        generate_readiness_report(
            replace(
                dashboard(),
                research_status="BLOCKED",
            )
        )


def test_invalid_input_rejected():
    with pytest.raises(TypeError):
        generate_readiness_report(None)
