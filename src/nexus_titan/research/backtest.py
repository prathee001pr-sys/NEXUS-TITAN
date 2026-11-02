"""Production-grade historical backtesting engine with instrument-aware costs, safe lot sizing, and intrabar stops."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from nexus_titan.cost.charges import InstrumentType, calculate_indian_trade_costs
from nexus_titan.data.canonical import load_canonical_data
from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig


@dataclass(frozen=True)
class BacktestResult:
    """Comprehensive performance and risk scorecard."""
    starting_capital: float
    ending_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_percent: float
    net_profit: float
    return_percent: float
    max_drawdown_percent: float
    profit_factor: float | None
    expectancy: float
    breakeven_trades: int = 0
    total_fees: float = 0.0
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    benchmark_return_percent: float = 0.0
    alpha_percent: float = 0.0
    intrabar_stops_hit: int = 0
    intrabar_targets_hit: int = 0
    sizing_mode: str = "fixed"
    instrument_type: str = "EQUITY_DELIVERY"
    rejected_for_risk_count: int = 0
    equity_curve: list[float] = field(default_factory=list)
    trade_log: list[dict] = field(default_factory=list)


def compute_file_sha256(path: str | Path) -> str:
    """Compute SHA-256 hash of a dataset file for provenance tracking."""
    file_path = Path(path)
    if not file_path.exists():
        return "UNKNOWN"
    return hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]


def load_candles(path: str | Path, symbol: str = "NIFTY", interval: str = "1d") -> list[dict[str, float]]:
    """Load and strictly validate candles using the canonical data pipeline."""
    canonical_candles, report = load_canonical_data(path, symbol=symbol, interval=interval)
    if not report.is_valid:
        error_summary = "; ".join(report.errors)
        raise ValueError(f"Canonical market data validation failed: {error_summary}")
    if len(canonical_candles) < 2:
        raise ValueError("At least two valid candles are required.")
    return [c.to_dict() for c in canonical_candles]


def _trailing_losses(pnls: list[float]) -> int:
    """Count consecutive losses from the most recently completed trade backwards."""
    count = 0
    for pnl in reversed(pnls):
        if pnl < 0:
            count += 1
        else:
            break
    return count


def run_backtest(
    candles: list[dict[str, float]],
    starting_capital: float = 50_000.0,
    quantity: float = 1.0,
    fee_per_side: float = 0.0,
    slippage_per_side: float = 0.0,
    signal: Callable[[int, list[dict[str, float]]], int] | None = None,
    stop_loss_pct: float | None = None,
    target_pct: float | None = None,
    use_indian_statutory_costs: bool = False,
    instrument_type: InstrumentType = "EQUITY_DELIVERY",
    annualization_periods: int = 252,
    sizing_mode: Literal["fixed", "capital_risk"] = "fixed",
    risk_per_trade_pct: float = 1.0,
    instrument_lot_size: int = 1,
    warmup_bars: int = 0,
    initial_margin_pct: float = 20.0,
    instrument_symbol: str = "EQUITY_DEFAULT",
) -> BacktestResult:
    """Run an event-driven historical backtest with costs and portfolio risk checks."""
    numeric_inputs = (starting_capital, quantity, fee_per_side, slippage_per_side)
    try:
        valid_numeric_inputs = all(
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
            for value in numeric_inputs
        )
    except (OverflowError, TypeError, ValueError):
        valid_numeric_inputs = False

    if not valid_numeric_inputs:
        raise ValueError("Capital, quantity, fees, and slippage must be finite numbers.")
    if starting_capital <= 0 or quantity <= 0:
        raise ValueError("Capital and quantity must be positive.")
    if fee_per_side < 0 or slippage_per_side < 0:
        raise ValueError("Costs cannot be negative.")
    if isinstance(risk_per_trade_pct, bool) or not isinstance(risk_per_trade_pct, (int, float)) or not math.isfinite(risk_per_trade_pct) or not 0 < risk_per_trade_pct <= 100:
        raise ValueError("risk_per_trade_pct must be finite and between 0 and 100.")
    if isinstance(instrument_lot_size, bool) or not isinstance(instrument_lot_size, int) or instrument_lot_size < 1:
        raise ValueError("instrument_lot_size must be a positive integer.")
    if isinstance(initial_margin_pct, bool) or not isinstance(initial_margin_pct, (int, float)) or not math.isfinite(initial_margin_pct) or not 1 <= initial_margin_pct <= 100:
        raise ValueError("initial_margin_pct must be finite and between 1 and 100.")
    if sizing_mode not in ("fixed", "capital_risk"):
        raise ValueError("Unsupported sizing_mode.")
    if len(candles) < 2:
        raise ValueError("At least two candles are required.")

    def compute_fees(side: str, price: float, qty: float) -> float:
        if use_indian_statutory_costs:
            breakdown = calculate_indian_trade_costs(side, price, int(qty), instrument_type)  # type: ignore[arg-type]
            return breakdown.total_charges
        return fee_per_side

    cash = starting_capital
    blocked_margin = 0.0
    position = 0.0
    entry_price = 0.0
    entry_index = 0
    active_stop = 0.0
    active_target = 0.0

    wins = losses = breakevens = trades = 0
    accumulated_fees = 0.0
    intrabar_stops = intrabar_targets = rejected_for_risk = 0
    trade_pnls: list[float] = []
    trade_log: list[dict] = []
    equity_curve: list[float] = [starting_capital]
    peak_equity = starting_capital
    max_drawdown = 0.0
    daily_pnl = 0.0
    current_day_key = None
    risk_engine = AuthoritativeRiskEngine(PortfolioRiskConfig(
        max_risk_per_trade_pct=float(risk_per_trade_pct),
        max_portfolio_exposure_pct=100.0,
        max_concurrent_positions=1,
        daily_loss_limit_pct=3.0,
        consecutive_loss_limit=3,
        max_drawdown_limit_pct=10.0,
    ))

    def mark_equity(mark_price: float) -> float:
        if instrument_type == "FUTURES":
            unrealized = (mark_price - entry_price) * position if position > 0 else 0.0
            return cash + blocked_margin + unrealized
        return cash + position * mark_price

    def record_closed_trade(pnl_value: float) -> None:
        nonlocal daily_pnl
        trade_pnls.append(pnl_value)
        daily_pnl += pnl_value

    for index in range(len(candles) - 1):
        next_candle = candles[index + 1]
        next_open = next_candle["open"]
        next_high = next_candle["high"]
        next_low = next_candle["low"]
        next_close = next_candle["close"]
        day_key = str(next_candle.get("date", next_candle.get("timestamp", index + 1)))[:10]
        if day_key != current_day_key:
            current_day_key = day_key
            daily_pnl = 0.0

        # Resolve ambiguous intrabar touches conservatively: stop-loss before target.
        if position > 0:
            exit_reason = None
            fill_price = 0.0
            if active_stop > 0:
                if next_open <= active_stop:
                    exit_reason = "STOP_LOSS_GAP"
                    fill_price = next_open - slippage_per_side
                    intrabar_stops += 1
                elif next_low <= active_stop:
                    exit_reason = "STOP_LOSS"
                    fill_price = active_stop - slippage_per_side
                    intrabar_stops += 1
            if exit_reason is None and active_target > 0:
                if next_open >= active_target:
                    exit_reason = "TARGET_GAP"
                    fill_price = next_open - slippage_per_side
                    intrabar_targets += 1
                elif next_high >= active_target:
                    exit_reason = "TARGET"
                    fill_price = active_target - slippage_per_side
                    intrabar_targets += 1

            if exit_reason:
                exit_fee = compute_fees("SELL", fill_price, position)
                gross_pnl = (fill_price - entry_price) * position
                if instrument_type == "FUTURES":
                    cash += blocked_margin + gross_pnl - exit_fee
                    blocked_margin = 0.0
                else:
                    cash += fill_price * position - exit_fee
                pnl = gross_pnl - compute_fees("BUY", entry_price, position) - exit_fee
                accumulated_fees += exit_fee
                record_closed_trade(pnl)
                trades += 1
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1
                else:
                    breakevens += 1
                trade_log.append({
                    "trade_num": trades, "entry_index": entry_index,
                    "exit_index": index + 1, "entry_price": round(entry_price, 2),
                    "exit_price": round(fill_price, 2), "quantity": position,
                    "pnl": round(pnl, 2),
                    "return_pct": round(pnl / (entry_price * position) * 100, 2),
                    "exit_reason": exit_reason,
                })
                position = entry_price = active_stop = active_target = 0.0

        if index < warmup_bars:
            equity_curve.append(mark_equity(next_close))
            continue

        action = signal(index, candles) if signal else 0
        if action == 1 and position == 0:
            buy_price = next_open + slippage_per_side
            if sizing_mode == "capital_risk":
                stop_dist = (buy_price * (stop_loss_pct / 100.0)) if stop_loss_pct else (buy_price * 0.02)
                risk_result = risk_engine.size_and_validate(
                    capital=max(cash + blocked_margin, 1.0),
                    entry_price=buy_price,
                    stop_price=max(0.01, buy_price - stop_dist),
                    symbol=instrument_symbol,
                    lot_size=instrument_lot_size,
                    current_exposure=0.0,
                    current_open_positions=0,
                    realized_daily_loss_pct=max(0.0, -daily_pnl / starting_capital * 100.0),
                    consecutive_losses=_trailing_losses(trade_pnls),
                    current_drawdown_pct=max(0.0, (peak_equity - mark_equity(next_close)) / peak_equity * 100.0),
                    slippage_buffer=slippage_per_side,
                )
                trade_qty = float(risk_result.quantity) if risk_result.approved else 0.0
                if trade_qty <= 0:
                    rejected_for_risk += 1
            else:
                trade_qty = quantity
                if trade_qty % instrument_lot_size != 0:
                    raise ValueError("Fixed-size quantity must be a multiple of instrument_lot_size.")

            if trade_qty > 0:
                entry_fee = compute_fees("BUY", buy_price, trade_qty)
                is_future = instrument_type == "FUTURES"
                required_margin = buy_price * trade_qty * (initial_margin_pct / 100.0) if is_future else buy_price * trade_qty
                cost = required_margin + entry_fee
                if cash >= cost:
                    cash -= cost
                    if is_future:
                        blocked_margin += required_margin
                    position = trade_qty
                    entry_price = buy_price
                    entry_index = index + 1
                    accumulated_fees += entry_fee
                    if stop_loss_pct:
                        active_stop = buy_price * (1.0 - stop_loss_pct / 100.0)
                    if target_pct:
                        active_target = buy_price * (1.0 + target_pct / 100.0)
                else:
                    rejected_for_risk += 1

        elif action == -1 and position > 0:
            sell_price = next_open - slippage_per_side
            exit_fee = compute_fees("SELL", sell_price, position)
            entry_fee = compute_fees("BUY", entry_price, position)
            gross_pnl = (sell_price - entry_price) * position
            if instrument_type == "FUTURES":
                cash += blocked_margin + gross_pnl - exit_fee
                blocked_margin = 0.0
            else:
                cash += sell_price * position - exit_fee
            pnl = gross_pnl - entry_fee - exit_fee
            accumulated_fees += exit_fee
            record_closed_trade(pnl)
            trades += 1
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            else:
                breakevens += 1
            trade_log.append({
                "trade_num": trades, "entry_index": entry_index,
                "exit_index": index + 1, "entry_price": round(entry_price, 2),
                "exit_price": round(sell_price, 2), "quantity": position,
                "pnl": round(pnl, 2),
                "return_pct": round(pnl / (entry_price * position) * 100, 2),
                "exit_reason": "SIGNAL_EXIT",
            })
            position = entry_price = active_stop = active_target = 0.0

        equity = mark_equity(next_close)
        equity_curve.append(equity)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100)

    if position > 0:
        final_sell = candles[-1]["close"] - slippage_per_side
        exit_fee = compute_fees("SELL", final_sell, position)
        entry_fee = compute_fees("BUY", entry_price, position)
        gross_pnl = (final_sell - entry_price) * position
        if instrument_type == "FUTURES":
            cash += blocked_margin + gross_pnl - exit_fee
            blocked_margin = 0.0
        else:
            cash += final_sell * position - exit_fee
        pnl = gross_pnl - entry_fee - exit_fee
        accumulated_fees += exit_fee
        record_closed_trade(pnl)
        trades += 1
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        else:
            breakevens += 1
        trade_log.append({
            "trade_num": trades, "entry_index": entry_index,
            "exit_index": len(candles) - 1, "entry_price": round(entry_price, 2),
            "exit_price": round(final_sell, 2), "quantity": position,
            "pnl": round(pnl, 2),
            "return_pct": round(pnl / (entry_price * position) * 100, 2),
            "exit_reason": "FINAL_CLOSE",
        })
        position = 0.0

    final_equity = cash + blocked_margin
    equity_curve[-1] = final_equity
    peak_equity = max(peak_equity, final_equity)
    if peak_equity > 0:
        max_drawdown = max(max_drawdown, (peak_equity - final_equity) / peak_equity * 100)

    gross_profit = sum(p for p in trade_pnls if p > 0)
    gross_loss = -sum(p for p in trade_pnls if p < 0)
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
    expectancy = (sum(trade_pnls) / len(trade_pnls)) if trade_pnls else 0.0
    net_profit = cash - starting_capital
    return_percent = (net_profit / starting_capital) * 100

    start_bar_idx = min(warmup_bars, len(candles) - 1)
    benchmark_start = candles[start_bar_idx]["open"]
    benchmark_end = candles[-1]["close"]
    benchmark_return = ((benchmark_end - benchmark_start) / benchmark_start) * 100
    alpha = return_percent - benchmark_return

    sharpe_ratio = sortino_ratio = calmar_ratio = None
    active_equity = equity_curve[warmup_bars:] if warmup_bars < len(equity_curve) else equity_curve
    if len(active_equity) > 2:
        bar_returns = [
            (active_equity[i] - active_equity[i - 1]) / active_equity[i - 1]
            for i in range(1, len(active_equity)) if active_equity[i - 1] > 0
        ]
        if bar_returns:
            mean_ret = sum(bar_returns) / len(bar_returns)
            variance = sum((r - mean_ret) ** 2 for r in bar_returns) / len(bar_returns)
            std_dev = math.sqrt(variance)
            if std_dev > 1e-8:
                sharpe_ratio = round(math.sqrt(annualization_periods) * (mean_ret / std_dev), 4)
            downside_sq = [min(0.0, r) ** 2 for r in bar_returns]
            downside_dev = math.sqrt(sum(downside_sq) / len(downside_sq))
            if downside_dev > 1e-8:
                sortino_ratio = round(math.sqrt(annualization_periods) * (mean_ret / downside_dev), 4)
    if max_drawdown > 1e-6:
        calmar_ratio = round(return_percent / max_drawdown, 4)

    return BacktestResult(
        starting_capital=starting_capital,
        ending_capital=cash,
        total_trades=trades,
        winning_trades=wins,
        losing_trades=losses,
        win_rate_percent=(wins / trades * 100) if trades else 0.0,
        net_profit=net_profit,
        return_percent=return_percent,
        max_drawdown_percent=max_drawdown,
        profit_factor=profit_factor,
        expectancy=expectancy,
        breakeven_trades=breakevens,
        total_fees=accumulated_fees,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        calmar_ratio=calmar_ratio,
        benchmark_return_percent=round(benchmark_return, 2),
        alpha_percent=round(alpha, 2),
        intrabar_stops_hit=intrabar_stops,
        intrabar_targets_hit=intrabar_targets,
        sizing_mode=sizing_mode,
        instrument_type=instrument_type,
        rejected_for_risk_count=rejected_for_risk,
        equity_curve=equity_curve,
        trade_log=trade_log,
    )
