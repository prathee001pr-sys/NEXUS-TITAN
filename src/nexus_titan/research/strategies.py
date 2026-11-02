"""Reference strategies for the historical research engine.

These strategies are deterministic and use only the candle history supplied
by the backtest engine. They do not connect to brokers or place orders.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from nexus_titan.data.ohlcv import OHLCVCandle
from nexus_titan.research.backtest_engine import Signal


class MovingAverageCrossover:
    """Long when the fast SMA is above the slow SMA; otherwise stay flat.

    A signal is produced only after ``slow_period`` completed candles exist.
    The backtest engine executes the returned target position at the next
    candle open, not at the close used to calculate the averages.
    """

    def __init__(self, *, fast_period: int = 5, slow_period: int = 20) -> None:
        for name, value in (("fast_period", fast_period), ("slow_period", slow_period)):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if fast_period >= slow_period:
            raise ValueError("fast_period must be smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def on_candle(self, history: Sequence[OHLCVCandle]) -> Signal:
        """Return the target position using no data beyond ``history``."""
        if len(history) < self.slow_period:
            return Signal(0)

        fast_window = history[-self.fast_period :]
        slow_window = history[-self.slow_period :]
        fast_average = sum((candle.close for candle in fast_window), Decimal("0")) / self.fast_period
        slow_average = sum((candle.close for candle in slow_window), Decimal("0")) / self.slow_period
        return Signal(1 if fast_average > slow_average else 0)


# V6 & Phase 7 compatibility exports. The original V2 MovingAverageCrossover remains unchanged;
# these classes operate on the V6 dictionary-candle research interface.
from nexus_titan.research.v6_strategies import (
    ATRChannelTrendStrategy,
    AVAILABLE_STRATEGIES,
    BollingerBreakoutStrategy,
    EMACrossoverStrategy,
    MACDTrendStrategy,
    RegimeAdaptiveCompositeStrategy,
    RSIMeanReversionStrategy,
    RSIMomentumStrategy,
    SMACrossoverStrategy,
)

__all__ = [
    "MovingAverageCrossover",
    "AVAILABLE_STRATEGIES",
    "SMACrossoverStrategy",
    "EMACrossoverStrategy",
    "RSIMeanReversionStrategy",
    "RSIMomentumStrategy",
    "MACDTrendStrategy",
    "BollingerBreakoutStrategy",
    "ATRChannelTrendStrategy",
    "RegimeAdaptiveCompositeStrategy",
]
