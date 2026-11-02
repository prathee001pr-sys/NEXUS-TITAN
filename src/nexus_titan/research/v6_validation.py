"""Multi-fold rolling walk-forward validation with warm-up context, block-bootstrap Monte Carlo, and multiple-testing correction."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal

from nexus_titan.research.backtest import BacktestResult, InstrumentType, run_backtest


class PromotionStage(str, Enum):
    """Strategy lifecycle governance states required by Blueprint Section 7.6 & NT-P1-11."""
    DRAFT = "DRAFT"
    BACKTEST_VALIDATED = "BACKTEST_VALIDATED"
    OOS_VALIDATED = "OOS_VALIDATED"
    STRESS_VALIDATED = "STRESS_VALIDATED"
    PAPER_SHADOW_VALIDATED = "PAPER_SHADOW_VALIDATED"
    APPROVED_FOR_NEXT_STAGE = "APPROVED_FOR_NEXT_STAGE"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class WalkForwardFoldResult:
    fold_number: int
    train_bars: int
    test_bars: int
    warmup_bars_used: int
    in_sample_return_pct: float
    out_of_sample_return_pct: float
    out_of_sample_trades: int
    out_of_sample_sharpe: float | None
    is_profitable_oos: bool


@dataclass(frozen=True)
class WalkForwardReport:
    """Report comparing multi-fold rolling out-of-sample performance."""
    total_folds: int
    folds: list[WalkForwardFoldResult]
    aggregate_oos_return_pct: float
    compounded_oos_return_pct: float
    total_oos_trades: int
    confidence_verdict: str  # ROBUST_CANDIDATE, MIXED, OVERFITTED, INSUFFICIENT_EVIDENCE
    status_summary: str
    window_mode: str = "anchored"

    @property
    def train_candles(self) -> int:
        return self.folds[0].train_bars if self.folds else 0

    @property
    def test_candles(self) -> int:
        return self.folds[0].test_bars if self.folds else 0

    @property
    def in_sample_return_pct(self) -> float:
        return self.folds[0].in_sample_return_pct if self.folds else 0.0

    @property
    def out_of_sample_return_pct(self) -> float:
        return self.compounded_oos_return_pct

    @property
    def is_overfitted(self) -> bool:
        return self.confidence_verdict == "OVERFITTED"


@dataclass(frozen=True)
class MonteCarloReport:
    """Monte Carlo output with an explicit warning for thin trade samples.

    The simulated percentiles are exploratory when sample_adequate is false;
    they must not be interpreted as a reliable tail-risk estimate.
    """
    iterations: int
    method: str  # "block_bootstrap" or "trade_shuffle"
    block_size: int
    original_max_drawdown_pct: float
    median_max_drawdown_pct: float
    percentile_95_max_drawdown_pct: float
    worst_case_drawdown_pct: float
    ruin_probability_pct: float
    sample_size: int = 0
    sample_adequate: bool = False
    warning: str | None = None
    drawdown_scope: str = "CLOSED_TRADE_PNL_ONLY; intratrade and unrealized exposure are excluded."


@dataclass(frozen=True)
class MultipleComparisonReport:
    """Deflated Sharpe Ratio & Bonferroni/Holm adjustment against data snooping (Workstream W)."""
    observed_sharpe: float
    num_trials: int
    sample_length: int
    expected_max_sharpe_null: float
    deflated_sharpe_probability: float
    passes_multiple_testing_gate: bool
    summary: str


@dataclass(frozen=True)
class StrategyPromotionDecision:
    """Governance decision evaluating whether a strategy can advance to the next stage (NT-P1-11)."""
    strategy_name: str
    current_stage: PromotionStage
    recommended_stage: PromotionStage
    promoted: bool
    reasons: tuple[str, ...]


def _compute_fold_boundaries(
    n: int, num_folds: int, initial_train_ratio: float = 0.50, window_mode: Literal["anchored", "sliding"] = "anchored"
) -> list[tuple[int, int, int]]:
    """Return list of (train_start, train_end, test_end) indices for arbitrary num_folds >= 1."""
    if num_folds == 3 and abs(initial_train_ratio - 0.50) < 1e-6 and window_mode == "anchored":
        # Preserve exact legacy 3-fold percentages (0.50->0.70, 0.70->0.85, 0.85->1.00)
        return [
            (0, int(n * 0.50), int(n * 0.70)),
            (0, int(n * 0.70), int(n * 0.85)),
            (0, int(n * 0.85), n),
        ]
    if num_folds == 1:
        split = int(n * 0.70)
        return [(0, split, n)]
    train_base = int(n * initial_train_ratio)
    remaining = n - train_base
    step = max(2, remaining // num_folds)
    boundaries: list[tuple[int, int, int]] = []
    for k in range(num_folds):
        train_end = train_base + k * step
        test_end = n if k == num_folds - 1 else min(n, train_end + step)
        train_start = 0 if window_mode == "anchored" else max(0, train_end - train_base)
        if test_end - train_end >= 2 and train_end - train_start >= 2:
            boundaries.append((train_start, train_end, test_end))
    return boundaries


def rolling_walk_forward_validation(
    candles: list[dict[str, float]],
    signal_factory: Callable[[list[dict[str, float]]], Callable[[int, list[dict[str, float]]], int]],
    num_folds: int = 3,
    min_trades_gate: int = 5,
    warmup_lookback: int = 25,
    starting_capital: float = 100000.0,
    fee_per_side: float = 20.0,
    slippage_per_side: float = 2.0,
    use_indian_statutory_costs: bool = False,
    instrument_type: InstrumentType = "EQUITY_DELIVERY",
    sizing_mode: Literal["fixed", "capital_risk"] = "fixed",
    risk_per_trade_pct: float = 1.0,
    stop_loss_pct: float | None = None,
    target_pct: float | None = None,
    instrument_lot_size: int = 1,
    window_mode: Literal["anchored", "sliding"] = "anchored",
    initial_train_ratio: float = 0.50,
) -> tuple[list[BacktestResult], WalkForwardReport]:
    """Perform multi-fold rolling chronological train/test validation with warm-up history (NT-P1-02, NT-P1-03, NT-P1-04)."""
    n = len(candles)
    if n < 30:
        raise ValueError("At least 30 candles are required for rolling walk-forward validation.")
    if isinstance(num_folds, bool) or not isinstance(num_folds, int) or num_folds < 1:
        raise ValueError("num_folds must be a positive integer.")
    if window_mode not in ("anchored", "sliding"):
        raise ValueError("window_mode must be 'anchored' or 'sliding'.")

    folds: list[WalkForwardFoldResult] = []
    oos_results: list[BacktestResult] = []
    fold_bounds = _compute_fold_boundaries(n, num_folds, initial_train_ratio, window_mode)

    compounded_multiplier = 1.0

    for idx, (train_start, train_end, test_end) in enumerate(fold_bounds, start=1):
        train_data = candles[train_start:train_end]

        # Carry indicator warm-up history from prior bars into OOS without trading on warm-up bars (NT-P1-04)
        warmup_start = max(0, train_end - warmup_lookback)
        actual_warmup_bars = train_end - warmup_start
        test_data_with_warmup = candles[warmup_start:test_end]

        train_sig = signal_factory(train_data)
        train_res = run_backtest(
            train_data,
            starting_capital=starting_capital,
            fee_per_side=fee_per_side,
            slippage_per_side=slippage_per_side,
            signal=train_sig,
            stop_loss_pct=stop_loss_pct,
            target_pct=target_pct,
            use_indian_statutory_costs=use_indian_statutory_costs,
            instrument_type=instrument_type,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            instrument_lot_size=instrument_lot_size,
        )

        test_sig = signal_factory(test_data_with_warmup)
        test_res = run_backtest(
            test_data_with_warmup,
            starting_capital=starting_capital,
            fee_per_side=fee_per_side,
            slippage_per_side=slippage_per_side,
            signal=test_sig,
            warmup_bars=actual_warmup_bars,
            stop_loss_pct=stop_loss_pct,
            target_pct=target_pct,
            use_indian_statutory_costs=use_indian_statutory_costs,
            instrument_type=instrument_type,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            instrument_lot_size=instrument_lot_size,
        )
        oos_results.append(test_res)

        compounded_multiplier *= (1.0 + test_res.return_percent / 100.0)

        folds.append(
            WalkForwardFoldResult(
                fold_number=idx,
                train_bars=len(train_data),
                test_bars=test_end - train_end,
                warmup_bars_used=actual_warmup_bars,
                in_sample_return_pct=round(train_res.return_percent, 2),
                out_of_sample_return_pct=round(test_res.return_percent, 2),
                out_of_sample_trades=test_res.total_trades,
                out_of_sample_sharpe=test_res.sharpe_ratio,
                is_profitable_oos=test_res.return_percent > 0,
            )
        )

    total_oos_trades = sum(f.out_of_sample_trades for f in folds)
    avg_oos_return = sum(f.out_of_sample_return_pct for f in folds) / len(folds)
    compounded_return = (compounded_multiplier - 1.0) * 100.0

    # Strict Sample-Size & Multi-Fold Stability Gate (NT-P1-03: Never call small samples ROBUST)
    if total_oos_trades < min_trades_gate:
        verdict = "INSUFFICIENT_EVIDENCE"
        summary = (
            f"Sample size gate failed: Only {total_oos_trades} out-of-sample trades across {len(folds)} folds "
            f"(minimum {min_trades_gate} required). Never promote thin samples."
        )
    elif all(f.is_profitable_oos for f in folds) and len(folds) >= 2:
        verdict = "ROBUST_CANDIDATE"
        summary = f"All {len(folds)} out-of-sample folds passed with {total_oos_trades} total trades."
    elif compounded_return < -1.0:
        verdict = "OVERFITTED"
        summary = "Warning: Out-of-sample degradation indicates in-sample curve fitting."
    else:
        verdict = "MIXED"
        summary = "Strategy showed mixed out-of-sample regime stability across folds."

    report = WalkForwardReport(
        total_folds=len(folds),
        folds=folds,
        aggregate_oos_return_pct=round(avg_oos_return, 2),
        compounded_oos_return_pct=round(compounded_return, 2),
        total_oos_trades=total_oos_trades,
        confidence_verdict=verdict,
        status_summary=summary,
        window_mode=window_mode,
    )

    return oos_results, report


def walk_forward_validation(
    candles: list[dict[str, float]],
    signal_factory: Callable[[list[dict[str, float]]], Callable[[int, list[dict[str, float]]], int]],
    train_ratio: float = 0.7,
    min_trades_gate: int = 5,
    starting_capital: float = 100000.0,
    fee_per_side: float = 20.0,
    slippage_per_side: float = 2.0,
    use_indian_statutory_costs: bool = False,
    instrument_type: InstrumentType = "EQUITY_DELIVERY",
) -> tuple[BacktestResult, BacktestResult, WalkForwardReport]:
    """Single chronological train/test split with strict minimum sample-size gate (NT-P1-03)."""
    split_idx = int(len(candles) * train_ratio)
    train_data = candles[:split_idx]
    test_data = candles[split_idx:]

    train_sig = signal_factory(train_data)
    train_res = run_backtest(
        train_data,
        starting_capital=starting_capital,
        fee_per_side=fee_per_side,
        slippage_per_side=slippage_per_side,
        signal=train_sig,
        use_indian_statutory_costs=use_indian_statutory_costs,
        instrument_type=instrument_type,
    )

    test_sig = signal_factory(test_data)
    test_res = run_backtest(
        test_data,
        starting_capital=starting_capital,
        fee_per_side=fee_per_side,
        slippage_per_side=slippage_per_side,
        signal=test_sig,
        use_indian_statutory_costs=use_indian_statutory_costs,
        instrument_type=instrument_type,
    )

    fold = WalkForwardFoldResult(
        fold_number=1,
        train_bars=len(train_data),
        test_bars=len(test_data),
        warmup_bars_used=0,
        in_sample_return_pct=round(train_res.return_percent, 2),
        out_of_sample_return_pct=round(test_res.return_percent, 2),
        out_of_sample_trades=test_res.total_trades,
        out_of_sample_sharpe=test_res.sharpe_ratio,
        is_profitable_oos=test_res.return_percent > 0,
    )

    if test_res.total_trades < min_trades_gate:
        verdict = "INSUFFICIENT_EVIDENCE"
        summary = f"Insufficient OOS trades ({test_res.total_trades} < {min_trades_gate}). Cannot certify robust."
    elif test_res.return_percent > 0:
        verdict = "ROBUST_CANDIDATE"
        summary = "Single split passed minimum trade gate."
    else:
        verdict = "OVERFITTED"
        summary = "Negative out-of-sample return."

    report = WalkForwardReport(
        total_folds=1,
        folds=[fold],
        aggregate_oos_return_pct=round(test_res.return_percent, 2),
        compounded_oos_return_pct=round(test_res.return_percent, 2),
        total_oos_trades=test_res.total_trades,
        confidence_verdict=verdict,
        status_summary=summary,
    )

    return train_res, test_res, report


def run_monte_carlo_simulation(
    trade_pnls: list[float],
    starting_capital: float = 100000.0,
    iterations: int = 1000,
    seed: int = 42,
    method: str = "block_bootstrap",
    block_size: int = 3,
    minimum_sample_size: int = 30,
) -> MonteCarloReport:
    """Run an exploratory trade-P&L resampling stress test.

    A minimum of 30 closed trades is an operational floor, not a guarantee of
    statistical power. Thin samples still produce descriptive resampling
    figures for diagnostics, but are explicitly marked inadequate and cannot
    satisfy strategy-promotion gates.
    """
    if isinstance(starting_capital, bool) or not isinstance(starting_capital, (int, float)) or not math.isfinite(starting_capital) or starting_capital <= 0:
        raise ValueError("starting_capital must be a finite positive number.")
    for name, value in (("iterations", iterations), ("block_size", block_size), ("minimum_sample_size", minimum_sample_size)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")
    if method not in ("block_bootstrap", "trade_shuffle"):
        raise ValueError("method must be 'block_bootstrap' or 'trade_shuffle'.")
    if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) for p in trade_pnls):
        raise ValueError("trade_pnls must contain only finite numeric values.")

    n = len(trade_pnls)
    sample_adequate = n >= minimum_sample_size
    warning = None if sample_adequate else (
        f"INSUFFICIENT_SAMPLE: {n} closed trades; at least {minimum_sample_size} required "
        "for this operational Monte Carlo gate. Results are exploratory only."
    )
    if not trade_pnls:
        return MonteCarloReport(
            iterations=iterations,
            method=method,
            block_size=block_size,
            original_max_drawdown_pct=0.0,
            median_max_drawdown_pct=0.0,
            percentile_95_max_drawdown_pct=0.0,
            worst_case_drawdown_pct=0.0,
            ruin_probability_pct=0.0,
            sample_size=0,
            sample_adequate=False,
            warning=warning,
        )

    rng = random.Random(seed)
    simulated_drawdowns: list[float] = []
    ruin_count = 0
    cash = float(starting_capital)
    peak = cash
    orig_max_dd = 0.0
    for pnl in trade_pnls:
        cash += float(pnl)
        peak = max(peak, cash)
        if peak > 0:
            dd = (peak - cash) / peak * 100.0
            orig_max_dd = max(orig_max_dd, dd)

    effective_method = method
    if method == "block_bootstrap" and n < block_size:
        effective_method = "trade_shuffle"
        if warning is None:
            warning = f"Block size {block_size} exceeds sample size {n}; trade shuffle used instead."

    for _ in range(iterations):
        if effective_method == "block_bootstrap":
            sampled_path: list[float] = []
            while len(sampled_path) < n:
                start_idx = rng.randint(0, n - block_size)
                sampled_path.extend(trade_pnls[start_idx : start_idx + block_size])
            sampled_path = sampled_path[:n]
        else:
            sampled_path = list(trade_pnls)
            rng.shuffle(sampled_path)

        sim_cash = float(starting_capital)
        sim_peak = sim_cash
        sim_max_dd = 0.0
        for pnl in sampled_path:
            sim_cash += float(pnl)
            sim_peak = max(sim_peak, sim_cash)
            if sim_peak > 0:
                dd = (sim_peak - max(0.0, sim_cash)) / sim_peak * 100.0
                sim_max_dd = max(sim_max_dd, dd)
            if sim_cash <= starting_capital * 0.5:
                ruin_count += 1
                break
        simulated_drawdowns.append(sim_max_dd)

    simulated_drawdowns.sort()
    median_dd = simulated_drawdowns[len(simulated_drawdowns) // 2]
    idx_95 = min(len(simulated_drawdowns) - 1, int(len(simulated_drawdowns) * 0.95))
    p95_dd = simulated_drawdowns[idx_95]
    worst_dd = simulated_drawdowns[-1]
    ruin_prob = (ruin_count / iterations) * 100.0
    return MonteCarloReport(
        iterations=iterations,
        method=effective_method,
        block_size=block_size,
        original_max_drawdown_pct=round(orig_max_dd, 2),
        median_max_drawdown_pct=round(median_dd, 2),
        percentile_95_max_drawdown_pct=round(p95_dd, 2),
        worst_case_drawdown_pct=round(worst_dd, 2),
        ruin_probability_pct=round(ruin_prob, 2),
        sample_size=n,
        sample_adequate=sample_adequate,
        warning=warning,
    )


def evaluate_multiple_comparison_bias(
    observed_sharpe: float | None,
    num_trials: int,
    sample_length: int,
    min_confidence: float = 0.95,
) -> MultipleComparisonReport:
    """Evaluate Deflated Sharpe Ratio against multiple-comparison data snooping (Workstream W)."""
    if observed_sharpe is None or not math.isfinite(observed_sharpe) or sample_length < 10 or num_trials < 1:
        return MultipleComparisonReport(
            observed_sharpe=0.0,
            num_trials=max(1, num_trials),
            sample_length=max(0, sample_length),
            expected_max_sharpe_null=0.0,
            deflated_sharpe_probability=0.0,
            passes_multiple_testing_gate=False,
            summary="Insufficient observations or undefined Sharpe ratio for multiple-comparison test.",
        )
    euler_gamma = 0.5772156649
    if num_trials == 1:
        expected_max_sr = 0.0
    else:
        z1 = math.sqrt(2.0 * math.log(num_trials))
        z2 = math.sqrt(2.0 * math.log(num_trials * math.e))
        expected_max_sr = ((1.0 - euler_gamma) * z1 + euler_gamma * z2) / math.sqrt(max(sample_length - 1, 1))
    sr_std = math.sqrt((1.0 + 0.5 * (observed_sharpe ** 2)) / max(sample_length - 1, 1))
    z_score = (observed_sharpe - expected_max_sr) / max(sr_std, 1e-8)
    prob = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))
    passed = prob >= min_confidence and observed_sharpe > expected_max_sr
    return MultipleComparisonReport(
        observed_sharpe=round(observed_sharpe, 4),
        num_trials=num_trials,
        sample_length=sample_length,
        expected_max_sharpe_null=round(expected_max_sr, 4),
        deflated_sharpe_probability=round(prob, 4),
        passes_multiple_testing_gate=passed,
        summary=(
            f"Deflated Sharpe probability {prob:.2%} vs {min_confidence:.0%} threshold across {num_trials} trials "
            f"(null max SR={expected_max_sr:.3f})."
        ),
    )


def evaluate_strategy_promotion(
    strategy_name: str,
    backtest_res: BacktestResult,
    wf_report: WalkForwardReport,
    mc_report: MonteCarloReport,
    is_verified_dataset: bool = False,
    min_oos_trades: int = 30,
    max_allowed_dd_pct: float = 15.0,
) -> StrategyPromotionDecision:
    """Enforce strict promotion gates: Research -> OOS -> Stress -> Paper -> Approval (NT-P1-11)."""
    reasons: list[str] = []

    if not is_verified_dataset:
        reasons.append("Dataset provenance/license is unverified (smoke-test sample only).")

    if backtest_res.expectancy <= 0:
        reasons.append(f"Non-positive net expectancy (Rs {backtest_res.expectancy:.2f}).")

    if not mc_report.sample_adequate:
        reasons.append(
            f"Monte Carlo sample inadequate ({mc_report.sample_size} < 30 trades); "
            "stress percentiles are exploratory only."
        )

    if wf_report.total_oos_trades < min_oos_trades:
        reasons.append(
            f"Insufficient OOS trades ({wf_report.total_oos_trades} < {min_oos_trades} required)."
        )

    if wf_report.confidence_verdict != "ROBUST_CANDIDATE":
        reasons.append(f"Walk-forward verdict is '{wf_report.confidence_verdict}', not 'ROBUST_CANDIDATE'.")

    if mc_report.percentile_95_max_drawdown_pct > max_allowed_dd_pct or mc_report.ruin_probability_pct > 0.0:
        reasons.append(
            f"Monte Carlo stress test failed (95th DD: {mc_report.percentile_95_max_drawdown_pct:.2f}%, Ruin: {mc_report.ruin_probability_pct:.2f}%)."
        )

    if reasons:
        return StrategyPromotionDecision(
            strategy_name=strategy_name,
            current_stage=PromotionStage.BACKTEST_VALIDATED,
            recommended_stage=PromotionStage.DRAFT,
            promoted=False,
            reasons=tuple(reasons),
        )

    return StrategyPromotionDecision(
        strategy_name=strategy_name,
        current_stage=PromotionStage.STRESS_VALIDATED,
        recommended_stage=PromotionStage.PAPER_SHADOW_VALIDATED,
        promoted=True,
        reasons=("All historical, rolling OOS, and Monte Carlo stress gates passed. Eligible for shadow trading.",),
    )
