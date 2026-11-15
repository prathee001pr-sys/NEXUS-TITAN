"""Connects TITAN EVOLVE to the V6 historical backtest/walk-forward engine.

V2's original research/strategies.py and validation.py remain unchanged; this
adapter imports the V6 catalogue through explicit non-conflicting module names.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from nexus_titan.research.backtest import InstrumentType
from nexus_titan.research.v6_strategies import AVAILABLE_STRATEGIES
from nexus_titan.research.v6_validation import rolling_walk_forward_validation


@dataclass(frozen=True)
class StrategyEvidence:
    strategy_key: str
    strategy_name: str
    compounded_oos_return_pct: float
    total_oos_trades: int
    worst_fold_drawdown_pct: float
    validation_verdict: str
    fold_returns_pct: tuple[float, ...]
    cost_model: str = "INDIAN_STATUTORY"
    instrument_type: str = "EQUITY_DELIVERY"


@dataclass(frozen=True)
class StrategyComparison:
    baseline: StrategyEvidence
    candidate: StrategyEvidence
    sample_size: int
    eligible_for_proposal: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategyExperimentRunner:
    """Runs built-in strategies only; no generated Python is executed."""

    def __init__(self, min_oos_trades: int = 30) -> None:
        if isinstance(min_oos_trades, bool) or not isinstance(min_oos_trades, int) or min_oos_trades < 30:
            raise ValueError("min_oos_trades must be an integer of at least 30.")
        self.min_oos_trades = min_oos_trades

    @staticmethod
    def _evaluate(
        strategy_key: str,
        candles: list[dict[str, float]],
        num_folds: int,
        starting_capital: float,
        fee_per_side: float,
        slippage_per_side: float,
        use_indian_statutory_costs: bool = True,
        instrument_type: InstrumentType = "EQUITY_DELIVERY",
        sizing_mode: Literal["fixed", "capital_risk"] = "fixed",
        risk_per_trade_pct: float = 1.0,
        stop_loss_pct: float | None = None,
        target_pct: float | None = None,
        instrument_lot_size: int = 1,
    ) -> StrategyEvidence:
        if strategy_key not in AVAILABLE_STRATEGIES:
            raise ValueError(f"Unknown built-in strategy: {strategy_key}")
        template = AVAILABLE_STRATEGIES[strategy_key]()
        oos_results, report = rolling_walk_forward_validation(
            candles,
            lambda _train: (lambda index, data: AVAILABLE_STRATEGIES[strategy_key]().get_signal(index, data)),
            num_folds=num_folds,
            min_trades_gate=1,
            starting_capital=starting_capital,
            fee_per_side=fee_per_side,
            slippage_per_side=slippage_per_side,
            use_indian_statutory_costs=use_indian_statutory_costs,
            instrument_type=instrument_type,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            stop_loss_pct=stop_loss_pct,
            target_pct=target_pct,
            instrument_lot_size=instrument_lot_size,
        )
        return StrategyEvidence(
            strategy_key=strategy_key,
            strategy_name=template.name,
            compounded_oos_return_pct=report.compounded_oos_return_pct,
            total_oos_trades=report.total_oos_trades,
            worst_fold_drawdown_pct=max((r.max_drawdown_percent for r in oos_results), default=0.0),
            validation_verdict=report.confidence_verdict,
            fold_returns_pct=tuple(f.out_of_sample_return_pct for f in report.folds),
            cost_model="INDIAN_STATUTORY" if use_indian_statutory_costs else "FLAT_BROKERAGE",
            instrument_type=instrument_type,
        )

    def compare(
        self,
        candles: list[dict[str, float]],
        baseline_key: str,
        candidate_key: str,
        num_folds: int = 3,
        starting_capital: float = 100_000.0,
        fee_per_side: float = 20.0,
        slippage_per_side: float = 2.0,
        use_indian_statutory_costs: bool = True,
        instrument_type: InstrumentType = "EQUITY_DELIVERY",
        sizing_mode: Literal["fixed", "capital_risk"] = "fixed",
        risk_per_trade_pct: float = 1.0,
        stop_loss_pct: float | None = None,
        target_pct: float | None = None,
        instrument_lot_size: int = 1,
    ) -> StrategyComparison:
        if len(candles) < 100:
            raise ValueError("At least 100 candles are required for a meaningful multi-fold comparison.")
        if baseline_key == candidate_key:
            raise ValueError("Baseline and candidate strategies must be different.")
        if num_folds != 3:
            raise ValueError("The current walk-forward validator supports exactly 3 chronological folds.")
        baseline = self._evaluate(
            baseline_key, candles, num_folds, starting_capital, fee_per_side, slippage_per_side,
            use_indian_statutory_costs=use_indian_statutory_costs, instrument_type=instrument_type,
            sizing_mode=sizing_mode, risk_per_trade_pct=risk_per_trade_pct,
            stop_loss_pct=stop_loss_pct, target_pct=target_pct, instrument_lot_size=instrument_lot_size,
        )
        candidate = self._evaluate(
            candidate_key, candles, num_folds, starting_capital, fee_per_side, slippage_per_side,
            use_indian_statutory_costs=use_indian_statutory_costs, instrument_type=instrument_type,
            sizing_mode=sizing_mode, risk_per_trade_pct=risk_per_trade_pct,
            stop_loss_pct=stop_loss_pct, target_pct=target_pct, instrument_lot_size=instrument_lot_size,
        )
        sample_size = min(baseline.total_oos_trades, candidate.total_oos_trades)
        reasons: list[str] = []
        if sample_size < self.min_oos_trades:
            reasons.append(f"Insufficient paired OOS trade evidence: {sample_size} < {self.min_oos_trades}.")
        if candidate.validation_verdict != "ROBUST_CANDIDATE":
            reasons.append(f"Candidate verdict is {candidate.validation_verdict}, not ROBUST_CANDIDATE.")
        if candidate.compounded_oos_return_pct <= baseline.compounded_oos_return_pct:
            reasons.append("Candidate did not improve compounded out-of-sample return.")
        if candidate.worst_fold_drawdown_pct > baseline.worst_fold_drawdown_pct + 0.25:
            reasons.append("Candidate worsened worst-fold drawdown by more than 0.25 percentage points.")
        return StrategyComparison(baseline, candidate, sample_size, not reasons, tuple(reasons))

    def evaluate_all(
        self,
        candles: list[dict[str, float]],
        num_folds: int = 3,
        starting_capital: float = 100_000.0,
        fee_per_side: float = 20.0,
        slippage_per_side: float = 2.0,
        use_indian_statutory_costs: bool = True,
        instrument_type: InstrumentType = "EQUITY_DELIVERY",
        sizing_mode: Literal["fixed", "capital_risk"] = "fixed",
        risk_per_trade_pct: float = 1.0,
        stop_loss_pct: float | None = None,
        target_pct: float | None = None,
        instrument_lot_size: int = 1,
    ) -> dict[str, dict[str, Any]]:
        """Evaluate all built-in strategies across 3 chronological walk-forward folds."""
        if len(candles) < 100:
            raise ValueError("At least 100 candles are required for multi-fold walk-forward evaluation.")
        results: dict[str, dict[str, Any]] = {}
        for key in AVAILABLE_STRATEGIES:
            ev = self._evaluate(
                key, candles, num_folds, starting_capital, fee_per_side, slippage_per_side,
                use_indian_statutory_costs=use_indian_statutory_costs, instrument_type=instrument_type,
                sizing_mode=sizing_mode, risk_per_trade_pct=risk_per_trade_pct,
                stop_loss_pct=stop_loss_pct, target_pct=target_pct, instrument_lot_size=instrument_lot_size,
            )
            results[key] = asdict(ev)
        return results

    def run_and_register(
        self,
        engine,
        candles: list[dict[str, float]],
        baseline_key: str,
        candidate_key: str,
        num_folds: int = 3,
        starting_capital: float = 100_000.0,
        fee_per_side: float = 20.0,
        slippage_per_side: float = 2.0,
        use_indian_statutory_costs: bool = True,
        instrument_type: InstrumentType = "EQUITY_DELIVERY",
        sizing_mode: Literal["fixed", "capital_risk"] = "fixed",
        risk_per_trade_pct: float = 1.0,
        stop_loss_pct: float | None = None,
        target_pct: float | None = None,
        instrument_lot_size: int = 1,
    ):
        """Compare, create a proposal and store the measured experiment if eligible.

        This records evidence only. It does not promote a strategy or alter live trading.
        """
        comparison = self.compare(
            candles, baseline_key, candidate_key, num_folds,
            starting_capital, fee_per_side, slippage_per_side,
            use_indian_statutory_costs=use_indian_statutory_costs,
            instrument_type=instrument_type,
            sizing_mode=sizing_mode,
            risk_per_trade_pct=risk_per_trade_pct,
            stop_loss_pct=stop_loss_pct,
            target_pct=target_pct,
            instrument_lot_size=instrument_lot_size,
        )
        if not comparison.eligible_for_proposal:
            return comparison, None, None
        proposal = self.create_improvement_proposal(engine, comparison)
        experiment = engine.record_experiment(
            proposal_id=proposal.proposal_id,
            baseline_metric=comparison.baseline.compounded_oos_return_pct,
            candidate_metric=comparison.candidate.compounded_oos_return_pct,
            metric_name="compounded_oos_return_pct",
            sample_size=comparison.sample_size,
            out_of_sample=True,
            safety_checks_passed=(comparison.candidate.worst_fold_drawdown_pct
                                  <= comparison.baseline.worst_fold_drawdown_pct + 0.25),
            metric_direction="higher",
        )
        return comparison, proposal, experiment

    @staticmethod
    def create_improvement_proposal(engine, comparison: StrategyComparison):
        """Create an auditable proposal from an eligible comparison; never promotes it."""
        if not comparison.eligible_for_proposal:
            raise PermissionError("Strategy comparison is not eligible: " + " ".join(comparison.reasons))
        return engine.propose_improvement(
            title=f"Evaluate {comparison.candidate.strategy_name} against {comparison.baseline.strategy_name}",
            description="Candidate showed stronger multi-fold out-of-sample evidence in the controlled strategy comparison.",
            rationale=(f"OOS return {comparison.candidate.compounded_oos_return_pct:.2f}% vs "
                       f"{comparison.baseline.compounded_oos_return_pct:.2f}%; "
                       f"worst-fold drawdown {comparison.candidate.worst_fold_drawdown_pct:.2f}% vs "
                       f"{comparison.baseline.worst_fold_drawdown_pct:.2f}%"),
            expected_benefit="Potentially stronger out-of-sample performance subject to independent review and paper validation.",
            risk_level="HIGH",
        )
