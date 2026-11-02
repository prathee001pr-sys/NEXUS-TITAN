"""Basic risk controls for virtual trading and CSV research, retained as a legacy facade."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    quantity: int
    risk_amount: float
    reason: str


@dataclass(frozen=True)
class RiskConfig:
    max_risk_per_trade_pct: float = 1.0
    max_position_value_pct: float = 20.0
    max_daily_loss_pct: float = 3.0
    max_concurrent_positions: int = 4
    consecutive_loss_limit: int = 3


def calculate_position(
    capital: float,
    entry_price: float,
    stop_price: float,
    config: RiskConfig = RiskConfig(),
    daily_loss_pct: float = 0.0,
) -> RiskDecision:
    """Calculate a whole-unit position using the original V6 ZIP risk rules."""
    values = (capital, entry_price, stop_price, daily_loss_pct)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return RiskDecision(False, 0, 0.0, "Inputs must be finite numbers.")
    if capital <= 0 or entry_price <= 0:
        return RiskDecision(False, 0, 0.0, "Capital and entry price must be positive.")
    if stop_price <= 0 or stop_price >= entry_price:
        return RiskDecision(False, 0, 0.0, "Stop price must be positive and below entry.")
    if not 0 <= daily_loss_pct <= 100:
        return RiskDecision(False, 0, 0.0, "Daily loss percentage must be between 0 and 100.")
    if not isinstance(config, RiskConfig):
        return RiskDecision(False, 0, 0.0, "Invalid risk configuration.")
    config_values = (config.max_risk_per_trade_pct, config.max_position_value_pct, config.max_daily_loss_pct)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in config_values):
        return RiskDecision(False, 0, 0.0, "Risk configuration must contain finite numbers.")
    if not 0 < config.max_risk_per_trade_pct <= 1:
        return RiskDecision(False, 0, 0.0, "Risk per trade must be between 0% and 1%.")
    if not 0 < config.max_position_value_pct <= 100:
        return RiskDecision(False, 0, 0.0, "Position limit must be between 0% and 100%.")
    if not 0 < config.max_daily_loss_pct <= 100:
        return RiskDecision(False, 0, 0.0, "Daily loss limit must be between 0% and 100%.")
    if daily_loss_pct >= config.max_daily_loss_pct:
        return RiskDecision(False, 0, 0.0, "Daily loss limit reached.")
    risk_budget = capital * config.max_risk_per_trade_pct / 100
    risk_per_unit = entry_price - stop_price
    by_risk = math.floor(risk_budget / risk_per_unit)
    by_capital = math.floor(capital * config.max_position_value_pct / 100 / entry_price)
    quantity = min(by_risk, by_capital)
    if quantity < 1:
        return RiskDecision(False, 0, 0.0, "Capital or risk budget is too small for one unit.")
    return RiskDecision(True, quantity, quantity * risk_per_unit,
                        "Position is within configured risk limits.")
