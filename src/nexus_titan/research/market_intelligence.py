"""Deterministic, dependency-free market intelligence calculators.

These functions are research features, not trade recommendations. They require
point-in-time inputs and deliberately return unavailable values when history is
insufficient rather than manufacturing a signal.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, pstdev
from typing import Iterable, Sequence


@dataclass(frozen=True)
class RegimeSnapshot:
    trend: str
    volatility: str
    adx: float | None
    atr_pct: float | None
    reasons: tuple[str, ...]


def _finite_series(values: Sequence[float], name: str) -> None:
    if not values:
        raise ValueError(f"{name} cannot be empty.")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} values must be finite numbers.")


def validate_ohlcv(highs: Sequence[float], lows: Sequence[float], opens: Sequence[float],
                   closes: Sequence[float], volumes: Sequence[float]) -> None:
    """Validate aligned OHLCV arrays; does not validate exchange calendar/licensing."""
    arrays = (highs, lows, opens, closes, volumes)
    if not arrays[0] or any(len(a) != len(arrays[0]) for a in arrays):
        raise ValueError("OHLCV arrays must be non-empty and have equal lengths.")
    for name, values in zip(("highs", "lows", "opens", "closes", "volumes"), arrays):
        _finite_series(values, name)
    for i, (o, h, l, c, v) in enumerate(zip(opens, highs, lows, closes, volumes)):
        if min(o, h, l, c) <= 0 or v < 0:
            raise ValueError(f"OHLC prices must be positive and volume non-negative (row {i}).")
        if h < max(o, c, l) or l > min(o, c, h):
            raise ValueError(f"Invalid OHLC relationship at row {i}.")


def vwap(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float],
         volumes: Sequence[float]) -> list[float | None]:
    """Cumulative typical-price VWAP; caller must pass one session at a time."""
    if not (len(highs) == len(lows) == len(closes) == len(volumes)) or not closes:
        raise ValueError("VWAP inputs must be non-empty and aligned.")
    _finite_series(highs, "highs"); _finite_series(lows, "lows")
    _finite_series(closes, "closes"); _finite_series(volumes, "volumes")
    numerator = denominator = 0.0
    out: list[float | None] = []
    for h, l, c, vol in zip(highs, lows, closes, volumes):
        if min(h, l, c) <= 0 or vol < 0 or h < max(l, c):
            raise ValueError("Invalid price or volume in VWAP input.")
        numerator += ((h + l + c) / 3.0) * vol
        denominator += vol
        out.append(numerator / denominator if denominator > 0 else None)
    return out


def rate_of_change(closes: Sequence[float], period: int = 10) -> list[float | None]:
    if isinstance(period, bool) or not isinstance(period, int) or period < 1:
        raise ValueError("period must be a positive integer.")
    _finite_series(closes, "closes")
    if any(x <= 0 for x in closes): raise ValueError("closes must be positive.")
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        out[i] = (closes[i] / closes[i-period] - 1.0) * 100.0
    return out


def realized_volatility(closes: Sequence[float], period: int = 20, annualization: float = 1.0) -> list[float | None]:
    """Rolling population stdev of log returns, annualized by caller-supplied factor."""
    if isinstance(period, bool) or not isinstance(period, int) or period < 2:
        raise ValueError("period must be an integer >= 2.")
    if not math.isfinite(annualization) or annualization <= 0:
        raise ValueError("annualization must be positive and finite.")
    _finite_series(closes, "closes")
    if any(x <= 0 for x in closes): raise ValueError("closes must be positive.")
    returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        out[i] = pstdev(returns[i-period:i]) * math.sqrt(annualization)
    return out


def adx(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14) -> list[float | None]:
    """Wilder-style ADX. First usable values require sufficient warm-up history."""
    n = len(closes)
    if not (len(highs) == len(lows) == n) or period < 2:
        raise ValueError("Aligned OHLC arrays and period >= 2 are required.")
    _finite_series(highs, "highs"); _finite_series(lows, "lows"); _finite_series(closes, "closes")
    if any(l > h or min(l, c) <= 0 for h, l, c in zip(highs, lows, closes)):
        raise ValueError("Invalid high/low/close values.")
    tr = [0.0] * n; plus = [0.0] * n; minus = [0.0] * n
    for i in range(1, n):
        up, down = highs[i] - highs[i-1], lows[i-1] - lows[i]
        plus[i] = up if up > down and up > 0 else 0.0
        minus[i] = down if down > up and down > 0 else 0.0
        tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
    out: list[float | None] = [None] * n
    if n < 2 * period + 1: return out
    tr_s, p_s, m_s = sum(tr[1:period+1]), sum(plus[1:period+1]), sum(minus[1:period+1])
    dx: list[float | None] = [None] * n
    for i in range(period, n):
        if i > period:
            tr_s = tr_s - tr_s / period + tr[i]
            p_s = p_s - p_s / period + plus[i]
            m_s = m_s - m_s / period + minus[i]
        pdi = 100 * p_s / tr_s if tr_s else 0.0
        mdi = 100 * m_s / tr_s if tr_s else 0.0
        dx[i] = 100 * abs(pdi-mdi) / (pdi+mdi) if pdi+mdi else 0.0
    first = 2 * period - 1
    if first >= n: return out
    current = mean(x for x in dx[period:first+1] if x is not None)
    out[first] = current
    for i in range(first+1, n):
        current = ((current * (period-1)) + (dx[i] or 0.0)) / period
        out[i] = current
    return out


def opening_range(highs: Sequence[float], lows: Sequence[float], bars: int) -> tuple[float, float]:
    """High/low of first N bars of a caller-isolated trading session."""
    if isinstance(bars, bool) or not isinstance(bars, int) or bars < 1 or len(highs) < bars or len(lows) < bars:
        raise ValueError("bars must be positive and enough session bars must be supplied.")
    _finite_series(highs[:bars], "highs"); _finite_series(lows[:bars], "lows")
    if any(lows[i] > highs[i] for i in range(bars)):
        raise ValueError("Low cannot exceed high.")
    return max(highs[:bars]), min(lows[:bars])


def order_book_imbalance(bid_depth: Sequence[float], ask_depth: Sequence[float]) -> float:
    """Depth imbalance in [-1, 1]; positive means more displayed bid depth."""
    if not bid_depth or not ask_depth or len(bid_depth) != len(ask_depth):
        raise ValueError("Bid and ask depth must be non-empty and aligned.")
    _finite_series(bid_depth, "bid_depth"); _finite_series(ask_depth, "ask_depth")
    if any(x < 0 for x in (*bid_depth, *ask_depth)):
        raise ValueError("Depth cannot be negative.")
    bid, ask = sum(bid_depth), sum(ask_depth)
    return (bid-ask)/(bid+ask) if bid+ask else 0.0


def classify_regime(closes: Sequence[float], highs: Sequence[float], lows: Sequence[float],
                    *, adx_period: int = 14, trend_threshold: float = 25.0,
                    volatility_lookback: int = 20) -> RegimeSnapshot:
    """Simple transparent regime heuristic; thresholds require market-specific calibration."""
    if not (len(closes) == len(highs) == len(lows)) or len(closes) < max(2*adx_period+1, volatility_lookback+1):
        return RegimeSnapshot("UNKNOWN", "UNKNOWN", None, None, ("INSUFFICIENT_HISTORY",))
    _finite_series(closes, "closes")
    if any(x <= 0 for x in closes): raise ValueError("closes must be positive.")
    a = adx(highs, lows, closes, adx_period)[-1]
    true_ranges = [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])) for i in range(1, len(closes))]
    atr_value = mean(true_ranges[-adx_period:]) if true_ranges else None
    atr_pct = (atr_value / closes[-1] * 100.0) if atr_value is not None else None
    # Compare latest realized volatility with its own recent rolling median; no future data.
    rv = realized_volatility(closes, max(2, volatility_lookback), 1.0)
    vals = [x for x in rv[-min(len(rv), 60):] if x is not None]
    if len(vals) < 5:
        vol_state = "UNKNOWN"
    else:
        baseline = sorted(vals[:-1] or vals)[len(vals[:-1] or vals)//2]
        vol_state = "EXPANSION" if vals[-1] > baseline * 1.25 else "COMPRESSION" if vals[-1] < baseline * 0.75 else "NORMAL"
    trend = "TRENDING" if a is not None and a >= trend_threshold else "RANGING"
    return RegimeSnapshot(trend, vol_state, round(a, 4) if a is not None else None,
                          round(atr_pct, 4) if atr_pct is not None else None,
                          ("ADX_HEURISTIC", "VOLATILITY_RELATIVE_TO_RECENT_BASELINE"))

@dataclass(frozen=True)
class OpenInterestSummary:
    call_oi: int
    put_oi: int
    put_call_ratio: float | None
    call_oi_change: int | None
    put_oi_change: int | None


def summarize_open_interest(current_quotes: Iterable[object], previous_quotes: Iterable[object] | None = None) -> OpenInterestSummary:
    """Aggregate CE/PE OI and optional point-in-time OI change by contract identity."""
    current = list(current_quotes)
    if not current:
        raise ValueError("At least one current option quote is required.")
    def key(q: object) -> tuple[object, ...]:
        return (getattr(q, "underlying"), getattr(q, "expiry_date"), getattr(q, "strike"), getattr(q, "option_type"))
    def oi(q: object) -> int:
        value = getattr(q, "open_interest")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("open_interest must be a non-negative integer.")
        return value
    calls = sum(oi(q) for q in current if getattr(q, "option_type", None) == "CE")
    puts = sum(oi(q) for q in current if getattr(q, "option_type", None) == "PE")
    call_change = put_change = None
    if previous_quotes is not None:
        prev = {key(q): oi(q) for q in previous_quotes}
        if len(prev) == 0:
            raise ValueError("Previous option snapshot cannot be empty when supplied.")
        if len({key(q) for q in current}) != len(current):
            raise ValueError("Duplicate contract identity in current option snapshot.")
        call_change = sum(oi(q) - prev[key(q)] for q in current if getattr(q, "option_type", None) == "CE" and key(q) in prev)
        put_change = sum(oi(q) - prev[key(q)] for q in current if getattr(q, "option_type", None) == "PE" and key(q) in prev)
    return OpenInterestSummary(calls, puts, puts / calls if calls else None, call_change, put_change)


def calculate_iv_skew(iv_by_strike: dict[float, float], spot: float, wing_distance_pct: float = 5.0) -> float | None:
    """Put-wing minus call-wing IV, using nearest available strikes around spot +/- distance."""
    if not math.isfinite(spot) or spot <= 0 or not math.isfinite(wing_distance_pct) or wing_distance_pct <= 0:
        raise ValueError("spot and wing_distance_pct must be positive and finite.")
    if not iv_by_strike:
        return None
    for strike, iv in iv_by_strike.items():
        if not math.isfinite(strike) or strike <= 0 or not math.isfinite(iv) or iv <= 0:
            raise ValueError("Strike and IV values must be positive and finite.")
    put_target, call_target = spot * (1-wing_distance_pct/100), spot * (1+wing_distance_pct/100)
    put_strike = min(iv_by_strike, key=lambda x: abs(x-put_target))
    call_strike = min(iv_by_strike, key=lambda x: abs(x-call_target))
    if put_strike >= spot or call_strike <= spot:
        return None
    return iv_by_strike[put_strike] - iv_by_strike[call_strike]


def gamma_exposure(gamma: float, open_interest: int, lot_size: int, spot: float, *, call_put_sign: int = 1) -> float:
    """Signed notional gamma proxy; contract multiplier convention must be calibrated externally."""
    if not math.isfinite(gamma) or gamma < 0 or not math.isfinite(spot) or spot <= 0:
        raise ValueError("gamma must be non-negative and spot positive/finite.")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 0 for x in (open_interest,)) or isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size < 1:
        raise ValueError("open_interest must be non-negative integer and lot_size positive integer.")
    if call_put_sign not in (-1, 1):
        raise ValueError("call_put_sign must be -1 or 1.")
    return gamma * open_interest * lot_size * spot * spot * call_put_sign
