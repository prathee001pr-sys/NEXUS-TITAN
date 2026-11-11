import pytest

from nexus_titan.operations.stage138_learning_evidence import (
    LearningEvidence,
    evaluate_learning_evidence,
)


def valid_evidence(**overrides):
    values = dict(
        historical_trades=200,
        out_of_sample_trades=60,
        paper_trades=50,
        profit_factor=1.5,
        max_drawdown_pct=8.0,
        data_leakage_detected=False,
        costs_included=True,
    )
    values.update(overrides)
    return LearningEvidence(**values)


def test_research_eligible_never_authorizes_live():
    result = evaluate_learning_evidence(valid_evidence())
    assert result.research_eligible
    assert result.live_authorized is False
    assert result.reasons == ()


def test_insufficient_paper_evidence():
    result = evaluate_learning_evidence(
        valid_evidence(paper_trades=0)
    )
    assert not result.research_eligible
    assert "insufficient_paper_trades" in result.reasons


def test_data_leakage_blocks_research():
    result = evaluate_learning_evidence(
        valid_evidence(data_leakage_detected=True)
    )
    assert not result.research_eligible


def test_missing_costs_blocks_research():
    result = evaluate_learning_evidence(
        valid_evidence(costs_included=False)
    )
    assert not result.research_eligible


def test_multiple_failures_reported():
    result = evaluate_learning_evidence(
        valid_evidence(
            historical_trades=0,
            profit_factor=0.5,
            max_drawdown_pct=25,
        )
    )
    assert len(result.reasons) == 3


@pytest.mark.parametrize("overrides", [
    {"historical_trades": -1},
    {"paper_trades": True},
    {"profit_factor": float("nan")},
    {"max_drawdown_pct": 101},
    {"costs_included": 1},
])
def test_invalid_evidence_rejected(overrides):
    with pytest.raises(ValueError):
        evaluate_learning_evidence(
            valid_evidence(**overrides)
        )
