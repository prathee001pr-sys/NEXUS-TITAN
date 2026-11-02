"""Deterministic OHLCV stress scenarios; not an exchange-calibrated market model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Mapping
import math

@dataclass(frozen=True)
class StressScenario:
    name: str
    gap_pct: float = 0.0
    intrabar_shock_pct: float = 0.0
    volume_multiplier: float = 1.0
    spread_multiplier: float = 1.0

    def __post_init__(self):
        vals = (self.gap_pct, self.intrabar_shock_pct, self.volume_multiplier, self.spread_multiplier)
        if not self.name.strip() or any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in vals):
            raise ValueError("Scenario name and finite numeric parameters are required.")
        if self.gap_pct <= -100 or self.intrabar_shock_pct < 0 or self.volume_multiplier < 0 or self.spread_multiplier < 1:
            raise ValueError("Invalid stress parameters.")

SCENARIOS = (
    StressScenario("GAP_DOWN_3", gap_pct=-3.0, intrabar_shock_pct=1.0, volume_multiplier=1.5, spread_multiplier=2.0),
    StressScenario("GAP_UP_3", gap_pct=3.0, intrabar_shock_pct=1.0, volume_multiplier=1.5, spread_multiplier=2.0),
    StressScenario("VOLATILITY_SPIKE", intrabar_shock_pct=3.0, volume_multiplier=2.0, spread_multiplier=3.0),
    StressScenario("LIQUIDITY_DROUGHT", intrabar_shock_pct=1.0, volume_multiplier=0.2, spread_multiplier=5.0),
)

def apply_stress(candles: Iterable[Mapping[str, object]], scenario: StressScenario) -> list[dict]:
    """Return a copied, price-consistent OHLCV path. Never mutates source candles."""
    if not isinstance(scenario, StressScenario):
        raise TypeError("scenario must be a StressScenario")
    source = list(candles)
    out = []
    previous_close = None
    for i, raw in enumerate(source):
        bar = dict(raw)
        try:
            o,h,l,c,v = (float(bar[k]) for k in ("open","high","low","close","volume"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid OHLCV bar at index {i}") from exc
        if any(not math.isfinite(x) for x in (o,h,l,c,v)) or min(o,h,l,c) <= 0 or v < 0 or h < max(o,c,l) or l > min(o,c,h):
            raise ValueError(f"Invalid OHLCV values at index {i}")
        factor = 1.0
        if i == 0 and scenario.gap_pct:
            factor = 1.0 + scenario.gap_pct / 100.0
        elif i > 0 and scenario.gap_pct:
            factor = 1.0 + scenario.gap_pct / 100.0
        o,h,l,c = (x*factor for x in (o,h,l,c))
        shock = scenario.intrabar_shock_pct / 100.0
        h *= 1.0 + shock
        l *= 1.0 - shock
        bar.update(open=round(o,8), high=round(max(h,o,c,l),8), low=round(min(l,o,c,h),8), close=round(c,8), volume=round(v*scenario.volume_multiplier,8))
        out.append(bar)
        previous_close = c
    return out
