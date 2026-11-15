import pytest

from nexus_titan.operations.stage138_learning_evidence import (
    EvidenceDecision,
)
from nexus_titan.operations.stage139_champion_challenger import (
    StrategyCandidate,
    compare_strategies,
)


def candidate(strategy_id, **overrides):
    values = dict(
        strategy_id=strategy_id,
        net_pnl=1000.0,
        profit_factor=1.4,
        max_drawdown_pct=10.0,
        expectancy=20.0,
    )
    values.update(overrides)
    return StrategyCandidate(**values)


def eligible():
    return EvidenceDecision(
        research_eligible=True,
        reasons=(),
        live_authorized=False,
    )


def test_better_challenger_requires_approval():
    result = compare_strategies(
        candidate("champion"),
        candidate(
            "challenger",
            net_pnl=1500,
            profit_factor=1.7,
            max_drawdown_pct=8,
            expectancy=30,
        ),
        eligible(),
    )
    assert result.challenger_better
    assert result.promotion_authorized is False


def test_worse_drawdown_blocks_challenger():
    result = compare_strategies(
        candidate("champion"),
        candidate(
            "challenger",
            net_pnl=1500,
            profit_factor=1.7,
            max_drawdown_pct=15,
            expectancy=30,
        ),
        eligible(),
    )
    assert not result.challenger_better
    assert "drawdown_worsened" in result.reasons


def test_missing_evidence_blocks_challenger():
    result = compare_strategies(
        candidate("champion"),
        candidate(
            "challenger",
            net_pnl=1500,
            profit_factor=1.7,
            max_drawdown_pct=8,
            expectancy=30,
        ),
        EvidenceDecision(False, ("missing_paper",), False),
    )
    assert not result.challenger_better


def test_same_strategy_rejected():
    with pytest.raises(ValueError):
        compare_strategies(
            candidate("same"),
            candidate("same"),
            eligible(),
        )


def test_invalid_metric_rejected():
    with pytest.raises(ValueError):
        compare_strategies(
            candidate("champion"),
            candidate("challenger", net_pnl=float("nan")),
            eligible(),
        )


def test_invalid_evidence_rejected():
    with pytest.raises(ValueError):
        compare_strategies(
            candidate("champion"),
            candidate("challenger"),
            EvidenceDecision(True, (), "yes"),
        )
