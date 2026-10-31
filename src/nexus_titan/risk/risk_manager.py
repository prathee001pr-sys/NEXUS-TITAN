"""Legacy-compatible configurable risk settings for CSV decision flow."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    max_risk_per_trade_pct: float = 1.0
    max_position_value_pct: float = 50.0
    max_daily_loss_pct: float = 3.0
    max_concurrent_positions: int = 4
    consecutive_loss_limit: int = 3
