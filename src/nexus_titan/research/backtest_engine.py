"""Deterministic long-only historical backtesting with next-bar execution."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime
from typing import Protocol, Sequence

from nexus_titan.data.ohlcv import OHLCVCandle


@dataclass(frozen=True, slots=True)
class Signal:
    """Desired exposure after the current candle closes."""

    target_position: int

    def __post_init__(self) -> None:
        if self.target_position not in (0, 1):
            raise ValueError("target_position must be 0 (flat) or 1 (long)")


class Strategy(Protocol):
    def on_candle(self, history: Sequence[OHLCVCandle]) -> Signal:
        """Return a signal using only candles in history, ending at current bar."""
        ...


@dataclass(frozen=True, slots=True)
class ExecutionCostModel:
    """Configurable costs; rates are fractions (e.g. 0.001 means 0.1%)."""

    brokerage_per_order: Decimal = Decimal("0")
    stt_sell_rate: Decimal = Decimal("0")
    exchange_rate: Decimal = Decimal("0")
    gst_rate: Decimal = Decimal("0")
    stamp_buy_rate: Decimal = Decimal("0")
    slippage_bps: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        for name in (
            "brokerage_per_order", "stt_sell_rate", "exchange_rate",
            "gst_rate", "stamp_buy_rate", "slippage_bps",
        ):
            value = Decimal(str(getattr(self, name)))
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} must be a finite non-negative number")
            object.__setattr__(self, name, value)
        if self.slippage_bps >= Decimal("10000"):
            raise ValueError("slippage_bps must be below 10000")


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    entry_time: datetime
    exit_time: datetime
    quantity: int
    entry_price: Decimal
    exit_price: Decimal
    gross_pnl: Decimal
    charges: Decimal
    net_pnl: Decimal


@dataclass(frozen=True, slots=True)
class BacktestResult:
    symbol: str
    timeframe: str
    initial_capital: Decimal
    final_capital: Decimal
    net_pnl: Decimal
    total_return: Decimal
    trades: tuple[BacktestTrade, ...]
    win_rate: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal
    max_drawdown: Decimal


class BacktestEngine:
    """Single-symbol, long-only engine; signals fill at the next candle open."""

    def __init__(
        self,
        *,
        initial_capital: Decimal | int | str = Decimal("50000"),
        quantity: int = 1,
        costs: ExecutionCostModel | None = None,
    ) -> None:
        self.initial_capital = Decimal(str(initial_capital))
        if not self.initial_capital.is_finite() or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and greater than zero")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        self.quantity = quantity
        self.costs = costs or ExecutionCostModel()

    def _charges(self, *, price: Decimal, side: str, quantity: int) -> Decimal:
        turnover = price * quantity
        brokerage = self.costs.brokerage_per_order
        exchange = turnover * self.costs.exchange_rate
        gst = (brokerage + exchange) * self.costs.gst_rate
        stt = turnover * self.costs.stt_sell_rate if side == "sell" else Decimal("0")
        stamp = turnover * self.costs.stamp_buy_rate if side == "buy" else Decimal("0")
        return brokerage + exchange + gst + stt + stamp

    def run(
        self,
        candles: Sequence[OHLCVCandle],
        strategy: Strategy,
        *,
        start_index: int = 0,
    ) -> BacktestResult:
        """Run from a signal candle index; earlier candles are history only."""
        if len(candles) < 2:
            raise ValueError("at least two candles are required")
        if (
            not isinstance(start_index, int)
            or isinstance(start_index, bool)
            or start_index < 0
            or start_index >= len(candles) - 1
        ):
            raise ValueError("start_index must be an integer from 0 to len(candles) - 2")
        symbol, timeframe = candles[0].symbol, candles[0].timeframe
        previous = None
        for candle in candles:
            if not isinstance(candle, OHLCVCandle):
                raise TypeError("all candles must be OHLCVCandle objects")
            if candle.symbol != symbol or candle.timeframe != timeframe:
                raise ValueError("backtest candles must share symbol and timeframe")
            if previous is not None and candle.timestamp <= previous:
                raise ValueError("candles must be strictly increasing with no duplicates")
            previous = candle.timestamp

        capital = self.initial_capital
        position = None
        trades: list[BacktestTrade] = []
        equity_peak = capital
        max_drawdown = Decimal("0")

        for index in range(start_index, len(candles) - 1):
            history = candles[: index + 1]
            signal = strategy.on_candle(history)
            if not isinstance(signal, Signal):
                raise TypeError("strategy.on_candle must return Signal")
            fill_bar = candles[index + 1]
            if signal.target_position == 1 and position is None:
                raw = fill_bar.open
                fill = raw * (Decimal("1") + self.costs.slippage_bps / Decimal("10000"))
                buy_cost = self._charges(price=fill, side="buy", quantity=self.quantity)
                required = fill * self.quantity + buy_cost
                if required > capital:
                    raise ValueError("insufficient capital for requested position and costs")
                capital -= required
                position = (fill_bar.timestamp, fill, buy_cost)
            elif signal.target_position == 0 and position is not None:
                entry_time, entry_price, entry_cost = position
                raw = fill_bar.open
                fill = raw * (Decimal("1") - self.costs.slippage_bps / Decimal("10000"))
                sell_cost = self._charges(price=fill, side="sell", quantity=self.quantity)
                gross = (fill - entry_price) * self.quantity
                total_charges = entry_cost + sell_cost
                net = gross - total_charges
                capital += fill * self.quantity - sell_cost
                trades.append(BacktestTrade(
                    entry_time, fill_bar.timestamp, self.quantity, entry_price,
                    fill, gross, total_charges, net,
                ))
                position = None
                equity_peak = max(equity_peak, capital)
                if equity_peak > 0:
                    max_drawdown = max(max_drawdown, (equity_peak - capital) / equity_peak)

        if position is not None:
            entry_time, entry_price, entry_cost = position
            final_bar = candles[-1]
            fill = final_bar.close * (
                Decimal("1") - self.costs.slippage_bps / Decimal("10000")
            )
            sell_cost = self._charges(price=fill, side="sell", quantity=self.quantity)
            gross = (fill - entry_price) * self.quantity
            total_charges = entry_cost + sell_cost
            net = gross - total_charges
            capital += fill * self.quantity - sell_cost
            trades.append(BacktestTrade(
                entry_time, final_bar.timestamp, self.quantity, entry_price,
                fill, gross, total_charges, net,
            ))
            equity_peak = max(equity_peak, capital)
            if equity_peak > 0:
                max_drawdown = max(max_drawdown, (equity_peak - capital) / equity_peak)

        net_pnl = capital - self.initial_capital
        wins = sum(1 for trade in trades if trade.net_pnl > 0)
        gross_wins = sum((t.net_pnl for t in trades if t.net_pnl > 0), Decimal("0"))
        gross_losses = -sum((t.net_pnl for t in trades if t.net_pnl < 0), Decimal("0"))
        profit_factor = (
            gross_wins / gross_losses if gross_losses > 0
            else (None if gross_wins == 0 else Decimal("Infinity"))
        )
        expectancy = (
            sum((t.net_pnl for t in trades), Decimal("0")) / len(trades)
            if trades else Decimal("0")
        )
        return BacktestResult(
            symbol, timeframe, self.initial_capital, capital, net_pnl,
            net_pnl / self.initial_capital,
            tuple(trades),
            Decimal(wins) / len(trades) if trades else Decimal("0"),
            profit_factor, expectancy, max_drawdown,
        )
