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


def test_good_candidate_still_requires_human_review():
    report = generate_advisor_report(
        EvidenceDecision(True, (), False),
        ChallengerDecision(True, False, ()),
    )
    assert report.status == "HUMAN_REVIEW"
    assert report.human_review_required
    assert not report.promotion_authorized
    assert not report.live_authorized


def test_missing_evidence_blocks():
    report = generate_advisor_report(
        EvidenceDecision(
            False,
            ("missing_paper_trades",),
            False,
        ),
        ChallengerDecision(False, False, ()),
    )
    assert report.status == "BLOCKED"
    assert "missing_paper_trades" in report.reasons


def test_weak_challenger_research_only():
    report = generate_advisor_report(
        EvidenceDecision(True, (), False),
        ChallengerDecision(
            False,
            False,
            ("drawdown_worsened",),
        ),
    )
    assert report.status == "RESEARCH_ONLY"
    assert not report.promotion_authorized


def test_live_authorization_rejected():
    with pytest.raises(ValueError):
        generate_advisor_report(
            EvidenceDecision(True, (), True),
            ChallengerDecision(True, False, ()),
        )


def test_automatic_promotion_rejected():
    with pytest.raises(ValueError):
        generate_advisor_report(
            EvidenceDecision(True, (), False),
            ChallengerDecision(True, True, ()),
        )


def test_invalid_input_rejected():
    with pytest.raises(TypeError):
        generate_advisor_report(None, None)
