"""Separate Crypto Market Engine and Isolated 24/7 Risk Silo."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class CryptoSymbolSpec:
    symbol: str
    base_asset: str
    quote_asset: str
    quantity_step: float = 0.0001
    price_tick: float = 0.01
    min_notional: float = 10.0
    maker_fee_pct: float = 0.10
    taker_fee_pct: float = 0.10


DEFAULT_CRYPTO_PAIRS: dict[str, CryptoSymbolSpec] = {
    "BTCUSDT": CryptoSymbolSpec("BTCUSDT", "BTC", "USDT", quantity_step=0.0001, price_tick=0.1, min_notional=10.0),
    "ETHUSDT": CryptoSymbolSpec("ETHUSDT", "ETH", "USDT", quantity_step=0.001, price_tick=0.05, min_notional=10.0),
    "SOLUSDT": CryptoSymbolSpec("SOLUSDT", "SOL", "USDT", quantity_step=0.01, price_tick=0.01, min_notional=5.0),
}


@dataclass(frozen=True)
class CryptoFeeBreakdown:
    fee_type: Literal["MAKER", "TAKER"]
    notional_value: float
    exchange_fee: float
    tds_tax: float
    total_fee: float


def calculate_crypto_trade_costs(
    price: float, quantity: float, side: Literal["BUY", "SELL"] = "BUY",
    is_maker: bool = False, apply_indian_vda_tds: bool = False,
    spec: CryptoSymbolSpec | None = None,
) -> CryptoFeeBreakdown:
    """Calculate maker/taker crypto costs separately from Indian equity charges."""
    if isinstance(price, bool) or isinstance(quantity, bool) or not isinstance(price, (int, float)) or not isinstance(quantity, (int, float)) or price <= 0 or quantity <= 0 or not (math.isfinite(price) and math.isfinite(quantity)):
        raise ValueError("Price and quantity must be finite positive numbers.")
    if not isinstance(side, str) or side.upper() not in ("BUY", "SELL"):
        raise ValueError("Side must be BUY or SELL.")
    if not isinstance(apply_indian_vda_tds, bool):
        raise ValueError("apply_indian_vda_tds must be a boolean.")
    spec = spec or DEFAULT_CRYPTO_PAIRS["BTCUSDT"]
    notional = price * quantity
    rate_pct = spec.maker_fee_pct if is_maker else spec.taker_fee_pct
    exchange_fee = notional * (rate_pct / 100.0)
    tds = notional * 0.01 if apply_indian_vda_tds and side.upper() == "SELL" else 0.0
    return CryptoFeeBreakdown(
        fee_type="MAKER" if is_maker else "TAKER",
        notional_value=round(notional, 4), exchange_fee=round(exchange_fee, 4),
        tds_tax=round(tds, 4), total_fee=round(exchange_fee + tds, 4),
    )


class CryptoVirtualAccount:
    """Isolated virtual capital and fractional position ledger for 24/7 crypto markets."""

    def __init__(
        self, account_id: str = "TITAN-CRYPTO-SILO", starting_capital: float | None = None,
        currency: str = "USDT", max_portfolio_exposure_pct: float = 100.0,
        apply_indian_vda_tds: bool = False,
    ):
        if starting_capital is None:
            raise ValueError("Crypto starting capital must be explicitly configured.")
        if isinstance(starting_capital, bool) or not isinstance(starting_capital, (int, float)) or starting_capital <= 0 or not math.isfinite(starting_capital):
            raise ValueError("Starting capital must be a finite positive number.")
        if isinstance(max_portfolio_exposure_pct, bool) or not isinstance(max_portfolio_exposure_pct, (int, float)) or not math.isfinite(max_portfolio_exposure_pct) or not 0 < max_portfolio_exposure_pct <= 100:
            raise ValueError("max_portfolio_exposure_pct must be finite and between 0 and 100.")
        if not isinstance(apply_indian_vda_tds, bool):
            raise ValueError("apply_indian_vda_tds must be a boolean.")
        self.account_id = account_id
        self.currency = currency
        self.starting_capital = float(starting_capital)
        self.cash_balance = float(starting_capital)
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.total_tds_withheld = 0.0
        self.max_portfolio_exposure_pct = float(max_portfolio_exposure_pct)
        self.apply_indian_vda_tds = apply_indian_vda_tds
        self.positions: dict[str, dict[str, float]] = {}

    def execute_crypto_order(
        self, symbol: str, side: Literal["BUY", "SELL"], price: float,
        quantity: float, is_maker: bool = False,
    ) -> dict[str, float | str]:
        if not isinstance(symbol, str) or symbol.upper() not in DEFAULT_CRYPTO_PAIRS:
            raise ValueError(f"Unknown crypto symbol '{symbol}'. Add verified exchange metadata first.")
        if side not in ("BUY", "SELL"):
            raise ValueError("Side must be BUY or SELL.")
        if isinstance(price, bool) or isinstance(quantity, bool) or not isinstance(price, (int, float)) or not isinstance(quantity, (int, float)) or price <= 0 or quantity <= 0 or not (math.isfinite(price) and math.isfinite(quantity)):
            raise ValueError("Price and quantity must be finite positive numbers.")
        spec = DEFAULT_CRYPTO_PAIRS[symbol.upper()]
        rounded_qty = math.floor(quantity / spec.quantity_step) * spec.quantity_step
        rounded_qty = round(rounded_qty, 8)
        if rounded_qty < spec.quantity_step:
            raise ValueError(f"Quantity below minimum step {spec.quantity_step} for {symbol}.")
        notional = price * rounded_qty
        if notional < spec.min_notional:
            raise ValueError(f"Order notional below minimum required ({spec.min_notional:.2f}).")
        costs = calculate_crypto_trade_costs(price, rounded_qty, side=side, is_maker=is_maker,
                                             apply_indian_vda_tds=self.apply_indian_vda_tds, spec=spec)
        fee, tds = costs.exchange_fee, costs.tds_tax
        if side.upper() == "BUY":
            total_cost = notional + fee
            exposure = sum(item["avg_price"] * item["quantity"] for item in self.positions.values())
            max_exposure = self.starting_capital * (self.max_portfolio_exposure_pct / 100.0)
            if exposure + notional > max_exposure:
                raise ValueError("Crypto portfolio exposure cap exceeded.")
            if self.cash_balance < total_cost:
                raise ValueError(f"Insufficient crypto cash: need {total_cost:.2f}, have {self.cash_balance:.2f}.")
            self.cash_balance -= total_cost
            self.total_fees += fee
            pos = self.positions.get(spec.symbol)
            if pos:
                new_qty = round(pos["quantity"] + rounded_qty, 8)
                pos["avg_price"] = (pos["avg_price"] * pos["quantity"] + price * rounded_qty) / new_qty
                pos["quantity"] = new_qty
                pos["unamortized_entry_fee"] = round(pos.get("unamortized_entry_fee", 0.0) + fee, 6)
            else:
                self.positions[spec.symbol] = {
                    "quantity": rounded_qty,
                    "avg_price": price,
                    "unamortized_entry_fee": round(fee, 6),
                }
        else:
            pos = self.positions.get(spec.symbol)
            if not pos or pos["quantity"] + 1e-10 < rounded_qty:
                raise ValueError(f"Insufficient open crypto position for {spec.symbol}.")
            if "unamortized_entry_fee" in pos:
                total_unamort = pos["unamortized_entry_fee"]
                entry_fee = total_unamort if abs(pos["quantity"] - rounded_qty) <= 1e-8 else round(
                    total_unamort * (rounded_qty / pos["quantity"]), 6
                )
                pos["unamortized_entry_fee"] = round(max(0.0, total_unamort - entry_fee), 6)
            else:
                entry_fee = calculate_crypto_trade_costs(
                    pos["avg_price"], rounded_qty, "BUY", is_maker, spec=spec
                ).exchange_fee
            proceeds = notional - fee - tds
            net_pnl = (price - pos["avg_price"]) * rounded_qty - fee - entry_fee - tds
            self.cash_balance += proceeds
            self.realized_pnl += net_pnl
            self.total_fees += fee
            self.total_tds_withheld += tds
            pos["quantity"] = round(pos["quantity"] - rounded_qty, 8)
            if pos["quantity"] <= 1e-8:
                del self.positions[spec.symbol]
        return {
            "symbol": spec.symbol, "side": side.upper(), "filled_qty": rounded_qty,
            "fill_price": price, "fee": fee, "tds_withheld": tds,
            "cash_balance": round(self.cash_balance, 4),
        }

    def reconcile_crypto(self) -> dict[str, float | bool]:
        """Reconcile crypto virtual cash balance against starting capital, realized P&L, and open cost basis."""
        open_locked = sum(
            pos["avg_price"] * pos["quantity"] + pos.get("unamortized_entry_fee", 0.0)
            for pos in self.positions.values()
        )
        expected_cash = round(self.starting_capital + self.realized_pnl - open_locked, 4)
        discrepancy = round(abs(self.cash_balance - expected_cash), 4)
        return {
            "starting_capital": round(self.starting_capital, 4),
            "cash_balance": round(self.cash_balance, 4),
            "realized_pnl": round(self.realized_pnl, 4),
            "total_fees": round(self.total_fees, 4),
            "total_tds_withheld": round(self.total_tds_withheld, 4),
            "open_cost_locked": round(open_locked, 4),
            "discrepancy": discrepancy,
            "is_reconciled": discrepancy < 0.01,
        }
