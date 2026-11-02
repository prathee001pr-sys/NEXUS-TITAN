"""Read-only signal and authoritative-risk decision flow; no orders are sent."""
from dataclasses import dataclass
from pathlib import Path

from nexus_titan.data.market_data import load_market_data
from nexus_titan.research.signal_engine import generate_signal
from nexus_titan.risk.risk_manager import RiskConfig
from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig


@dataclass(frozen=True)
class TradingDecision:
    signal: str
    approved: bool
    quantity: int
    risk_amount: float
    reason: str
    candles_loaded: int


def evaluate_csv(
    csv_path: str | Path,
    capital: float,
    stop_price: float,
    config: RiskConfig = RiskConfig(),
    daily_loss_pct: float = 0.0,
    fast_period: int = 5,
    slow_period: int = 10,
    current_exposure: float = 0.0,
    current_open_positions: int = 0,
    consecutive_losses: int = 0,
    current_drawdown_pct: float = 0.0,
    symbol: str = "EQUITY_DEFAULT",
    lot_size: int = 1,
) -> TradingDecision:
    """Load validated CSV, generate SMA signal, apply independent risk checks."""
    data = load_market_data(csv_path)
    if not data.is_valid:
        return TradingDecision("HOLD", False, 0, 0.0,
                              "; ".join(data.errors) or "Market data is invalid.", len(data.candles))
    closes = [c.close for c in data.candles]
    signal = generate_signal(closes, fast_period=fast_period, slow_period=slow_period)
    if signal.action != "BUY":
        return TradingDecision(signal.action, False, 0, 0.0,
                               f"No trade: {signal.reason}", len(data.candles))
    risk = AuthoritativeRiskEngine(PortfolioRiskConfig(
        max_risk_per_trade_pct=config.max_risk_per_trade_pct,
        max_portfolio_exposure_pct=config.max_position_value_pct,
        daily_loss_limit_pct=config.max_daily_loss_pct,
        max_concurrent_positions=config.max_concurrent_positions,
        consecutive_loss_limit=config.consecutive_loss_limit,
    )).size_and_validate(
        capital=capital, entry_price=closes[-1], stop_price=stop_price, symbol=symbol,
        lot_size=lot_size, current_exposure=current_exposure,
        current_open_positions=current_open_positions,
        realized_daily_loss_pct=daily_loss_pct, consecutive_losses=consecutive_losses,
        current_drawdown_pct=current_drawdown_pct,
    )
    return TradingDecision(signal.action, risk.approved, risk.quantity, risk.risk_amount,
                           risk.reason, len(data.candles))
