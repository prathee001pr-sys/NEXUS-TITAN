"""Automated Trade Post-Mortem and Causal P&L Attribution Engine."""
from __future__ import annotations
from dataclasses import dataclass
from nexus_titan.research.backtest import BacktestResult


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


def generate_post_mortem(strategy_name: str, result: BacktestResult,
                         slippage_per_side: float = 2.0) -> PostMortemReport:
    if not result.trade_log:
        return PostMortemReport(strategy_name, 0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                 0, 0, 0, 0, "NO_TRADES",
                                 "Adjust indicator thresholds or test across longer dataset.")
    total_slippage = sum(2.0 * slippage_per_side * t["quantity"] for t in result.trade_log)
    total_fees = result.total_fees
    net_pnl = result.net_profit
    gross_market_pnl = round(net_pnl + total_fees + total_slippage, 2)
    stop_exits = sum(1 for t in result.trade_log if "STOP_LOSS" in t.get("exit_reason", ""))
    target_exits = sum(1 for t in result.trade_log if "TARGET" in t.get("exit_reason", ""))
    signal_exits = sum(1 for t in result.trade_log if t.get("exit_reason") == "SIGNAL_EXIT")
    premature_stops = sum(1 for t in result.trade_log
                          if "STOP_LOSS" in t.get("exit_reason", "")
                          and (t["exit_index"] - t["entry_index"]) <= 1)
    efficiency = max(0.0, round((net_pnl / gross_market_pnl) * 100.0, 2)) if gross_market_pnl > 0 else 0.0
    if stop_exits > result.total_trades * 0.5:
        leakage = "HIGH_STOP_OUT_RATE"
        recommendation = "Widen stop-loss using ATR(14) multiplier instead of fixed percentage."
    elif (total_fees + total_slippage) > abs(gross_market_pnl) * 0.4:
        leakage = "EXECUTION_FRICTION_AND_TAXES"
        recommendation = "Reduce trade turnover and verify instrument-specific charges before comparing strategies."
    else:
        leakage = "OPTIMAL_EXECUTION"
        recommendation = "Execution friction appears controlled; focus on out-of-sample regime stability."
    return PostMortemReport(
        strategy_name, result.total_trades, gross_market_pnl, round(total_slippage, 2),
        round(total_fees, 2), round(net_pnl, 2), efficiency, stop_exits, target_exits,
        signal_exits, premature_stops, leakage, recommendation,
    )
