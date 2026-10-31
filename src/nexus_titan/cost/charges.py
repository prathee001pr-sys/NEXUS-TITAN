"""Configurable Indian statutory transaction cost engine for equities and derivatives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

InstrumentType = Literal[
    "EQUITY_DELIVERY",
    "EQUITY_INTRADAY",
    "FUTURES",
    "OPTIONS",
]


@dataclass(frozen=True)
class TradeCostBreakdown:
    """Detailed statutory and broker charge breakdown for Indian markets."""
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    gst: float
    total_charges: float
    schedule_version: str = "2026-2027.1"
    disclaimer: str = ("Indicative NSE schedule dated 2026-04-01; broker-specific charges and option exercise/physical-settlement "
                       "tax treatment may differ and are not fully modeled. Re-verify official charges before each release.")

    def summary_dict(self) -> dict[str, float | str]:
        return {
            "brokerage": self.brokerage,
            "stt": self.stt,
            "exchange_charges": self.exchange_charges,
            "sebi_charges": self.sebi_charges,
            "stamp_duty": self.stamp_duty,
            "gst": self.gst,
            "total_charges": self.total_charges,
            "schedule_version": self.schedule_version,
            "disclaimer": self.disclaimer,
        }


@dataclass(frozen=True)
class IndianCostConfig:
    """Standard Indian regulatory charge schedule (NSE / SEBI) matching Blueprint P0-08."""
    version: str = "2026-2027.1"
    effective_date: str = "2026-04-01"
    brokerage_pct: float = 0.03
    brokerage_flat_cap: float = 20.0
    gst_pct: float = 18.0
    sebi_per_crore: float = 10.0
    stt_equity_delivery_pct: float = 0.1
    stt_equity_intraday_sell_pct: float = 0.025
    stt_futures_sell_pct: float = 0.05
    stt_options_sell_pct: float = 0.15
    stt_options_exercise_pct: float = 0.15
    exchange_turnover_equity_pct: float = 0.00307
    exchange_turnover_futures_pct: float = 0.00183
    exchange_turnover_options_pct: float = 0.03553
    stamp_duty_equity_delivery_pct: float = 0.015
    stamp_duty_equity_intraday_pct: float = 0.003
    stamp_duty_futures_pct: float = 0.002
    stamp_duty_options_pct: float = 0.003


def calculate_indian_trade_costs(
    side: Literal["BUY", "SELL"],
    price: float,
    quantity: int,
    instrument: InstrumentType = "EQUITY_DELIVERY",
    config: IndianCostConfig = IndianCostConfig(),
) -> TradeCostBreakdown:
    """Calculate indicative India charges using the configured exchange schedule.

    This helper does not fully model option exercise/physical settlement; it is
    an entry/exit estimate, not an official contract-note calculator.
    """
    if price <= 0 or quantity <= 0:
        raise ValueError("Price and quantity must be positive.")
    if not (math.isfinite(price) and math.isfinite(quantity)):
        raise ValueError("Price and quantity must be finite.")
    if side.upper() not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL.")
    if instrument not in ("EQUITY_DELIVERY", "EQUITY_INTRADAY", "FUTURES", "OPTIONS"):
        raise ValueError("Unsupported instrument type.")
    turnover = price * quantity
    is_buy = side.upper() == "BUY"
    raw_brokerage = turnover * (config.brokerage_pct / 100.0)
    brokerage = min(raw_brokerage, config.brokerage_flat_cap)

    stt = 0.0
    if instrument == "EQUITY_DELIVERY":
        stt = turnover * (config.stt_equity_delivery_pct / 100.0)
    elif instrument == "EQUITY_INTRADAY" and not is_buy:
        stt = turnover * (config.stt_equity_intraday_sell_pct / 100.0)
    elif instrument == "FUTURES" and not is_buy:
        stt = turnover * (config.stt_futures_sell_pct / 100.0)
    elif instrument == "OPTIONS" and not is_buy:
        stt = turnover * (config.stt_options_sell_pct / 100.0)

    if instrument in ("EQUITY_DELIVERY", "EQUITY_INTRADAY"):
        exchange_charges = turnover * (config.exchange_turnover_equity_pct / 100.0)
    elif instrument == "FUTURES":
        exchange_charges = turnover * (config.exchange_turnover_futures_pct / 100.0)
    else:
        exchange_charges = turnover * (config.exchange_turnover_options_pct / 100.0)

    sebi_charges = turnover * (config.sebi_per_crore / 10_000_000.0)
    stamp_duty = 0.0
    if is_buy:
        if instrument == "EQUITY_DELIVERY":
            stamp_duty = turnover * (config.stamp_duty_equity_delivery_pct / 100.0)
        elif instrument == "EQUITY_INTRADAY":
            stamp_duty = turnover * (config.stamp_duty_equity_intraday_pct / 100.0)
        elif instrument == "FUTURES":
            stamp_duty = turnover * (config.stamp_duty_futures_pct / 100.0)
        elif instrument == "OPTIONS":
            stamp_duty = turnover * (config.stamp_duty_options_pct / 100.0)

    taxable_service = brokerage + exchange_charges + sebi_charges
    gst = taxable_service * (config.gst_pct / 100.0)
    total_charges = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)
    return TradeCostBreakdown(
        brokerage=round(brokerage, 2), stt=round(stt, 2),
        exchange_charges=round(exchange_charges, 2),
        sebi_charges=round(sebi_charges, 2), stamp_duty=round(stamp_duty, 2),
        gst=round(gst, 2), total_charges=total_charges,
        schedule_version=config.version,
    )
