"""Basic rule-based trading signals for NEXUS TITAN research."""
from dataclasses import dataclass
from typing import Literal
import math

SignalType = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class Signal:
    action: SignalType
    reason: str
    fast_average: float | None = None
    slow_average: float | None = None


def generate_signal(closes: list[float], fast_period: int = 5, slow_period: int = 10) -> Signal:
    if (not isinstance(fast_period, int) or isinstance(fast_period, bool)
        or not isinstance(slow_period, int) or isinstance(slow_period, bool)):
        return Signal("HOLD", "Periods must be whole numbers.")
    if fast_period < 1 or slow_period < 1 or fast_period >= slow_period:
        return Signal("HOLD", "Periods must satisfy 1 <= fast_period < slow_period.")
    if not isinstance(closes, (list, tuple)):
        return Signal("HOLD", "Closing prices must be a list or tuple.")
    if len(closes) < slow_period:
        return Signal("HOLD", f"Need at least {slow_period} closing prices.")
    for price in closes:
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            return Signal("HOLD", "Prices must be finite positive numbers.")
    fast_average = sum(closes[-fast_period:]) / fast_period
    slow_average = sum(closes[-slow_period:]) / slow_period
    if fast_average > slow_average:
        return Signal("BUY", "Fast moving average is above slow moving average.", fast_average, slow_average)
    if fast_average < slow_average:
        return Signal("SELL", "Fast moving average is below slow moving average.", fast_average, slow_average)
    return Signal("HOLD", "Fast and slow moving averages are equal.", fast_average, slow_average)
