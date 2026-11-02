"""Option research execution bridge over verified snapshot history.

Pure offline simulation. No broker, order book collector, permissions,
strategy promotion, or automatic live trading connection is provided.
Displayed bid/ask depth is mandatory independent evidence; a snapshot's
traded volume/open interest must NEVER be used as executable depth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from nexus_titan.cost.charges import (
    IndianCostConfig, TradeCostBreakdown, calculate_indian_trade_costs,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import (
    ResearchOptionChainHistory, inspect_option_chain_history,
)
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.virtual.microstructure import (
    MicrostructureConfig, MicrostructureSimulator, OrderBookSnapshot,
    SimulatedExecutionOutcome,
)


class OptionResearchExecutionError(ValueError):
    """A validation gate rejected the offline research order."""


@dataclass(frozen=True, slots=True)
class OptionDisplayedDepth:
    """Independently sourced top-of-book quantities for one option instrument.

    source_declared_verified is operator-provided evidence metadata; it does
    not independently authenticate the vendor or prove displayed liquidity.
    """

    as_of: datetime
    bid_quantity: int
    ask_quantity: int
    source_reference: str
    source_declared_verified: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("depth.as_of must be timezone-aware")
        for name in ("bid_quantity", "ask_quantity"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative whole number")
        if not isinstance(self.source_reference, str) or not self.source_reference.strip():
            raise ValueError("depth.source_reference is required")
        if not isinstance(self.source_declared_verified, bool):
            raise ValueError("source_declared_verified must be boolean")


@dataclass(frozen=True, slots=True)
class OptionResearchFill:
    """One simulated fill fragment. Never a real-world trade or P&L."""

    status: Literal["FILLED", "PARTIAL", "UNFILLED"]
    reason: str
    option_type: Literal["CE", "PE"]
    strike: float
    side: Literal["BUY", "SELL"]
    requested_quantity: int
    filled_quantity: int
    remaining_quantity: int
    execution_price: float | None
    notional: float
    estimated_fees: float
    execution_shortfall_vs_mid: float
    total_estimated_friction: float
    fees_breakdown: TradeCostBreakdown | None
    spread_cost_per_unit: float
    impact_slippage_per_unit: float
    latency_drift_per_unit: float
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def simulate_historical_option_fill(
    history: ResearchOptionChainHistory,
    *,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    observed_at: datetime,
    strike: float,
    option_type: Literal["CE", "PE"],
    side: Literal["BUY", "SELL"],
    lots: int,
    depth: OptionDisplayedDepth,
    order_type: Literal["MARKET", "LIMIT"] = "MARKET",
    limit_price: float | None = None,
    microstructure: MicrostructureConfig | None = None,
    costs: IndianCostConfig | None = None,
    max_depth_quote_skew_ms: float = 2000.0,
) -> OptionResearchFill:
    """Simulate one fragment using supplied, timestamp-matched top-of-book depth.

    History is fully revalidated before selecting a quote. This is deliberately
    conservative; order-level risk permissions, actual queue/fill evidence,
    brokerage reconciliation and trade lifecycle remain unimplemented here.
    """
    if not isinstance(history, ResearchOptionChainHistory):
        raise OptionResearchExecutionError("Validated research history is required")
    if history.approved_for_strategy_promotion is not False:
        raise OptionResearchExecutionError("History cannot authorize strategy promotion")
    if not _aware(observed_at):
        raise OptionResearchExecutionError("observed_at must be timezone-aware")
    if option_type not in ("CE", "PE") or side not in ("BUY", "SELL"):
        raise OptionResearchExecutionError("option_type or side is invalid")
    if order_type not in ("MARKET", "LIMIT"):
        raise OptionResearchExecutionError("order_type must be MARKET or LIMIT")
    if isinstance(lots, bool) or not isinstance(lots, int) or lots < 1:
        raise OptionResearchExecutionError("lots must be a positive integer")
    if isinstance(strike, bool) or not isinstance(strike, (int, float)) or not math.isfinite(strike) or strike <= 0:
        raise OptionResearchExecutionError("strike must be finite and positive")
    if not isinstance(contract, PointInTimeContractSpec):
        raise OptionResearchExecutionError("Point-in-time contract is required")
    if contract.segment != "OPTIONS" or contract.exchange.strip().upper() != "NSE":
        raise OptionResearchExecutionError("NSE OPTIONS metadata is required")
    if lots > contract.max_lots_per_trade or lots * contract.lot_size > contract.freeze_quantity:
        raise OptionResearchExecutionError("Lots exceed contract order/freeze limit")
    if not isinstance(depth, OptionDisplayedDepth) or not depth.source_declared_verified:
        raise OptionResearchExecutionError("Independently sourced depth declaration is required")
    if order_type == "MARKET" and limit_price is not None:
        raise OptionResearchExecutionError("MARKET order must not include limit_price")
    if order_type == "LIMIT" and limit_price is None:
        raise OptionResearchExecutionError("LIMIT order requires limit_price")
    if microstructure is not None and not isinstance(microstructure, MicrostructureConfig):
        raise OptionResearchExecutionError("Invalid microstructure configuration")
    if costs is not None and not isinstance(costs, IndianCostConfig):
        raise OptionResearchExecutionError("Invalid transaction-cost configuration")
    if (isinstance(max_depth_quote_skew_ms, bool)
            or not isinstance(max_depth_quote_skew_ms, (int, float))
            or not math.isfinite(max_depth_quote_skew_ms)
            or max_depth_quote_skew_ms < 0):
        raise OptionResearchExecutionError("Depth/quote synchronization limit must be finite and non-negative")

    # A caller can instantiate the frozen ResearchOptionChainHistory directly.
    # Rechecking stops such a forged instance bypassing the Stage 1-15/PR8 gates.
    audit = inspect_option_chain_history(
        history.snapshots, contract=contract, calendar=calendar,
        interval_minutes=history.interval_minutes,
    )
    if not audit.is_valid or audit.expected_slots != history.expected_slots:
        raise OptionResearchExecutionError("Historical data integrity rejected: " + "; ".join(audit.issues[:5]))
    target = observed_at.astimezone(timezone.utc)
    matches = [
        snapshot for snapshot in history.snapshots
        if snapshot.observed_at.astimezone(timezone.utc) == target
    ]
    if len(matches) != 1:
        raise OptionResearchExecutionError("Exactly one validated snapshot must match observed_at")
    snapshot = matches[0]
    selected = [
        quote for quote in snapshot.quotes
        if quote.option_type == option_type and quote.strike == strike
    ]
    if len(selected) != 1:
        raise OptionResearchExecutionError("Exactly one option leg must match strike and option_type")
    quote = selected[0]

    cfg = microstructure or MicrostructureConfig()
    if depth.as_of > observed_at:
        raise OptionResearchExecutionError("Displayed depth timestamp is after observation")
    if (observed_at - depth.as_of).total_seconds() * 1000 > cfg.max_quote_age_ms:
        raise OptionResearchExecutionError("Displayed depth is stale")
    quote_when = datetime.fromisoformat(quote.timestamp.replace("Z", "+00:00"))
    # The data at this instant must be a coherent top-of-book observation; do
    # not combine unrelated timestamps or treat OHLCV volume as displayed qty.
    if abs((depth.as_of - quote_when).total_seconds()) * 1000 > max_depth_quote_skew_ms:
        raise OptionResearchExecutionError("Displayed depth and option quote are unsynchronized")

    book = OrderBookSnapshot(
        symbol=quote.symbol,
        timestamp=quote.timestamp,
        bid_price=quote.bid,
        ask_price=quote.ask,
        bid_qty=depth.bid_quantity,
        ask_qty=depth.ask_quantity,
        last_traded_price=quote.ltp,
        quote_age_ms=(observed_at - quote_when).total_seconds() * 1000,
        tick_size=contract.tick_size,
    )
    qty = lots * contract.lot_size
    outcome: SimulatedExecutionOutcome = MicrostructureSimulator(cfg).evaluate_order_against_book(
        side=side, order_type=order_type, requested_qty=qty,
        lot_size=contract.lot_size, book=book, limit_price=limit_price,
        queue_traded_volume=0,  # Never invent a real queue-volume observation.
    )
    filled = outcome.filled_qty if outcome.accepted_for_fill else 0
    if not filled:
        return OptionResearchFill(
            status="UNFILLED", reason=outcome.status_reason,
            option_type=option_type, strike=float(strike), side=side,
            requested_quantity=qty, filled_quantity=0,
            remaining_quantity=qty, execution_price=None,
            notional=0.0, estimated_fees=0.0,
            execution_shortfall_vs_mid=0.0, total_estimated_friction=0.0,
            fees_breakdown=None, spread_cost_per_unit=0.0,
            impact_slippage_per_unit=0.0, latency_drift_per_unit=0.0,
        )
    fees = calculate_indian_trade_costs(
        side, outcome.execution_price, filled, "OPTIONS", costs or IndianCostConfig()
    )
    notional = round(outcome.execution_price * filled, 2)
    mid = (quote.bid + quote.ask) / 2
    shortfall = round(
        (outcome.execution_price - mid) * filled
        if side == "BUY" else (mid - outcome.execution_price) * filled,
        2,
    )
    # Shortfall already incorporates spread/slippage. Do not count the spread
    # a second time when computing estimated total friction.
    friction = round(fees.total_charges + shortfall, 2)
    return OptionResearchFill(
        status="FILLED" if filled == qty else "PARTIAL",
        reason=outcome.status_reason, option_type=option_type, strike=float(strike),
        side=side, requested_quantity=qty, filled_quantity=filled,
        remaining_quantity=qty-filled, execution_price=outcome.execution_price,
        notional=notional, estimated_fees=fees.total_charges,
        execution_shortfall_vs_mid=shortfall,
        total_estimated_friction=friction, fees_breakdown=fees,
        spread_cost_per_unit=outcome.spread_cost_per_unit,
        impact_slippage_per_unit=outcome.impact_slippage_per_unit,
        latency_drift_per_unit=outcome.latency_drift_per_unit,
    )
