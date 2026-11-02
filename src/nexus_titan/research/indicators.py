"""Pure standard-library technical indicators for NEXUS-TITAN research."""

from __future__ import annotations

import math


def sma(series: list[float], period: int) -> list[float | None]:
    """Calculate Simple Moving Average."""
    if period < 1 or not isinstance(period, int):
        raise ValueError("Period must be a positive integer.")
    result: list[float | None] = [None] * len(series)
    if len(series) < period:
        return result

    running_sum = sum(series[:period])
    result[period - 1] = running_sum / period
    for i in range(period, len(series)):
        running_sum += series[i] - series[i - period]
        result[i] = running_sum / period
    return result


def ema(series: list[float], period: int) -> list[float | None]:
    """Calculate Exponential Moving Average using standard 2 / (period + 1) multiplier."""
    if period < 1 or not isinstance(period, int):
        raise ValueError("Period must be a positive integer.")
    result: list[float | None] = [None] * len(series)
    if len(series) < period:
        return result

    multiplier = 2.0 / (period + 1.0)
    # Seed with SMA of the first `period` elements
    initial_sma = sum(series[:period]) / period
    result[period - 1] = initial_sma

    prev_ema = initial_sma
    for i in range(period, len(series)):
        current_ema = (series[i] - prev_ema) * multiplier + prev_ema
        result[i] = current_ema
        prev_ema = current_ema
    return result


def rsi(series: list[float], period: int = 14) -> list[float | None]:
    """Calculate Relative Strength Index using Wilder's smoothed moving average."""
    if period < 1 or not isinstance(period, int):
        raise ValueError("Period must be a positive integer.")
    result: list[float | None] = [None] * len(series)
    if len(series) <= period:
        return result

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(series)):
        change = series[i] - series[i - 1]
        gains.append(max(0.0, change))
        losses.append(max(0.0, -change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0.0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0.0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return result


def macd(
    series: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Calculate MACD Line, Signal Line, and Histogram."""
    if fast_period >= slow_period:
        raise ValueError("fast_period must be strictly less than slow_period.")

    fast_ema = ema(series, fast_period)
    slow_ema = ema(series, slow_period)

    macd_line: list[float | None] = [None] * len(series)
    for i in range(len(series)):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i]

    # Calculate Signal line as EMA of MACD line (skipping initial None values)
    valid_macd_indices = [i for i, v in enumerate(macd_line) if v is not None]
    signal_line: list[float | None] = [None] * len(series)
    histogram: list[float | None] = [None] * len(series)

    if len(valid_macd_indices) >= signal_period:
        valid_macd_values = [macd_line[i] for i in valid_macd_indices]
        valid_signal_values = ema(valid_macd_values, signal_period)

        for original_idx, sig_val in zip(valid_macd_indices, valid_signal_values):
            signal_line[original_idx] = sig_val
            if sig_val is not None and macd_line[original_idx] is not None:
                histogram[original_idx] = macd_line[original_idx] - sig_val

    return macd_line, signal_line, histogram


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> list[float | None]:
    """Calculate Average True Range (ATR) with Wilder's smoothing."""
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("High, Low, and Close series must have equal length.")
    if period < 1 or not isinstance(period, int):
        raise ValueError("Period must be a positive integer.")

    result: list[float | None] = [None] * n
    if n < period + 1:
        return result

    # True range calculation
    tr: list[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr_val = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr.append(tr_val)

    # Initial ATR is simple average of first period
    initial_atr = sum(tr[:period]) / period
    result[period - 1] = initial_atr

    current_atr = initial_atr
    for i in range(period, n):
        current_atr = (current_atr * (period - 1) + tr[i]) / period
        result[i] = current_atr

    return result


def bollinger_bands(
    series: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Calculate Upper, Middle (SMA), and Lower Bollinger Bands."""
    if period < 1 or not isinstance(period, int):
        raise ValueError("Period must be a positive integer.")
    n = len(series)
    upper: list[float | None] = [None] * n
    middle: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n

    if n < period:
        return upper, middle, lower

    middle_sma = sma(series, period)

    for i in range(period - 1, n):
        window = series[i - period + 1 : i + 1]
        mean = middle_sma[i]
        assert mean is not None
        variance = sum((x - mean) ** 2 for x in window) / period
        std_dev = math.sqrt(variance)

        middle[i] = mean
        upper[i] = mean + num_std * std_dev
        lower[i] = mean - num_std * std_dev

    return upper, middle, lower
