from dataclasses import replace

from nexus_titan.research.backtest import BacktestResult
from nexus_titan.research.strategy_lab import StrategyEvidence, compare_strategies


def result(trades=40, ret=5.0, dd=2.0, pf=1.5, sharpe=1.0):
    return BacktestResult(50000, 52500, trades, 25, 15, 62.5, 2500, ret, dd, pf, 62.5,
                          sharpe_ratio=sharpe)


def test_challenger_comparison_is_eligible_but_never_promotes():
    a = StrategyEvidence("champion", result(), "a" * 64, True, True, True)
    b = StrategyEvidence("challenger", result(ret=8), "a" * 64, True, True, True)
    comparison = compare_strategies(a, b)
    assert comparison.eligible and comparison.challenger_outperformed
    assert comparison.promotion_authorized is False


def test_insufficient_evidence_blocks_comparison():
    a = StrategyEvidence("champion", result(10), "a" * 64, True, True, True)
    b = StrategyEvidence("challenger", result(10), "a" * 64, False, False, True)
    comparison = compare_strategies(a, b)
    assert not comparison.eligible
    assert "challenger_insufficient_trades" in comparison.reasons
    assert "challenger_missing_out_of_sample_evidence" in comparison.reasons


def test_unverified_dataset_manifest_blocks_challenger_even_with_matching_hash():
    a = StrategyEvidence("champion", result(), "a" * 64, True, True, True)
    b = StrategyEvidence("challenger", result(ret=8), "a" * 64, True, True, False)
    comparison = compare_strategies(a, b)
    assert not comparison.eligible
    assert "challenger_dataset_manifest_unverified" in comparison.reasons
    assert comparison.promotion_authorized is False


def test_malformed_fingerprint_and_trade_count_mismatch_block_comparison():
    bad = replace(result(), total_trades=41)
    a = StrategyEvidence("champion", result(), "a" * 64, True, True, True)
    b = StrategyEvidence("challenger", bad, "not-a-sha", True, True, True)
    comparison = compare_strategies(a, b)
    assert not comparison.eligible
    assert "challenger_invalid_dataset_fingerprint" in comparison.reasons
    assert "challenger_trade_count_mismatch" in comparison.reasons


def test_non_finite_metric_blocks_comparison():
    bad = replace(result(), return_percent=float("nan"))
    a = StrategyEvidence("champion", result(), "a" * 64, True, True, True)
    b = StrategyEvidence("challenger", bad, "a" * 64, True, True, True)
    comparison = compare_strategies(a, b)
    assert not comparison.eligible
    assert "challenger_non_finite_metrics" in comparison.reasons
