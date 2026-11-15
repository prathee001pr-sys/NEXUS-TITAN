from dataclasses import replace

import pytest

from nexus_titan.operations.stage138_learning_evidence import (
    EvidenceDecision,
)
from nexus_titan.operations.stage139_champion_challenger import (
    ChallengerDecision,
)
from nexus_titan.operations.stage140_titan_advisor import (
    generate_advisor_report,
)
from nexus_titan.operations.stage141_historical_integrity import (
    IntegrityReport,
)
from nexus_titan.operations.stage142_backtest_validation import (
    BacktestValidation,
)
from nexus_titan.operations.stage143_shadow_reconciliation import (
    ReconciliationReport,
)
from nexus_titan.operations.stage144_research_acceptance import (
    evaluate_research_acceptance,
)
from nexus_titan.operations.stage145_dashboard_status import (
    build_dashboard_research_status,
)


def valid_reports():
    return (
        IntegrityReport(True, 100, ()),
        BacktestValidation(True, 900, 100, ()),
        ReconciliationReport(True, 1, 1, 10, ()),
    )


def test_forged_live_authorization_rejected():
    h, b, s = valid_reports()
    with pytest.raises(ValueError):
        evaluate_research_acceptance(
            h,
            replace(b, live_authorized=True),
            s,
        )


def test_forged_research_authorization_blocked():
    h, b, s = valid_reports()
    result = evaluate_research_acceptance(
        replace(h, research_authorized=True),
        b,
        s,
    )
    assert not result.accepted_for_review


def test_missing_shadow_evidence_blocked():
    h, b, s = valid_reports()
    result = evaluate_research_acceptance(
        h,
        b,
        replace(s, order_count=0, fill_count=0),
    )
    assert not result.accepted_for_review


def test_fake_dashboard_promotion_rejected():
    h, b, s = valid_reports()
    accepted = evaluate_research_acceptance(h, b, s)
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(
                accepted,
                promotion_authorized=True,
            ),
        )


def test_human_review_bypass_rejected():
    h, b, s = valid_reports()
    accepted = evaluate_research_acceptance(h, b, s)
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(
                accepted,
                human_review_required=False,
            ),
        )


def test_advisor_rejects_auto_promotion():
    with pytest.raises(ValueError):
        generate_advisor_report(
            EvidenceDecision(True, (), False),
            ChallengerDecision(True, True, ()),
        )


def test_advisor_rejects_live_permission():
    with pytest.raises(ValueError):
        generate_advisor_report(
            EvidenceDecision(True, (), True),
            ChallengerDecision(True, False, ()),
        )


def test_dashboard_does_not_expose_execution_controls():
    h, b, s = valid_reports()
    accepted = evaluate_research_acceptance(h, b, s)
    dashboard = build_dashboard_research_status(
        "INDIAN_FO", accepted
    )
    assert dashboard.live_trading_enabled is False
    assert dashboard.automatic_promotion_enabled is False


def test_blocked_research_cannot_become_ready():
    h, b, s = valid_reports()
    blocked = evaluate_research_acceptance(
        replace(
            h,
            accepted=False,
            reasons=("untrusted_source",),
        ),
        b,
        s,
    )
    dashboard = build_dashboard_research_status(
        "INDIAN_FO", blocked
    )
    assert dashboard.research_status == "BLOCKED"


def test_inconsistent_acceptance_rejected():
    h, b, s = valid_reports()
    accepted = evaluate_research_acceptance(h, b, s)
    with pytest.raises(ValueError):
        build_dashboard_research_status(
            "INDIAN_FO",
            replace(
                accepted,
                status="BLOCKED",
            ),
        )
