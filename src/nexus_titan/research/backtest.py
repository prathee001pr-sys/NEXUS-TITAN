"""Production-grade historical backtesting engine with instrument-aware costs, safe lot sizing, intrabar stops, short-selling, and turnover/exposure telemetry."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Literal

from nexus_titan.cost.charges import InstrumentType, calculate_indian_trade_costs
from nexus_titan.data.canonical import load_canonical_data
from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig


class _CandleHistoryView(Sequence[Mapping[str, object]]):
    """Read-only candle prefix; a strategy cannot inspect future bars via its input."""

    def __init__(self, bars: tuple[Mapping[str, object], ...], visible_count: int) -> None:
        self._bars = bars
        self._visible_count = max(0, min(int(visible_count), len(bars)))

    def __len__(self) -> int:
        return self._visible_count

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(self._visible_count)
            return [self._bars[i] for i in range(start, stop, step)]
        if isinstance(index, bool) or not isinstance(index, int):
            raise TypeError("Candle history indices must be integers or slices.")
        if index < 0:
            index += self._visible_count
        if index < 0 or index >= self._visible_count:
            raise IndexError("Strategy requested a candle outside its visible history.")
        return self._bars[index]


@dataclass(frozen=True)
class BacktestResult:
    """Comprehensive performance and risk scorecard (Workstream B / Section 8.2)."""

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
    total_turnover: float = 0.0
    average_exposure_percent: float = 0.0
    fill_ratio_percent: float = 100.0
    short_trades: int = 0


def compute_file_sha256(path: str | Path) -> str:
    """Return the full 64-character SHA-256 digest using bounded memory.

    Keep the dashboard fingerprint consistent with the canonical dataset
    provenance manifest. A 16-character prefix is not the manifest digest.
    """
    file_path = Path(path)
    if not file_path.is_file():
        return "UNKNOWN"
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    candles: Sequence[Mapping[str, object]],
    starting_capital: float = 50_000.0,
    quantity: float = 1.0,
    fee_per_side: float = 0.0,
    slippage_per_side: float = 0.0,
    signal: Callable[[int, Sequence[Mapping[str, object]]], int] | None = None,
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
    allow_short: bool = False,
    spread_bps: float = 0.0,
) -> BacktestResult:
    """Run an event-driven historical backtest with costs, portfolio risk checks, and optional short-selling."""
    numeric_inputs = (starting_capital, quantity, fee_per_side, slippage_per_side, spread_bps)
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
        raise ValueError("Capital, quantity, fees, slippage, and spread_bps must be finite numbers.")
    if starting_capital <= 0 or quantity <= 0:
        raise ValueError("Capital and quantity must be positive.")
    if not float(quantity).is_integer():
        raise ValueError("quantity must be a whole number of units; fractional contract fills are not supported.")
    if fee_per_side < 0 or slippage_per_side < 0 or spread_bps < 0:
        raise ValueError("Costs cannot be negative.")
    if (isinstance(annualization_periods, bool) or not isinstance(annualization_periods, int)
            or annualization_periods < 1):
        raise ValueError("annualization_periods must be a positive integer.")
    if not isinstance(candles, (list, tuple)) or len(candles) < 2:
        raise ValueError("At least two candles are required.")
    if (isinstance(warmup_bars, bool) or not isinstance(warmup_bars, int)
            or not 0 <= warmup_bars < len(candles)):
        raise ValueError("warmup_bars must be an integer from 0 through len(candles)-1.")
    for name, value in (("stop_loss_pct", stop_loss_pct), ("target_pct", target_pct)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or value <= 0 or value >= 100):
            raise ValueError(f"{name} must be a finite percentage greater than 0 and less than 100.")
    if instrument_type not in ("EQUITY_DELIVERY", "EQUITY_INTRADAY", "FUTURES", "OPTIONS"):
        raise ValueError("Unsupported instrument_type.")
    if signal is not None and not callable(signal):
        raise ValueError("signal must be callable or None.")
    if isinstance(risk_per_trade_pct, bool) or not isinstance(risk_per_trade_pct, (int, float)) or not math.isfinite(risk_per_trade_pct) or not 0 < risk_per_trade_pct <= 100:
        raise ValueError("risk_per_trade_pct must be finite and between 0 and 100.")
    if isinstance(instrument_lot_size, bool) or not isinstance(instrument_lot_size, int) or instrument_lot_size < 1:
        raise ValueError("instrument_lot_size must be a positive integer.")
    if isinstance(initial_margin_pct, bool) or not isinstance(initial_margin_pct, (int, float)) or not math.isfinite(initial_margin_pct) or not 1 <= initial_margin_pct <= 100:
        raise ValueError("initial_margin_pct must be finite and between 1 and 100.")
    if sizing_mode not in ("fixed", "capital_risk"):
        raise ValueError("Unsupported sizing_mode.")
    required_bar_fields = ("open", "high", "low", "close", "volume")
    raw_timestamps: list[str] = []
    timestamp_presence: list[bool] = []
    for bar_index, bar in enumerate(candles):
        if not isinstance(bar, Mapping) or any(field_name not in bar for field_name in required_bar_fields):
            raise ValueError(f"Candle {bar_index} must be a mapping containing OHLCV fields.")
        values = [bar[field_name] for field_name in required_bar_fields]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            raise ValueError(f"Candle {bar_index} contains non-finite or non-numeric OHLCV values.")
        o, h, low, close, volume = (float(v) for v in values)
        if min(o, h, low, close) <= 0 or volume < 0:
            raise ValueError(f"Candle {bar_index} has non-positive price or negative volume.")
        if h < max(o, low, close) or low > min(o, h, close):
            raise ValueError(f"Candle {bar_index} has impossible OHLC bounds.")
        raw_timestamp = bar.get("timestamp")
        timestamp_presence.append(raw_timestamp is not None)
        if raw_timestamp is not None:
            raw_timestamps.append(str(raw_timestamp).strip())
    if any(timestamp_presence) and not all(timestamp_presence):
        raise ValueError("Either every candle must have a timestamp or none may have one.")
    if raw_timestamps:
        numeric_labels = [value.isdigit() for value in raw_timestamps]
        if all(numeric_labels):
            # Preserve the original test/API convention that uses strictly
            # increasing integer sequence labels instead of calendar timestamps.
            numeric_times = [int(value) for value in raw_timestamps]
            if any(b <= a for a, b in zip(numeric_times, numeric_times[1:])):
                raise ValueError("Numeric candle timestamp labels must be strictly increasing and unique.")
        elif any(numeric_labels):
            raise ValueError("Candle timestamps cannot mix numeric sequence labels and ISO-8601 dates.")
        else:
            from datetime import datetime
            parsed_timestamps = []
            for bar_index, raw_timestamp in enumerate(raw_timestamps):
                try:
                    parsed_timestamps.append(datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00")))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Candle {bar_index} has an invalid ISO-8601 timestamp.") from exc
            for idx in range(1, len(parsed_timestamps)):
                try:
                    if parsed_timestamps[idx] <= parsed_timestamps[idx - 1]:
                        raise ValueError("Candles must have strictly increasing, non-duplicate timestamps.")
                except TypeError as exc:
                    raise ValueError("Candle timestamps must use a consistent timezone convention.") from exc
    # Snapshot the caller data and give strategies a read-only prefix on each bar.
    # This prevents accidental mutation and ordinary look-ahead access through
    # the supplied strategy argument without copying the whole prefix per candle.
    candles = tuple(MappingProxyType(dict(bar)) for bar in candles)

    if allow_short and instrument_type == "EQUITY_DELIVERY":
        raise ValueError("Short selling is not permitted in EQUITY_DELIVERY; use FUTURES or EQUITY_INTRADAY.")
    if allow_short and instrument_type == "OPTIONS":
        raise ValueError("Short options are disabled until an exchange-calibrated portfolio SPAN/ELM margin model is supplied.")
    if sizing_mode == "capital_risk" and stop_loss_pct is None:
        raise ValueError("capital_risk sizing requires an explicit stop_loss_pct; a notional guess is not a protective stop.")

    def compute_fees(side: str, price: float, qty: float) -> float:
        if use_indian_statutory_costs:
            breakdown = calculate_indian_trade_costs(side, price, int(qty), instrument_type)  # type: ignore[arg-type]
            return breakdown.total_charges
        return fee_per_side

    def effective_slippage(raw_price: float) -> float:
        half_spread = raw_price * (spread_bps / 20_000.0) if spread_bps > 0 else 0.0
        return slippage_per_side + half_spread

    cash = starting_capital
    blocked_margin = 0.0
    position = 0.0
    position_side = 0  # +1 for LONG, -1 for SHORT, 0 for FLAT
    entry_price = 0.0
    entry_index = 0
    active_stop = 0.0
    active_target = 0.0

    wins = losses = breakevens = trades = short_trades_count = 0
    accumulated_fees = 0.0
    total_turnover = 0.0
    exposure_ratios: list[float] = []
    entry_attempts = 0
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

    def is_margin_product() -> bool:
        return instrument_type == "FUTURES" or position_side == -1

    def mark_equity(mark_price: float) -> float:
        if position == 0:
            return cash
        if is_margin_product():
            unrealized = (mark_price - entry_price) * position * position_side
            return cash + blocked_margin + unrealized
        return cash + position * mark_price

    def close_active_position(fill_price: float, exit_idx: int, reason: str) -> None:
        nonlocal cash, blocked_margin, position, position_side, entry_price, active_stop, active_target
        nonlocal wins, losses, breakevens, trades, accumulated_fees, total_turnover, daily_pnl
        exit_side_str = "SELL" if position_side == 1 else "BUY"
        entry_side_str = "BUY" if position_side == 1 else "SELL"
        exit_fee = compute_fees(exit_side_str, fill_price, position)
        entry_fee = compute_fees(entry_side_str, entry_price, position)
        gross_pnl = (fill_price - entry_price) * position * position_side
        if is_margin_product():
            cash += blocked_margin + gross_pnl - exit_fee
            blocked_margin = 0.0
        else:
            cash += fill_price * position - exit_fee
        pnl = gross_pnl - entry_fee - exit_fee
        accumulated_fees += exit_fee
        total_turnover += fill_price * position
        trade_pnls.append(pnl)
        daily_pnl += pnl
        trades += 1
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        else:
            breakevens += 1
        trade_log.append({
            "trade_num": trades,
            "side": "LONG" if position_side == 1 else "SHORT",
            "entry_index": entry_index,
            "exit_index": exit_idx,
            "entry_price": round(entry_price, 2),
            "exit_price": round(fill_price, 2),
            "quantity": position,
            "pnl": round(pnl, 2),
            "return_pct": round(pnl / (entry_price * position) * 100, 2),
            "exit_reason": reason,
        })
        position = entry_price = active_stop = active_target = 0.0
        position_side = 0

    for index in range(len(candles) - 1):
        next_candle = candles[index + 1]
        next_open = next_candle["open"]
        next_high = next_candle["high"]
        next_low = next_candle["low"]
        next_close = next_candle["close"]
        day_key = str(next_candle.get("date", next_candle.get("timestamp", index + 1)))[:10]
        new_session = day_key != current_day_key
        if new_session and current_day_key is not None and position > 0 and instrument_type == "EQUITY_INTRADAY":
            # Indian cash intraday positions must not be carried across sessions.
            session_exit_slip = effective_slippage(next_open)
            session_exit = next_open - session_exit_slip if position_side == 1 else next_open + session_exit_slip
            close_active_position(max(0.01, session_exit), index + 1, "INTRADAY_SESSION_END")
        if new_session:
            current_day_key = day_key
            daily_pnl = 0.0

        # Resolve ambiguous intrabar touches conservatively: stop-loss before target.
        if position > 0:
            exit_reason = None
            fill_price = 0.0
            if position_side == 1:
                if active_stop > 0:
                    if next_open <= active_stop:
                        exit_reason = "STOP_LOSS_GAP"
                        fill_price = next_open - effective_slippage(next_open)
                        intrabar_stops += 1
                    elif next_low <= active_stop:
                        exit_reason = "STOP_LOSS"
                        fill_price = active_stop - effective_slippage(active_stop)
                        intrabar_stops += 1
                if exit_reason is None and active_target > 0:
                    if next_open >= active_target:
                        exit_reason = "TARGET_GAP"
                        fill_price = next_open - effective_slippage(next_open)
                        intrabar_targets += 1
                    elif next_high >= active_target:
                        exit_reason = "TARGET"
                        fill_price = active_target - effective_slippage(active_target)
                        intrabar_targets += 1
            elif position_side == -1:
                if active_stop > 0:
                    if next_open >= active_stop:
                        exit_reason = "STOP_LOSS_GAP"
                        fill_price = next_open + effective_slippage(next_open)
                        intrabar_stops += 1
                    elif next_high >= active_stop:
                        exit_reason = "STOP_LOSS"
                        fill_price = active_stop + effective_slippage(active_stop)
                        intrabar_stops += 1
                if exit_reason is None and active_target > 0:
                    if next_open <= active_target:
                        exit_reason = "TARGET_GAP"
                        fill_price = next_open + effective_slippage(next_open)
                        intrabar_targets += 1
                    elif next_low <= active_target:
                        exit_reason = "TARGET"
                        fill_price = active_target + effective_slippage(active_target)
                        intrabar_targets += 1

            if exit_reason:
                close_active_position(fill_price, index + 1, exit_reason)

        if index < warmup_bars:
            eq = mark_equity(next_close)
            equity_curve.append(eq)
            exposure_ratios.append(0.0)
            continue

        action = signal(index, _CandleHistoryView(candles, index + 1)) if signal else 0
        if isinstance(action, bool) or action not in (-1, 0, 1):
            raise ValueError(f"Strategy signal at index {index} must be exactly -1, 0, or 1.")
        closed_on_signal = False

        # Signal exit when holding an opposite position
        if position > 0:
            if (position_side == 1 and action == -1) or (position_side == -1 and action == 1):
                slip = effective_slippage(next_open)
                exit_px = next_open - slip if position_side == 1 else next_open + slip
                close_active_position(exit_px, index + 1, "SIGNAL_EXIT")
                closed_on_signal = True

        # Entry check when flat (and did not just close on the same bar)
        if not closed_on_signal and position == 0 and (action == 1 or (action == -1 and allow_short)):
            entry_attempts += 1
            desired_side = 1 if action == 1 else -1
            side_str: Literal["BUY", "SELL"] = "BUY" if desired_side == 1 else "SELL"
            slip = effective_slippage(next_open)
            exec_entry = next_open + slip if desired_side == 1 else max(0.05, next_open - slip)

            if sizing_mode == "capital_risk":
                stop_dist = (exec_entry * (stop_loss_pct / 100.0)) if stop_loss_pct else (exec_entry * 0.02)
                indicative_stop = (
                    max(0.01, exec_entry - stop_dist) if desired_side == 1 else (exec_entry + stop_dist)
                )
                risk_result = risk_engine.size_and_validate(
                    capital=max(cash + blocked_margin, 1.0),
                    entry_price=exec_entry,
                    stop_price=indicative_stop,
                    symbol=instrument_symbol,
                    lot_size=instrument_lot_size,
                    current_exposure=0.0,
                    current_open_positions=0,
                    realized_daily_loss_pct=max(0.0, -daily_pnl / starting_capital * 100.0),
                    consecutive_losses=_trailing_losses(trade_pnls),
                    current_drawdown_pct=max(0.0, (peak_equity - mark_equity(next_close)) / peak_equity * 100.0),
                    slippage_buffer=slip,
                    side=side_str,
                )
                trade_qty = float(risk_result.quantity) if risk_result.approved else 0.0
                if trade_qty <= 0:
                    rejected_for_risk += 1
            else:
                trade_qty = quantity
                if trade_qty % instrument_lot_size != 0:
                    raise ValueError("Fixed-size quantity must be a multiple of instrument_lot_size.")

            if trade_qty > 0:
                if not float(trade_qty).is_integer() or int(trade_qty) % instrument_lot_size != 0:
                    raise ValueError("Calculated trade quantity must be a whole number and a multiple of instrument_lot_size.")
                entry_fee = compute_fees(side_str, exec_entry, trade_qty)
                use_margin = instrument_type == "FUTURES" or desired_side == -1
                required_margin = (
                    exec_entry * trade_qty * (initial_margin_pct / 100.0)
                    if use_margin
                    else exec_entry * trade_qty
                )
                cost = required_margin + entry_fee
                if cash >= cost:
                    cash -= cost
                    if use_margin:
                        blocked_margin += required_margin
                    position = trade_qty
                    position_side = desired_side
                    entry_price = exec_entry
                    entry_index = index + 1
                    accumulated_fees += entry_fee
                    total_turnover += exec_entry * trade_qty
                    if desired_side == -1:
                        short_trades_count += 1
                    if stop_loss_pct:
                        active_stop = (
                            exec_entry * (1.0 - stop_loss_pct / 100.0)
                            if desired_side == 1
                            else exec_entry * (1.0 + stop_loss_pct / 100.0)
                        )
                    if target_pct:
                        active_target = (
                            exec_entry * (1.0 + target_pct / 100.0)
                            if desired_side == 1
                            else exec_entry * (1.0 - target_pct / 100.0)
                        )
                else:
                    rejected_for_risk += 1

        equity = mark_equity(next_close)
        equity_curve.append(equity)
        exp_val = (position * next_close / equity * 100.0) if (position > 0 and equity > 0) else 0.0
        exposure_ratios.append(exp_val)
        peak_equity = max(peak_equity, equity)
        if peak_equity > 0:
            max_drawdown = max(max_drawdown, (peak_equity - equity) / peak_equity * 100)

    if position > 0:
        slip = effective_slippage(candles[-1]["close"])
        final_px = candles[-1]["close"] - slip if position_side == 1 else candles[-1]["close"] + slip
        close_active_position(final_px, len(candles) - 1, "FINAL_CLOSE")

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

    avg_exposure = round(sum(exposure_ratios) / len(exposure_ratios), 2) if exposure_ratios else 0.0
    accepted_entries = entry_attempts - rejected_for_risk
    fill_ratio = round((accepted_entries / entry_attempts) * 100.0, 2) if entry_attempts > 0 else 100.0

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
        total_turnover=round(total_turnover, 2),
        average_exposure_percent=avg_exposure,
        fill_ratio_percent=fill_ratio,
        short_trades=short_trades_count,
    )
