"""Advanced portfolio risk controls, Decimal tick rounding, lot rounding, and circuit breakers."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal


@dataclass(frozen=True)
class InstrumentSpec:
    """Trading parameters for specific exchange instruments."""
    symbol: str
    lot_size: int = 1
    tick_size: float = 0.05
    max_lots_per_trade: int = 20
    freeze_quantity: int = 1800


DEFAULT_INSTRUMENT_SPECS: dict[str, InstrumentSpec] = {
    "NIFTY": InstrumentSpec(symbol="NIFTY", lot_size=25, tick_size=0.05, max_lots_per_trade=10, freeze_quantity=1800),
    "BANKNIFTY": InstrumentSpec(symbol="BANKNIFTY", lot_size=15, tick_size=0.05, max_lots_per_trade=10, freeze_quantity=900),
    "FINNIFTY": InstrumentSpec(symbol="FINNIFTY", lot_size=25, tick_size=0.05, max_lots_per_trade=10, freeze_quantity=1800),
    "MIDCPNIFTY": InstrumentSpec(symbol="MIDCPNIFTY", lot_size=50, tick_size=0.05, max_lots_per_trade=10, freeze_quantity=2800),
    "EQUITY_DEFAULT": InstrumentSpec(symbol="EQUITY_DEFAULT", lot_size=1, tick_size=0.05, max_lots_per_trade=500, freeze_quantity=100000),
}


@dataclass(frozen=True)
class PortfolioRiskConfig:
    """Comprehensive portfolio and pre-trade risk thresholds."""
    max_risk_per_trade_pct: float = 1.0
    max_portfolio_exposure_pct: float = 60.0
    max_concurrent_positions: int = 4
    daily_loss_limit_pct: float = 3.0
    consecutive_loss_limit: int = 3
    max_drawdown_limit_pct: float = 10.0


@dataclass(frozen=True)
class PreTradeRiskResult:
    """Evaluation result for an intended trade order."""
    approved: bool
    quantity: int
    risk_amount: float
    effective_entry: float
    effective_stop: float
    reason: str


def round_to_tick(price: float, tick_size: float = 0.05) -> float:
    """Round a price deterministically to the nearest exchange valid tick using Decimal arithmetic."""
    if isinstance(price, bool) or isinstance(tick_size, bool) or not isinstance(price, (int, float)) or not isinstance(tick_size, (int, float)):
        raise ValueError("price and tick_size must be numeric.")
    if not (math.isfinite(price) and math.isfinite(tick_size)) or tick_size <= 0:
        raise ValueError("price must be finite and tick_size must be positive.")
    d_price = Decimal(str(price))
    d_tick = Decimal(str(tick_size))
    steps = (d_price / d_tick).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    rounded = (steps * d_tick).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return float(rounded)


class PortfolioRiskManager:
    """Deterministic pre-trade risk gatekeeper supporting Long (BUY) and Short (SELL) entries."""

    def __init__(self, config: PortfolioRiskConfig = PortfolioRiskConfig()):
        self.config = config

    def evaluate_order(
        self,
        capital: float,
        current_exposure: float,
        current_open_positions: int,
        realized_daily_loss_pct: float,
        consecutive_losses: int,
        entry_price: float,
        stop_price: float,
        spec: InstrumentSpec | None = None,
        current_drawdown_pct: float = 0.0,
        side: Literal["BUY", "SELL"] = "BUY",
    ) -> PreTradeRiskResult:
        """Run pre-trade risk checks including lot rounding, freeze qty, and circuit breakers."""
        spec = spec or DEFAULT_INSTRUMENT_SPECS["EQUITY_DEFAULT"]
        for val in (capital, current_exposure, realized_daily_loss_pct, entry_price, stop_price, current_drawdown_pct):
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Inputs must be finite numbers.")
        if capital <= 0 or entry_price <= 0:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Capital and entry price must be positive.")
        if current_exposure < 0 or realized_daily_loss_pct < 0 or current_drawdown_pct < 0:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Exposure and loss/drawdown percentages cannot be negative.")
        if isinstance(current_open_positions, bool) or not isinstance(current_open_positions, int) or current_open_positions < 0:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "current_open_positions must be a non-negative integer.")
        if isinstance(consecutive_losses, bool) or not isinstance(consecutive_losses, int) or consecutive_losses < 0:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "consecutive_losses must be a non-negative integer.")
        if (not isinstance(spec.lot_size, int) or isinstance(spec.lot_size, bool) or spec.lot_size < 1
                or not math.isfinite(spec.tick_size) or spec.tick_size <= 0
                or not isinstance(spec.max_lots_per_trade, int) or spec.max_lots_per_trade < 1):
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Instrument lot/tick configuration is invalid.")
        if not isinstance(side, str) or side.upper() not in ("BUY", "SELL"):
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "side must be BUY or SELL.")
        cfg_values = (
            self.config.max_risk_per_trade_pct, self.config.max_portfolio_exposure_pct,
            self.config.daily_loss_limit_pct, self.config.max_drawdown_limit_pct,
        )
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in cfg_values):
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Risk configuration must contain finite numbers.")
        if not (
            0 < self.config.max_risk_per_trade_pct <= 100
            and 0 < self.config.max_portfolio_exposure_pct <= 100
            and 0 < self.config.daily_loss_limit_pct <= 100
            and 0 < self.config.max_drawdown_limit_pct <= 100
            and self.config.max_concurrent_positions >= 1
            and self.config.consecutive_loss_limit >= 1
        ):
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Risk configuration is outside supported limits.")

        clean_entry = round_to_tick(entry_price, spec.tick_size)
        clean_stop = round_to_tick(stop_price, spec.tick_size)
        is_buy = side.upper() == "BUY"
        if is_buy:
            if clean_stop <= 0 or clean_stop >= clean_entry:
                return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "Stop price must be positive and below entry price.")
            risk_per_share = clean_entry - clean_stop
        else:
            if clean_stop <= clean_entry:
                return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, "SHORT stop price must be strictly above entry price.")
            risk_per_share = clean_stop - clean_entry

        if realized_daily_loss_pct >= self.config.daily_loss_limit_pct:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, f"Daily loss limit ({self.config.daily_loss_limit_pct}%) breached. Trading locked.")
        if current_drawdown_pct >= self.config.max_drawdown_limit_pct:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, f"Maximum drawdown limit ({self.config.max_drawdown_limit_pct}%) breached. Trading locked.")
        if consecutive_losses >= self.config.consecutive_loss_limit:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, f"Consecutive loss guard triggered ({consecutive_losses} losses). Trading paused.")
        if current_open_positions >= self.config.max_concurrent_positions:
            return PreTradeRiskResult(False, 0, 0.0, 0.0, 0.0, f"Max concurrent positions ({self.config.max_concurrent_positions}) reached.")

        risk_budget = capital * (self.config.max_risk_per_trade_pct / 100.0)
        raw_quantity = math.floor(risk_budget / risk_per_share)
        max_allowed_exposure = capital * (self.config.max_portfolio_exposure_pct / 100.0)
        remaining_exposure = max(0.0, max_allowed_exposure - current_exposure)
        exposure_cap_qty = math.floor(remaining_exposure / clean_entry)
        target_qty = min(raw_quantity, exposure_cap_qty)
        lot_rounded_qty = (target_qty // spec.lot_size) * spec.lot_size
        max_allowed_qty = min(spec.max_lots_per_trade * spec.lot_size, getattr(spec, "freeze_quantity", 100000))
        final_qty = min(lot_rounded_qty, max_allowed_qty)

        if final_qty < spec.lot_size:
            return PreTradeRiskResult(False, 0, 0.0, clean_entry, clean_stop,
                f"Capital or risk budget too small for minimum 1 lot ({spec.lot_size} units).")
        total_risk = round(final_qty * risk_per_share, 2)
        return PreTradeRiskResult(
            approved=True, quantity=final_qty, risk_amount=total_risk,
            effective_entry=clean_entry, effective_stop=clean_stop,
            reason=f"Approved: {final_qty} units ({final_qty // spec.lot_size} lots) within risk budget.",
        )
