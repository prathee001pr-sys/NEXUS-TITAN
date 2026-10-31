"""Pure standard-library Indian F&O Contract Master and Black-Scholes Options Greeks Engine."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

OptionType = Literal["CE", "PE"]


@dataclass(frozen=True)
class DerivativeContract:
    symbol: str
    underlying: str
    exchange: str
    segment: Literal["FUTURES", "OPTIONS"]
    expiry_date: str
    strike: float | None
    option_type: OptionType | None
    lot_size: int
    tick_size: float = 0.05
    freeze_quantity: int = 1800
    effective_from: str = "2025-01-01"
    effective_to: str = "2026-12-31"


@dataclass(frozen=True)
class OptionGreeks:
    option_type: OptionType
    theoretical_price: float
    delta: float
    gamma: float
    theta_daily: float
    vega_per_pct: float
    rho_per_pct: float
    implied_volatility: float


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)


def calculate_option_greeks(
    spot: float, strike: float, days_to_expiry: float,
    volatility: float = 0.15, risk_free_rate: float = 0.068,
    option_type: OptionType = "CE",
) -> OptionGreeks:
    """Calculate theoretical option premium and Black-Scholes first/second-order sensitivities."""
    for label, value in (("spot", spot), ("strike", strike),
                         ("days_to_expiry", days_to_expiry),
                         ("volatility", volatility), ("risk_free_rate", risk_free_rate)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number.")
    if spot <= 0 or strike <= 0 or volatility <= 0 or days_to_expiry < 0:
        raise ValueError("Spot, strike and volatility must be positive; days_to_expiry cannot be negative.")
    opt_clean = option_type.upper()
    if opt_clean not in ("CE", "PE"):
        raise ValueError("option_type must be 'CE' or 'PE'.")
    t = max(days_to_expiry / 365.0, 1e-5)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility * volatility) * t) / (volatility * sqrt_t)
    d2 = d1 - volatility * sqrt_t
    pdf_d1 = _norm_pdf(d1)
    discount = math.exp(-risk_free_rate * t)
    if opt_clean == "CE":
        price = spot * _norm_cdf(d1) - strike * discount * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta_annual = -(spot * pdf_d1 * volatility) / (2.0 * sqrt_t) - risk_free_rate * strike * discount * _norm_cdf(d2)
        rho = (strike * t * discount * _norm_cdf(d2)) / 100.0
    else:
        price = strike * discount * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
        theta_annual = -(spot * pdf_d1 * volatility) / (2.0 * sqrt_t) + risk_free_rate * strike * discount * _norm_cdf(-d2)
        rho = -(strike * t * discount * _norm_cdf(-d2)) / 100.0
    gamma = pdf_d1 / (spot * volatility * sqrt_t)
    vega = (spot * pdf_d1 * sqrt_t) / 100.0
    theta_daily = theta_annual / 365.0
    return OptionGreeks(
        option_type=opt_clean, theoretical_price=round(max(0.05, price), 2),
        delta=round(delta, 4), gamma=round(gamma, 6),
        theta_daily=round(theta_daily, 2), vega_per_pct=round(vega, 2),
        rho_per_pct=round(rho, 2), implied_volatility=round(volatility, 4),
    )


def solve_implied_volatility(
    market_price: float, spot: float, strike: float, days_to_expiry: float,
    option_type: OptionType = "CE", risk_free_rate: float = 0.068,
) -> float:
    """Solve implied volatility using a bounded bisection search."""
    for label, value in (("market_price", market_price), ("spot", spot), ("strike", strike),
                         ("days_to_expiry", days_to_expiry), ("risk_free_rate", risk_free_rate)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label} must be finite.")
    if market_price <= 0 or spot <= 0 or strike <= 0 or days_to_expiry < 0:
        raise ValueError("Premium and underlying prices must be positive; expiry cannot be negative.")
    if option_type.upper() not in ("CE", "PE"):
        raise ValueError("option_type must be CE or PE.")
    low_vol, high_vol, vol = 0.01, 3.00, 0.20
    for _ in range(60):
        greeks = calculate_option_greeks(spot, strike, days_to_expiry, vol, risk_free_rate, option_type)
        diff = greeks.theoretical_price - market_price
        if abs(diff) < 0.01:
            return round(vol, 4)
        if diff > 0:
            high_vol = vol
        else:
            low_vol = vol
        vol = 0.5 * (low_vol + high_vol)
    return round(vol, 4)
