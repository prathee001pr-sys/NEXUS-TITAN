"""Modular trading strategy implementations for NEXUS-TITAN research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from nexus_titan.research.indicators import (
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
)


class Strategy(Protocol):
    """Protocol for all NEXUS-TITAN research strategies."""

    name: str

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        """Return 1 for BUY, -1 for SELL, 0 for HOLD at given candle index."""
        ...


@dataclass(frozen=True)
class SMACrossoverStrategy:
    """Simple Moving Average Crossover Strategy."""

    fast_period: int = 5
    slow_period: int = 20
    name: str = "SMA Crossover"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index < self.slow_period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        fast = sma(closes, self.fast_period)
        slow = sma(closes, self.slow_period)

        curr_fast, prev_fast = fast[-1], fast[-2]
        curr_slow, prev_slow = slow[-1], slow[-2]

        if None in (curr_fast, prev_fast, curr_slow, prev_slow):
            return 0

        # Bullish Crossover: Fast crosses above Slow
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return 1
        # Bearish Crossover: Fast crosses below Slow
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return -1
        return 0


@dataclass(frozen=True)
class EMACrossoverStrategy:
    """Exponential Moving Average Crossover Strategy."""

    fast_period: int = 9
    slow_period: int = 21
    name: str = "EMA Crossover"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index < self.slow_period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        fast = ema(closes, self.fast_period)
        slow = ema(closes, self.slow_period)

        curr_fast, prev_fast = fast[-1], fast[-2]
        curr_slow, prev_slow = slow[-1], slow[-2]

        if None in (curr_fast, prev_fast, curr_slow, prev_slow):
            return 0

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return 1
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return -1
        return 0


@dataclass(frozen=True)
class RSIMeanReversionStrategy:
    """RSI Mean-Reversion Strategy: Buy when crossing above oversold, exit when above overbought."""

    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    name: str = "RSI Mean Reversion"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index <= self.period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        rsi_values = rsi(closes, self.period)

        curr_rsi = rsi_values[-1]
        prev_rsi = rsi_values[-2]

        if curr_rsi is None or prev_rsi is None:
            return 0

        # Crossed back above oversold -> Buy signal
        if prev_rsi <= self.oversold and curr_rsi > self.oversold:
            return 1
        # Crossed above overbought -> Sell / Take profit signal
        if prev_rsi < self.overbought and curr_rsi >= self.overbought:
            return -1
        return 0


@dataclass(frozen=True)
class RSIMomentumStrategy:
    """RSI Midline Momentum Strategy: Buy when crossing above 50, exit when falling below 50."""

    period: int = 14
    midline: float = 50.0
    name: str = "RSI Momentum"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index <= self.period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        rsi_values = rsi(closes, self.period)

        curr_rsi = rsi_values[-1]
        prev_rsi = rsi_values[-2]

        if curr_rsi is None or prev_rsi is None:
            return 0

        # Bullish momentum cross: RSI crosses above 50
        if prev_rsi <= self.midline and curr_rsi > self.midline:
            return 1
        # Bearish momentum cross: RSI falls below 50
        if prev_rsi >= self.midline and curr_rsi < self.midline:
            return -1
        return 0


@dataclass(frozen=True)
class MACDTrendStrategy:
    """MACD Line vs Signal Line crossover strategy."""

    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    name: str = "MACD Trend"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index < self.slow_period + self.signal_period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        macd_line, sig_line, _ = macd(
            closes, self.fast_period, self.slow_period, self.signal_period
        )

        curr_m, prev_m = macd_line[-1], macd_line[-2]
        curr_s, prev_s = sig_line[-1], sig_line[-2]

        if None in (curr_m, prev_m, curr_s, prev_s):
            return 0

        # MACD crosses above Signal line -> Buy
        if prev_m <= prev_s and curr_m > curr_s:
            return 1
        # MACD crosses below Signal line -> Sell
        if prev_m >= prev_s and curr_m < curr_s:
            return -1
        return 0


@dataclass(frozen=True)
class BollingerBreakoutStrategy:
    """Bollinger Bands Breakout Strategy."""

    period: int = 20
    num_std: float = 2.0
    name: str = "Bollinger Breakout"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index < self.period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        upper, middle, lower = bollinger_bands(closes, self.period, self.num_std)

        curr_close = closes[-1]
        prev_close = closes[-2]
        curr_upper = upper[-1]
        curr_middle = middle[-1]

        if None in (curr_upper, curr_middle):
            return 0

        # Close breaks above upper band -> Long breakout
        if prev_close <= upper[-2] and curr_close > curr_upper:
            return 1
        # Close falls below middle band (20 SMA) -> Exit
        if curr_close < curr_middle:
            return -1
        return 0


AVAILABLE_STRATEGIES: dict[str, Callable[[], Strategy]] = {
    "sma": lambda: SMACrossoverStrategy(),
    "ema": lambda: EMACrossoverStrategy(),
    "rsi": lambda: RSIMeanReversionStrategy(),
    "rsi_momentum": lambda: RSIMomentumStrategy(),
    "macd": lambda: MACDTrendStrategy(),
    "bollinger": lambda: BollingerBreakoutStrategy(),
}
