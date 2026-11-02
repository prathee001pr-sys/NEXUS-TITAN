"""Evidence-gated champion/challenger comparison; never promotes strategies.

A better score is not proof of an edge. Comparisons require independently
verified dataset provenance, matching data, out-of-sample results, realistic
costs and a minimum trade sample. Promotion remains a separate human-governed
process and is never authorized here.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from nexus_titan.research.backtest import BacktestResult

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class StrategyEvidence:
    name: str
    result: BacktestResult
    dataset_fingerprint: str
    out_of_sample: bool
    costs_included: bool
    dataset_manifest_verified: bool = False


@dataclass(frozen=True)
class StrategyComparison:
    champion: str
    challenger: str
    eligible: bool
    challenger_outperformed: bool
    score_delta: float
    reasons: tuple[str, ...]
    promotion_authorized: bool = False


def _finite_result(result: BacktestResult) -> bool:
    numeric = (
        result.starting_capital, result.ending_capital, result.win_rate_percent,
        result.net_profit, result.return_percent, result.max_drawdown_percent,
        result.expectancy, result.total_fees, result.total_turnover,
        result.average_exposure_percent, result.fill_ratio_percent,
    )
    optional = (result.profit_factor, result.sharpe_ratio, result.sortino_ratio, result.calmar_ratio)
    return all(not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)
               for v in numeric) and all(
        v is None or (not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v))
        for v in optional
    )


def _score(result: BacktestResult) -> float:
    """Conservative transparent score; capped PF and drawdown penalty."""
    pf = result.profit_factor if result.profit_factor is not None else 0.0
    sharpe = result.sharpe_ratio if result.sharpe_ratio is not None else 0.0
    return (result.return_percent + min(pf, 5.0) * 2.0 + sharpe * 2.0
            - result.max_drawdown_percent)


def compare_strategies(champion: StrategyEvidence, challenger: StrategyEvidence,
                       *, minimum_trades: int = 30) -> StrategyComparison:
    if isinstance(minimum_trades, bool) or not isinstance(minimum_trades, int) or minimum_trades < 1:
        raise ValueError("minimum_trades must be a positive integer")
    if champion.name == challenger.name:
        raise ValueError("champion and challenger must have different names")
    reasons: list[str] = []
    for label, evidence in (("champion", champion), ("challenger", challenger)):
        result = evidence.result
        if result.total_trades < minimum_trades:
            reasons.append(f"{label}_insufficient_trades")
        if not _SHA256.fullmatch(evidence.dataset_fingerprint or ""):
            reasons.append(f"{label}_invalid_dataset_fingerprint")
        if not evidence.dataset_manifest_verified:
            reasons.append(f"{label}_dataset_manifest_unverified")
        if not evidence.out_of_sample:
            reasons.append(f"{label}_missing_out_of_sample_evidence")
        if not evidence.costs_included:
            reasons.append(f"{label}_costs_not_included")
        if not _finite_result(result):
            reasons.append(f"{label}_non_finite_metrics")
        elif result.starting_capital <= 0 or result.ending_capital < 0 or result.max_drawdown_percent < 0:
            reasons.append(f"{label}_invalid_performance_metrics")
        if (result.winning_trades + result.losing_trades + result.breakeven_trades
                != result.total_trades):
            reasons.append(f"{label}_trade_count_mismatch")
    if champion.dataset_fingerprint != challenger.dataset_fingerprint:
        reasons.append("dataset_fingerprint_mismatch")
    eligible = not reasons
    delta = round(_score(challenger.result) - _score(champion.result), 4) if (
        _finite_result(champion.result) and _finite_result(challenger.result)
    ) else 0.0
    return StrategyComparison(champion.name, challenger.name, eligible,
                               bool(eligible and delta > 0), delta, tuple(reasons), False)
