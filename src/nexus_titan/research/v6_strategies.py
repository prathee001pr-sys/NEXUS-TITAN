"""Modular Phase 6 strategy catalogue, kept separate from the V2 baseline strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from nexus_titan.research.indicators import bollinger_bands, ema, macd, rsi, sma


class Strategy(Protocol):
    name: str

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        """Return 1 for BUY, -1 for SELL, 0 for HOLD at given candle index."""
        ...


@dataclass(frozen=True)
class SMACrossoverStrategy:
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
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return 1
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return -1
        return 0


@dataclass(frozen=True)
class EMACrossoverStrategy:
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
    period: int = 14
    oversold: float = 30.0
    overbought: float = 70.0
    name: str = "RSI Mean Reversion"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index <= self.period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        values = rsi(closes, self.period)
        current, previous = values[-1], values[-2]
        if current is None or previous is None:
            return 0
        if previous <= self.oversold and current > self.oversold:
            return 1
        if previous < self.overbought and current >= self.overbought:
            return -1
        return 0


@dataclass(frozen=True)
class RSIMomentumStrategy:
    period: int = 14
    midline: float = 50.0
    name: str = "RSI Momentum"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index <= self.period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        values = rsi(closes, self.period)
        current, previous = values[-1], values[-2]
        if current is None or previous is None:
            return 0
        if previous <= self.midline and current > self.midline:
            return 1
        if previous >= self.midline and current < self.midline:
            return -1
        return 0


@dataclass(frozen=True)
class MACDTrendStrategy:
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    name: str = "MACD Trend"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index < self.slow_period + self.signal_period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        macd_line, signal_line, _ = macd(
            closes, self.fast_period, self.slow_period, self.signal_period
        )
        current_macd, previous_macd = macd_line[-1], macd_line[-2]
        current_signal, previous_signal = signal_line[-1], signal_line[-2]
        if None in (current_macd, previous_macd, current_signal, previous_signal):
            return 0
        if previous_macd <= previous_signal and current_macd > current_signal:
            return 1
        if previous_macd >= previous_signal and current_macd < current_signal:
            return -1
        return 0


@dataclass(frozen=True)
class BollingerBreakoutStrategy:
    period: int = 20
    num_std: float = 2.0
    name: str = "Bollinger Breakout"

    def get_signal(self, index: int, candles: list[dict[str, float]]) -> int:
        if index < self.period:
            return 0
        closes = [c["close"] for c in candles[: index + 1]]
        upper, middle, _ = bollinger_bands(closes, self.period, self.num_std)
        current_close, previous_close = closes[-1], closes[-2]
        current_upper, current_middle = upper[-1], middle[-1]
        if current_upper is None or current_middle is None:
            return 0
        if previous_close <= upper[-2] and current_close > current_upper:
            return 1
        if current_close < current_middle:
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
