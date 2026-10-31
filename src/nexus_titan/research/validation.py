"""Chronological data splitting and isolated out-of-sample evaluation."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Sequence

from nexus_titan.data.ohlcv import OHLCVCandle
from nexus_titan.research.backtest_engine import BacktestEngine, BacktestResult, Strategy


@dataclass(frozen=True, slots=True)
class ChronologicalSplit:
    """Non-overlapping chronological in-sample and out-of-sample candles."""

    in_sample: tuple[OHLCVCandle, ...]
    out_of_sample: tuple[OHLCVCandle, ...]


def split_chronologically(
    candles: Sequence[OHLCVCandle],
    *,
    in_sample_fraction: Decimal | float | str = Decimal("0.7"),
) -> ChronologicalSplit:
    """Split oldest candles into in-sample and newest candles into evaluation.

    Each partition contains at least two candles. All candles must belong to
    one symbol/timeframe and be strictly chronological.
    """
    try:
        fraction = Decimal(str(in_sample_fraction))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("in_sample_fraction must be a number between 0 and 1") from exc
    if not fraction.is_finite() or not Decimal("0") < fraction < Decimal("1"):
        raise ValueError("in_sample_fraction must be greater than 0 and less than 1")

    ordered = tuple(candles)
    if len(ordered) < 4:
        raise ValueError("at least four candles are required for a two-part split")
    if not all(isinstance(candle, OHLCVCandle) for candle in ordered):
        raise TypeError("all candles must be OHLCVCandle objects")

    symbol, timeframe = ordered[0].symbol, ordered[0].timeframe
    previous = None
    for candle in ordered:
        if candle.symbol != symbol or candle.timeframe != timeframe:
            raise ValueError("split candles must share symbol and timeframe")
        if previous is not None and candle.timestamp <= previous:
            raise ValueError("split candles must be strictly increasing with no duplicates")
        previous = candle.timestamp

    split_index = int(Decimal(len(ordered)) * fraction)
    if split_index < 2 or len(ordered) - split_index < 2:
        raise ValueError("fraction must leave at least two candles in each partition")
    return ChronologicalSplit(ordered[:split_index], ordered[split_index:])


def evaluate_out_of_sample(
    engine: BacktestEngine,
    strategy: Strategy,
    split: ChronologicalSplit,
) -> BacktestResult:
    """Evaluate only the holdout period while retaining training history.

    Signals are first requested from the final in-sample candle and are filled
    at the first out-of-sample candle open. No trade is opened during the
    in-sample period; the returned metrics cover the holdout period only.
    """
    if not isinstance(split, ChronologicalSplit):
        raise TypeError("split must be a ChronologicalSplit")
    combined = split.in_sample + split.out_of_sample
    return engine.run(combined, strategy, start_index=len(split.in_sample) - 1)
