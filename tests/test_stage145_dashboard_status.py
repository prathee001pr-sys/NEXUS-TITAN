from dataclasses import replace

import pytest

from nexus_titan.operations.stage144_research_acceptance import (
    ResearchAcceptance,
)
from nexus_titan.operations.stage145_dashboard_status import (
    build_dashboard_research_status,
)


def acceptance(approved=True):
    return ResearchAcceptance(
        accepted_for_review=approved,
        status="HUMAN_REVIEW" if approved else "BLOCKED",
        reasons=() if approved else ("missing_evidence",),
    )


@pytest.mark.parametrize("market", [
    "INDIAN_FO",
    "CRYPTO",
])
def test_review_status_is_read_only(market):
    result = build_dashboard_research_status(
        market, acceptance()
    )
    assert result.research_review_eligible
    assert result.human_review_required
    assert not result.live_trading_enabled
    assert not result.automatic_promotion_enabled


def test_blocked_status():
    result = build_dashboard_research_status(
        "INDIAN_FO", acceptance(False)
    )
    assert result.research_status == "BLOCKED"
    assert not result.research_review_eligible


def test_invalid_market_rejected():
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "UNKNOWN", acceptance()
        )


def test_live_authorization_rejected():
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(acceptance(), live_authorized=True),
        )


def test_promotion_rejected():
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(
                acceptance(),
                promotion_authorized=True,
            ),
        )


def test_inconsistent_status_rejected():
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(
                acceptance(),
                status="BLOCKED",
            ),
        )


def test_human_review_bypass_rejected():
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(
                acceptance(),
                human_review_required=False,
            ),
        )
