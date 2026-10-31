"""Multi-fold rolling walk-forward validation with warm-up context and block-bootstrap Monte Carlo."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Literal

from nexus_titan.research.backtest import BacktestResult, InstrumentType, run_backtest


class PromotionStage(str, Enum):
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
    confidence_verdict: str
    status_summary: str

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
    """Monte Carlo report with deterministic seed and risk-of-ruin estimate."""
    iterations: int
    method: str
    block_size: int
    original_max_drawdown_pct: float
    median_max_drawdown_pct: float
    percentile_95_max_drawdown_pct: float
    worst_case_drawdown_pct: float
    ruin_probability_pct: float


@dataclass(frozen=True)
class StrategyPromotionDecision:
    strategy_name: str
    current_stage: PromotionStage
    recommended_stage: PromotionStage
    promoted: bool
    reasons: tuple[str, ...]


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
) -> tuple[list[BacktestResult], WalkForwardReport]:
    """Perform rolling chronological train/test validation with warm-up history."""
    n = len(candles)
    if n < 30:
        raise ValueError("At least 30 candles are required for rolling walk-forward validation.")
    folds: list[WalkForwardFoldResult] = []
    oos_results: list[BacktestResult] = []
    fold_splits = [(0.50, 0.70), (0.70, 0.85), (0.85, 1.00)] if num_folds == 3 else [(0.70, 1.00)]
    compounded_multiplier = 1.0

    for idx, (train_end_pct, test_end_pct) in enumerate(fold_splits, start=1):
        train_end = int(n * train_end_pct)
        test_end = int(n * test_end_pct)
        train_data = candles[:train_end]
        warmup_start = max(0, train_end - warmup_lookback)
        actual_warmup_bars = train_end - warmup_start
        test_data_with_warmup = candles[warmup_start:test_end]

        train_sig = signal_factory(train_data)
        train_res = run_backtest(
            train_data, starting_capital=starting_capital,
            fee_per_side=fee_per_side, slippage_per_side=slippage_per_side,
            signal=train_sig, stop_loss_pct=stop_loss_pct, target_pct=target_pct,
            use_indian_statutory_costs=use_indian_statutory_costs,
            instrument_type=instrument_type, sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            instrument_lot_size=instrument_lot_size,
        )
        test_sig = signal_factory(test_data_with_warmup)
        test_res = run_backtest(
            test_data_with_warmup, starting_capital=starting_capital,
            fee_per_side=fee_per_side, slippage_per_side=slippage_per_side,
            signal=test_sig, warmup_bars=actual_warmup_bars,
            stop_loss_pct=stop_loss_pct, target_pct=target_pct,
            use_indian_statutory_costs=use_indian_statutory_costs,
            instrument_type=instrument_type, sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            instrument_lot_size=instrument_lot_size,
        )
        oos_results.append(test_res)
        compounded_multiplier *= (1.0 + test_res.return_percent / 100.0)
        folds.append(WalkForwardFoldResult(
            fold_number=idx, train_bars=len(train_data),
            test_bars=test_end - train_end, warmup_bars_used=actual_warmup_bars,
            in_sample_return_pct=round(train_res.return_percent, 2),
            out_of_sample_return_pct=round(test_res.return_percent, 2),
            out_of_sample_trades=test_res.total_trades,
            out_of_sample_sharpe=test_res.sharpe_ratio,
            is_profitable_oos=test_res.return_percent > 0,
        ))

    total_oos_trades = sum(f.out_of_sample_trades for f in folds)
    avg_oos_return = sum(f.out_of_sample_return_pct for f in folds) / len(folds)
    compounded_return = (compounded_multiplier - 1.0) * 100.0
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
        total_folds=len(folds), folds=folds,
        aggregate_oos_return_pct=round(avg_oos_return, 2),
        compounded_oos_return_pct=round(compounded_return, 2),
        total_oos_trades=total_oos_trades,
        confidence_verdict=verdict, status_summary=summary,
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
    """Single chronological train/test split with minimum sample-size gate."""
    split_idx = int(len(candles) * train_ratio)
    train_data = candles[:split_idx]
    test_data = candles[split_idx:]
    train_sig = signal_factory(train_data)
    train_res = run_backtest(
        train_data, starting_capital=starting_capital,
        fee_per_side=fee_per_side, slippage_per_side=slippage_per_side,
        signal=train_sig, use_indian_statutory_costs=use_indian_statutory_costs,
        instrument_type=instrument_type,
    )
    test_sig = signal_factory(test_data)
    test_res = run_backtest(
        test_data, starting_capital=starting_capital,
        fee_per_side=fee_per_side, slippage_per_side=slippage_per_side,
        signal=test_sig, use_indian_statutory_costs=use_indian_statutory_costs,
        instrument_type=instrument_type,
    )
    fold = WalkForwardFoldResult(
        fold_number=1, train_bars=len(train_data), test_bars=len(test_data),
        warmup_bars_used=0, in_sample_return_pct=round(train_res.return_percent, 2),
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
        total_folds=1, folds=[fold],
        aggregate_oos_return_pct=round(test_res.return_percent, 2),
        compounded_oos_return_pct=round(test_res.return_percent, 2),
        total_oos_trades=test_res.total_trades,
        confidence_verdict=verdict, status_summary=summary,
    )
    return train_res, test_res, report


def run_monte_carlo_simulation(
    trade_pnls: list[float],
    starting_capital: float = 100000.0,
    iterations: int = 1000,
    seed: int = 42,
    method: str = "block_bootstrap",
    block_size: int = 3,
) -> MonteCarloReport:
    """Monte Carlo simulation with block bootstrap and ruin drawdown fix."""
    if not trade_pnls:
        return MonteCarloReport(
            iterations=iterations, method=method, block_size=block_size,
            original_max_drawdown_pct=0.0, median_max_drawdown_pct=0.0,
            percentile_95_max_drawdown_pct=0.0, worst_case_drawdown_pct=0.0,
            ruin_probability_pct=0.0,
        )
    rng = random.Random(seed)
    simulated_drawdowns: list[float] = []
    ruin_count = 0
    n = len(trade_pnls)
    cash = starting_capital
    peak = cash
    original_max_drawdown = 0.0
    for pnl in trade_pnls:
        cash += pnl
        peak = max(peak, cash)
        if peak > 0:
            original_max_drawdown = max(original_max_drawdown, (peak - cash) / peak * 100.0)

    for _ in range(iterations):
        if method == "block_bootstrap" and n >= block_size:
            sampled: list[float] = []
            while len(sampled) < n:
                start_idx = rng.randint(0, n - block_size)
                sampled.extend(trade_pnls[start_idx:start_idx + block_size])
            sampled = sampled[:n]
        else:
            sampled = list(trade_pnls)
            rng.shuffle(sampled)
        simulated_cash = starting_capital
        simulated_peak = simulated_cash
        simulated_max_drawdown = 0.0
        for pnl in sampled:
            simulated_cash += pnl
            simulated_peak = max(simulated_peak, simulated_cash)
            if simulated_peak > 0:
                drawdown = (simulated_peak - max(0.0, simulated_cash)) / simulated_peak * 100.0
                simulated_max_drawdown = max(simulated_max_drawdown, drawdown)
            if simulated_cash <= starting_capital * 0.5:
                ruin_count += 1
                break
        simulated_drawdowns.append(simulated_max_drawdown)

    simulated_drawdowns.sort()
    median_dd = simulated_drawdowns[len(simulated_drawdowns) // 2]
    percentile_95_dd = simulated_drawdowns[int(len(simulated_drawdowns) * 0.95)]
    worst_dd = simulated_drawdowns[-1]
    ruin_probability = (ruin_count / iterations) * 100.0
    return MonteCarloReport(
        iterations=iterations, method=method, block_size=block_size,
        original_max_drawdown_pct=round(original_max_drawdown, 2),
        median_max_drawdown_pct=round(median_dd, 2),
        percentile_95_max_drawdown_pct=round(percentile_95_dd, 2),
        worst_case_drawdown_pct=round(worst_dd, 2),
        ruin_probability_pct=round(ruin_probability, 2),
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
    """Enforce dataset, expectancy, OOS sample, walk-forward and Monte Carlo promotion gates."""
    reasons: list[str] = []
    if not is_verified_dataset:
        reasons.append("Dataset provenance/license is unverified (smoke-test sample only).")
    if backtest_res.expectancy <= 0:
        reasons.append(f"Non-positive net expectancy (Rs {backtest_res.expectancy:.2f}).")
    if wf_report.total_oos_trades < min_oos_trades:
        reasons.append(
            f"Insufficient OOS trades ({wf_report.total_oos_trades} < minimum {min_oos_trades} required)."
        )
    if wf_report.confidence_verdict != "ROBUST_CANDIDATE":
        reasons.append(f"Walk-forward verdict is '{wf_report.confidence_verdict}', not 'ROBUST_CANDIDATE'.")
    if mc_report.percentile_95_max_drawdown_pct > max_allowed_dd_pct or mc_report.ruin_probability_pct > 0.0:
        reasons.append(
            f"Monte Carlo stress test failed (95th DD: {mc_report.percentile_95_max_drawdown_pct:.2f}%, Ruin: {mc_report.ruin_probability_pct:.2f}%)."
        )
    if reasons:
        return StrategyPromotionDecision(
            strategy_name=strategy_name, current_stage=PromotionStage.BACKTEST_VALIDATED,
            recommended_stage=PromotionStage.DRAFT, promoted=False, reasons=tuple(reasons),
        )
    return StrategyPromotionDecision(
        strategy_name=strategy_name, current_stage=PromotionStage.STRESS_VALIDATED,
        recommended_stage=PromotionStage.PAPER_SHADOW_VALIDATED, promoted=True,
        reasons=("All historical, rolling OOS, and Monte Carlo stress gates passed. Eligible for shadow trading.",),
    )
