"""Unified Authoritative Risk Engine for backtest and virtual execution."""

from __future__ import annotations

from nexus_titan.risk.portfolio_risk import (
    DEFAULT_INSTRUMENT_SPECS,
    InstrumentSpec,
    PortfolioRiskConfig,
    PortfolioRiskManager,
    PreTradeRiskResult,
)


class AuthoritativeRiskEngine:
    """Single source of truth for lot sizing and deterministic risk checks."""

    def __init__(self, config: PortfolioRiskConfig = PortfolioRiskConfig()):
        self.config = config
        self._portfolio_mgr = PortfolioRiskManager(config)

    def size_and_validate(
        self,
        capital: float,
        entry_price: float,
        stop_price: float,
        symbol: str = "EQUITY_DEFAULT",
        lot_size: int | None = None,
        tick_size: float = 0.05,
        current_exposure: float = 0.0,
        current_open_positions: int = 0,
        realized_daily_loss_pct: float = 0.0,
        consecutive_losses: int = 0,
        slippage_buffer: float = 0.0,
        current_drawdown_pct: float = 0.0,
    ) -> PreTradeRiskResult:
        """Evaluate risk and compute whole-lot quantity within configured limits."""
        base_spec = DEFAULT_INSTRUMENT_SPECS.get(symbol.upper(), DEFAULT_INSTRUMENT_SPECS["EQUITY_DEFAULT"])
        effective_lot = lot_size if lot_size is not None else base_spec.lot_size
        effective_spec = InstrumentSpec(
            symbol=symbol.upper(),
            lot_size=effective_lot,
            tick_size=tick_size,
            max_lots_per_trade=base_spec.max_lots_per_trade,
        )
        adjusted_stop = stop_price - slippage_buffer if stop_price < entry_price else stop_price
        return self._portfolio_mgr.evaluate_order(
            capital=capital,
            current_exposure=current_exposure,
            current_open_positions=current_open_positions,
            realized_daily_loss_pct=realized_daily_loss_pct,
            consecutive_losses=consecutive_losses,
            entry_price=entry_price,
            stop_price=adjusted_stop,
            spec=effective_spec,
            current_drawdown_pct=current_drawdown_pct,
        )
