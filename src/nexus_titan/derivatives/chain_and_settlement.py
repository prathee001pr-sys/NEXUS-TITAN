"""Historical Option Chain Validation, SPAN/ELM Margin Estimator, and Expiry Settlement Engine (Workstreams F, G, H, O)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from nexus_titan.cost.charges import IndianCostConfig, calculate_indian_trade_costs
from nexus_titan.derivatives.options_engine import OptionType


@dataclass(frozen=True)
class OptionChainQuote:
    """Point-in-time option strike quote with bid/ask, OI, volume, and underlying spot (Workstream H)."""

    timestamp: str
    symbol: str
    underlying: str
    expiry_date: str
    strike: float
    option_type: OptionType
    bid: float
    ask: float
    ltp: float
    volume: int
    open_interest: int
    underlying_spot: float
    lot_size: int = 25

    @property
    def mid_price(self) -> float:
        return round(0.5 * (self.bid + self.ask), 2)

    @property
    def spread_pct(self) -> float:
        return round(((self.ask - self.bid) / self.mid_price) * 100.0, 4) if self.mid_price > 0 else 0.0


@dataclass(frozen=True)
class OptionChainQualityReport:
    """Validation report for a point-in-time option chain snapshot (Workstream H)."""

    quote_count: int
    crossed_quotes: int
    intrinsic_arbitrage_violations: int
    wide_spread_quotes: int
    zero_oi_quotes: int
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        # A zero-OI or excessively wide quote is not reliable execution evidence.
        return (self.crossed_quotes == 0 and self.intrinsic_arbitrage_violations == 0
                and self.wide_spread_quotes == 0 and self.zero_oi_quotes == 0
                and len(self.errors) == 0)


def inspect_option_chain_snapshot(
    quotes: list[OptionChainQuote] | tuple[OptionChainQuote, ...],
    *,
    max_spread_pct: float = 15.0,
    intrinsic_tolerance: float = 2.0,
) -> OptionChainQualityReport:
    """Reject malformed, crossed, wide-spread and zero-OI option quotes.

    A valid structural snapshot is not a guarantee of exchange liquidity; this
    gate only ensures the supplied quote passes the configured minimum checks.
    """
    if not math.isfinite(max_spread_pct) or max_spread_pct <= 0:
        raise ValueError("max_spread_pct must be a finite positive number.")
    if not math.isfinite(intrinsic_tolerance) or intrinsic_tolerance < 0:
        raise ValueError("intrinsic_tolerance must be a finite non-negative number.")
    errors: list[str] = []
    crossed = arb = wide = zero_oi = 0

    for idx, q in enumerate(quotes):
        bad_row = False
        if not isinstance(q, OptionChainQuote):
            errors.append(f"Row {idx}: item is not an OptionChainQuote.")
            continue
        try:
            quote_time = datetime.fromisoformat(q.timestamp.replace("Z", "+00:00"))
            expiry = datetime.fromisoformat(q.expiry_date).date()
            if quote_time.tzinfo is None or quote_time.utcoffset() is None:
                raise ValueError("timezone offset missing")
            if expiry < quote_time.date():
                errors.append(f"Row {idx} ({q.symbol}): expiry date precedes quote timestamp.")
                bad_row = True
        except (AttributeError, TypeError, ValueError):
            errors.append(f"Row {idx} ({getattr(q, 'symbol', 'UNKNOWN')}): timestamp/expiry must be valid ISO dates with an aware quote timestamp.")
            bad_row = True

        numeric_values = (q.bid, q.ask, q.ltp, q.strike, q.underlying_spot)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in numeric_values):
            errors.append(f"Row {idx} ({q.symbol}): prices, strike, and spot must be finite numbers.")
            bad_row = True
        elif min(q.bid, q.ask, q.ltp, q.strike, q.underlying_spot) <= 0:
            errors.append(f"Row {idx} ({q.symbol}): prices, strike, and spot must be positive.")
            bad_row = True

        if isinstance(q.volume, bool) or not isinstance(q.volume, int) or q.volume < 0:
            errors.append(f"Row {idx} ({q.symbol}): volume must be a non-negative integer.")
            bad_row = True
        if isinstance(q.open_interest, bool) or not isinstance(q.open_interest, int) or q.open_interest < 0:
            errors.append(f"Row {idx} ({q.symbol}): open interest must be a non-negative integer.")
            bad_row = True
        if isinstance(q.lot_size, bool) or not isinstance(q.lot_size, int) or q.lot_size < 1:
            errors.append(f"Row {idx} ({q.symbol}): lot_size must be a positive integer.")
            bad_row = True
        if q.option_type not in ("CE", "PE"):
            errors.append(f"Row {idx} ({q.symbol}): option_type must be CE or PE.")
            bad_row = True
        if bad_row:
            continue

        if q.bid > q.ask:
            crossed += 1
            errors.append(f"Row {idx} ({q.symbol}): crossed market bid ({q.bid}) > ask ({q.ask}).")
        intrinsic = max(0.0, q.underlying_spot - q.strike) if q.option_type == "CE" else max(0.0, q.strike - q.underlying_spot)
        if q.ask + intrinsic_tolerance < intrinsic:
            arb += 1
            errors.append(f"Row {idx} ({q.symbol}): ask ({q.ask}) violates intrinsic lower bound ({intrinsic:.2f}).")
        if q.spread_pct > max_spread_pct:
            wide += 1
            errors.append(f"Row {idx} ({q.symbol}): spread {q.spread_pct:.2f}% exceeds {max_spread_pct:.2f}% limit.")
        if q.open_interest <= 0:
            zero_oi += 1
            errors.append(f"Row {idx} ({q.symbol}): zero open interest is not eligible for execution research.")

    return OptionChainQualityReport(
        quote_count=len(quotes), crossed_quotes=crossed,
        intrinsic_arbitrage_violations=arb, wide_spread_quotes=wide,
        zero_oi_quotes=zero_oi, errors=tuple(errors),
    )


@dataclass(frozen=True)
class DerivativeMarginRequirement:
    """Indicative NSE SPAN + Exposure Loss Margin (ELM) requirement (Workstreams F & O)."""

    instrument_type: Literal["FUTURES", "OPTIONS_LONG", "OPTIONS_SHORT"]
    notional_value: float
    span_margin: float
    exposure_margin: float
    premium_required: float
    total_margin_blocked: float


def estimate_span_elm_margin(
    *,
    underlying_spot: float,
    quantity: int,
    instrument_type: Literal["FUTURES", "OPTIONS_LONG", "OPTIONS_SHORT"],
    option_premium: float = 0.0,
    strike: float | None = None,
    option_type: OptionType = "CE",
    span_pct: float = 12.0,
    elm_pct: float = 3.0,
) -> DerivativeMarginRequirement:
    """Calculate indicative NSE SPAN + Exposure margin for futures, long options, and short options."""
    numeric = (underlying_spot, option_premium, span_pct, elm_pct)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in numeric):
        raise ValueError("Margin inputs must be finite numbers.")
    if underlying_spot <= 0 or isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ValueError("underlying_spot and integer quantity must be positive.")
    if not 0 <= span_pct <= 100 or not 0 <= elm_pct <= 100 or option_premium < 0:
        raise ValueError("Margin percentages must be 0..100 and option_premium non-negative.")
    if instrument_type not in ("FUTURES", "OPTIONS_LONG", "OPTIONS_SHORT"):
        raise ValueError(f"Unsupported derivative margin type: {instrument_type}")
    if instrument_type == "OPTIONS_SHORT":
        if strike is None or isinstance(strike, bool) or not isinstance(strike, (int, float)) or not math.isfinite(strike) or strike <= 0:
            raise ValueError("Short options require a finite positive strike.")
        if option_type not in ("CE", "PE"):
            raise ValueError("option_type must be CE or PE.")
    notional = underlying_spot * quantity
    if instrument_type == "FUTURES":
        span = round(notional * (span_pct / 100.0), 2)
        elm = round(notional * (elm_pct / 100.0), 2)
        return DerivativeMarginRequirement("FUTURES", round(notional, 2), span, elm, 0.0, round(span + elm, 2))
    if instrument_type == "OPTIONS_LONG":
        if option_premium <= 0:
            raise ValueError("Long options require positive option_premium.")
        prem = round(option_premium * quantity, 2)
        return DerivativeMarginRequirement("OPTIONS_LONG", round(notional, 2), 0.0, 0.0, prem, prem)
    if instrument_type == "OPTIONS_SHORT":
        if strike is None or strike <= 0 or option_premium < 0:
            raise ValueError("Short options require valid strike and option_premium.")
        otm_amount = max(0.0, strike - underlying_spot) if option_type == "CE" else max(0.0, underlying_spot - strike)
        base_span = max(
            notional * (span_pct / 100.0) - otm_amount * quantity,
            notional * 0.05,
        )
        span = round(base_span + option_premium * quantity, 2)
        elm = round(notional * (elm_pct / 100.0), 2)
        return DerivativeMarginRequirement("OPTIONS_SHORT", round(notional, 2), span, elm, 0.0, round(span + elm, 2))
    raise ValueError(f"Unsupported derivative margin type: {instrument_type}")


@dataclass(frozen=True)
class OptionExpirySettlementResult:
    """Settlement result at option expiry including intrinsic payoff, exercise STT, and physical settlement check (Workstream O)."""

    symbol: str
    option_type: OptionType
    side: Literal["LONG", "SHORT"]
    settlement_spot: float
    strike: float
    quantity: int
    entry_premium: float
    intrinsic_payoff_per_unit: float
    is_in_the_money: bool
    exercised: bool
    settlement_mode: Literal["CASH_INDEX", "PHYSICAL_STOCK_OBLIGATION", "EXPIRED_WORTHLESS"]
    exercise_stt: float
    gross_pnl: float
    net_pnl_after_exercise_stt: float
    warning: str


def settle_option_at_expiry(
    *,
    symbol: str,
    option_type: OptionType,
    side: Literal["LONG", "SHORT"],
    settlement_spot: float,
    strike: float,
    quantity: int,
    entry_premium: float,
    is_index_option: bool = True,
    cost_config: IndianCostConfig = IndianCostConfig(),
) -> OptionExpirySettlementResult:
    """Evaluate option expiry settlement, intrinsic exercise STT (0.125%/0.15% on intrinsic/settlement), and physical delivery flags."""
    values = (settlement_spot, strike, entry_premium)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("Settlement prices and premium must be finite numbers.")
    if (settlement_spot <= 0 or strike <= 0 or isinstance(quantity, bool)
            or not isinstance(quantity, int) or quantity < 1 or entry_premium < 0):
        raise ValueError("settlement_spot/strike must be positive, quantity a positive integer, premium non-negative.")
    if side not in ("LONG", "SHORT") or not isinstance(is_index_option, bool):
        raise ValueError("side must be LONG/SHORT and is_index_option must be boolean.")
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol is required.")
    opt = option_type.upper() if isinstance(option_type, str) else ""
    if opt not in ("CE", "PE"):
        raise ValueError("option_type must be CE or PE.")
    intrinsic = max(0.0, settlement_spot - strike) if opt == "CE" else max(0.0, strike - settlement_spot)
    itm = intrinsic > 0.0
    entry_charges = calculate_indian_trade_costs(
        "BUY" if side == "LONG" else "SELL", max(0.05, entry_premium), quantity, "OPTIONS", cost_config
    ).total_charges

    if not itm:
        gross = -entry_premium * quantity if side == "LONG" else entry_premium * quantity
        return OptionExpirySettlementResult(
            symbol=symbol,
            option_type=opt,  # type: ignore[arg-type]
            side=side,
            settlement_spot=settlement_spot,
            strike=strike,
            quantity=quantity,
            entry_premium=entry_premium,
            intrinsic_payoff_per_unit=0.0,
            is_in_the_money=False,
            exercised=False,
            settlement_mode="EXPIRED_WORTHLESS",
            exercise_stt=0.0,
            gross_pnl=round(gross, 2),
            net_pnl_after_exercise_stt=round(gross - entry_charges, 2),
            warning="Option expired OTM/ATM worthless.",
        )

    # Exercise STT applies to long ITM exercised options
    exercise_stt = (
        round(intrinsic * quantity * (cost_config.stt_options_exercise_pct / 100.0), 2)
        if side == "LONG"
        else 0.0
    )
    if side == "LONG":
        gross = (intrinsic - entry_premium) * quantity
        # Do-not-exercise guard when exercise STT exceeds intrinsic value
        if intrinsic * quantity < exercise_stt:
            return OptionExpirySettlementResult(
                symbol=symbol,
                option_type=opt,  # type: ignore[arg-type]
                side=side,
                settlement_spot=settlement_spot,
                strike=strike,
                quantity=quantity,
                entry_premium=entry_premium,
                intrinsic_payoff_per_unit=round(intrinsic, 2),
                is_in_the_money=True,
                exercised=False,
                settlement_mode="EXPIRED_WORTHLESS",
                exercise_stt=0.0,
                gross_pnl=round(-entry_premium * quantity, 2),
                net_pnl_after_exercise_stt=round(-entry_premium * quantity - entry_charges, 2),
                warning="Intrinsic payoff smaller than exercise STT; do-not-exercise protection triggered.",
            )
    else:
        gross = (entry_premium - intrinsic) * quantity

    mode: Literal["CASH_INDEX", "PHYSICAL_STOCK_OBLIGATION"] = (
        "CASH_INDEX" if is_index_option else "PHYSICAL_STOCK_OBLIGATION"
    )
    warn = (
        "Cash-settled index option exercised at intrinsic value."
        if is_index_option
        else "CRITICAL: Stock option finished ITM; physical delivery obligation & penalty margins apply unless squared off pre-expiry."
    )
    return OptionExpirySettlementResult(
        symbol=symbol,
        option_type=opt,  # type: ignore[arg-type]
        side=side,
        settlement_spot=settlement_spot,
        strike=strike,
        quantity=quantity,
        entry_premium=entry_premium,
        intrinsic_payoff_per_unit=round(intrinsic, 2),
        is_in_the_money=True,
        exercised=True,
        settlement_mode=mode,
        exercise_stt=exercise_stt,
        gross_pnl=round(gross, 2),
        net_pnl_after_exercise_stt=round(gross - entry_charges - exercise_stt, 2),
        warning=warn,
    )
