"""Trade post-mortem and evidence-bounded P&L attribution.

Attribution is descriptive, not causal. Slippage remains an explicit estimate unless
actual order/quote fills are supplied by a future execution-data adapter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from nexus_titan.research.backtest import BacktestResult


@dataclass(frozen=True)
class RegimeAttribution:
    regime: str
    trades: int
    net_pnl: float
    win_rate_pct: float
    average_return_pct: float


@dataclass(frozen=True)
class PostMortemReport:
    strategy_name: str
    total_trades: int
    gross_market_pnl: float
    slippage_drag: float
    statutory_fees_drag: float
    net_realized_pnl: float
    execution_efficiency_pct: float
    stop_loss_exits: int
    target_exits: int
    signal_exits: int
    premature_stop_outs: int
    primary_leakage_source: str
    actionable_recommendation: str
    # Stage 8 descriptive attribution fields. Defaults preserve older constructors.
    long_trades: int = 0
    short_trades: int = 0
    average_win: float = 0.0
    average_loss: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    average_holding_bars: float = 0.0
    profit_concentration_pct: float = 0.0
    exit_reason_counts: tuple[tuple[str, int], ...] = ()
    regime_attribution: tuple[RegimeAttribution, ...] = ()
    evidence_warning: str = ""
    attribution_method: str = "DESCRIPTIVE_TRADE_LOG_NOT_CAUSAL"


def _finite_number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _regime_breakdown(trades: list[dict], regimes: Mapping[int, str] | None) -> tuple[RegimeAttribution, ...]:
    if regimes is None:
        return ()
    grouped: dict[str, list[dict]] = {}
    for trade in trades:
        entry_index = trade.get("entry_index")
        label = regimes.get(entry_index, "UNKNOWN") if isinstance(entry_index, int) else "UNKNOWN"
        if not isinstance(label, str) or not label.strip():
            label = "UNKNOWN"
        grouped.setdefault(label.strip().upper(), []).append(trade)
    result = []
    for label, rows in sorted(grouped.items()):
        pnls = [_finite_number(row.get("pnl")) for row in rows]
        returns = [_finite_number(row.get("return_pct")) for row in rows]
        result.append(RegimeAttribution(
            regime=label,
            trades=len(rows),
            net_pnl=round(sum(pnls), 2),
            win_rate_pct=round(sum(pnl > 0 for pnl in pnls) / len(rows) * 100, 2),
            average_return_pct=round(sum(returns) / len(rows), 4),
        ))
    return tuple(result)


def generate_post_mortem(
    strategy_name: str,
    result: BacktestResult,
    slippage_per_side: float = 2.0,
    *,
    regime_by_entry_index: Mapping[int, str] | None = None,
    minimum_evidence_trades: int = 30,
) -> PostMortemReport:
    """Summarize trade outcomes and friction without claiming causal attribution.

    `slippage_per_side` is an estimate in currency units per unit per side. It must
    not be interpreted as actual execution slippage unless independently calibrated.
    """
    if not isinstance(strategy_name, str) or not strategy_name.strip():
        raise ValueError("strategy_name is required.")
    if isinstance(slippage_per_side, bool) or not isinstance(slippage_per_side, (int, float)) or not math.isfinite(slippage_per_side) or slippage_per_side < 0:
        raise ValueError("slippage_per_side must be finite and non-negative.")
    if isinstance(minimum_evidence_trades, bool) or not isinstance(minimum_evidence_trades, int) or minimum_evidence_trades < 1:
        raise ValueError("minimum_evidence_trades must be a positive integer.")

    rows = list(getattr(result, "trade_log", []) or [])
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        warning = f"Insufficient evidence: 0 trades; minimum is {minimum_evidence_trades}."
        return PostMortemReport(
            strategy_name=strategy_name.strip(), total_trades=0, gross_market_pnl=0.0,
            slippage_drag=0.0, statutory_fees_drag=0.0, net_realized_pnl=0.0,
            execution_efficiency_pct=0.0, stop_loss_exits=0, target_exits=0,
            signal_exits=0, premature_stop_outs=0, primary_leakage_source="NO_TRADES",
            actionable_recommendation="Collect a larger, provenance-verified sample before changing strategy parameters.",
            evidence_warning=warning,
        )

    pnls = [_finite_number(row.get("pnl")) for row in rows]
    returns = [_finite_number(row.get("return_pct")) for row in rows]
    slippage_drag = sum(2.0 * float(slippage_per_side) * max(0.0, _finite_number(row.get("quantity"))) for row in rows)
    fees_drag = max(0.0, _finite_number(getattr(result, "total_fees", 0.0)))
    net_pnl = round(sum(pnls), 2)
    gross_market_pnl = round(net_pnl + fees_drag + slippage_drag, 2)

    reasons = [str(row.get("exit_reason") or "UNKNOWN").upper() for row in rows]
    reason_counts: dict[str, int] = {}
    for reason in reasons:
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    stop_exits = sum(count for reason, count in reason_counts.items() if "STOP_LOSS" in reason)
    target_exits = sum(count for reason, count in reason_counts.items() if "TARGET" in reason)
    signal_exits = reason_counts.get("SIGNAL_EXIT", 0)
    premature_stops = sum(
        1 for row, reason in zip(rows, reasons)
        if "STOP_LOSS" in reason
        and isinstance(row.get("entry_index"), int)
        and isinstance(row.get("exit_index"), int)
        and 0 <= row["exit_index"] - row["entry_index"] <= 1
    )

    positive = [pnl for pnl in pnls if pnl > 0]
    negative = [pnl for pnl in pnls if pnl < 0]
    long_trades = sum(str(row.get("side", "")).upper() == "LONG" for row in rows)
    short_trades = sum(str(row.get("side", "")).upper() == "SHORT" for row in rows)
    holding = [row["exit_index"] - row["entry_index"] for row in rows
               if isinstance(row.get("entry_index"), int) and isinstance(row.get("exit_index"), int)
               and row["exit_index"] >= row["entry_index"]]
    positive_gross = sum(positive)
    profit_concentration = max(positive) / positive_gross * 100 if positive and positive_gross > 0 else 0.0
    efficiency = max(0.0, round(net_pnl / gross_market_pnl * 100.0, 2)) if gross_market_pnl > 0 else 0.0

    if stop_exits > len(rows) * 0.5:
        leakage, recommendation = "HIGH_STOP_OUT_RATE", "Review stop placement by market regime and volatility; do not widen stops without out-of-sample risk testing."
    elif fees_drag + slippage_drag > abs(gross_market_pnl) * 0.4:
        leakage, recommendation = "EXECUTION_FRICTION_AND_TAXES", "Validate instrument-specific charges and reduce turnover only if out-of-sample evidence supports it."
    elif positive and profit_concentration > 60:
        leakage, recommendation = "PROFIT_CONCENTRATION", "Check whether results depend on a small number of outlier trades; require broader OOS evidence."
    elif not negative:
        leakage, recommendation = "LOSS_SAMPLE_INSUFFICIENT", "A loss-free small sample is not proof of robustness; test adverse regimes and larger samples."
    else:
        leakage, recommendation = "REGIME_AND_SIGNAL_STABILITY", "Review regime-wise outcomes, sample adequacy and execution assumptions before modifying the strategy."

    warning = ""
    if len(rows) < minimum_evidence_trades:
        warning = f"Insufficient evidence: {len(rows)} trades; minimum review threshold is {minimum_evidence_trades}. Descriptive only."
    if not regime_by_entry_index:
        warning = (warning + " " if warning else "") + "Regime attribution unavailable: entry-index regime labels were not supplied."

    return PostMortemReport(
        strategy_name=strategy_name.strip(), total_trades=len(rows),
        gross_market_pnl=gross_market_pnl, slippage_drag=round(slippage_drag, 2),
        statutory_fees_drag=round(fees_drag, 2), net_realized_pnl=net_pnl,
        execution_efficiency_pct=efficiency, stop_loss_exits=stop_exits,
        target_exits=target_exits, signal_exits=signal_exits,
        premature_stop_outs=premature_stops, primary_leakage_source=leakage,
        actionable_recommendation=recommendation, long_trades=long_trades,
        short_trades=short_trades,
        average_win=round(sum(positive) / len(positive), 2) if positive else 0.0,
        average_loss=round(sum(negative) / len(negative), 2) if negative else 0.0,
        best_trade_pnl=round(max(pnls), 2), worst_trade_pnl=round(min(pnls), 2),
        average_holding_bars=round(sum(holding) / len(holding), 2) if holding else 0.0,
        profit_concentration_pct=round(profit_concentration, 2),
        exit_reason_counts=tuple(sorted(reason_counts.items())),
        regime_attribution=_regime_breakdown(rows, regime_by_entry_index),
        evidence_warning=warning,
    )
