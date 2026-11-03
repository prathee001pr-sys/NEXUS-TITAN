"""Stage58: read-only synthetic multi-snapshot NSE F&O execution stress analysis.

Composes the existing PointInTimeContractSpec, MarketCalendar,
MicrostructureSimulator and IndianCostConfig. Data source declarations are
CALLER-ASSERTED, not independently authenticated. No trade/order/ledger/API
writes, no broker connectivity, and no verified live market quotes.

This model estimates fill fragments and a conservative cost reserve, not
margin, mark-to-market P&L, a contract note, strategy alpha or risk permission.
A snapshot's traded volume/OI is NOT treated as executable depth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from nexus_titan.cost.charges import (
    IndianCostConfig, TradeCostBreakdown, calculate_indian_trade_costs,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.virtual.microstructure import (
    MicrostructureConfig, MicrostructureSimulator, OrderBookSnapshot,
)


class Stage58ExecutionBlocked(ValueError):
    """Synthetic evidence is missing, incompatible, stale or unsupported."""


@dataclass(frozen=True, slots=True)
class Stage58DisplayedObservation:
    event_id: str
    observed_at: datetime
    book: OrderBookSnapshot
    depth_source_reference: str
    depth_source_declared_verified: bool
    queue_traded_volume: int = 0


@dataclass(frozen=True, slots=True)
class Stage58ExecutionFragment:
    event_id: str
    observed_at: datetime
    filled_quantity: int
    remaining_quantity: int
    status: Literal["FILLED", "PARTIAL", "UNFILLED"]
    reason: str
    execution_price: float | None
    notional: float
    fees: TradeCostBreakdown | None
    mid_shortfall: float
    spread_cost_per_unit: float
    impact_slippage_per_unit: float
    latency_drift_per_unit: float
    live_orders_transmitted: int = 0


@dataclass(frozen=True, slots=True)
class Stage58ExecutionScenario:
    segment: Literal["FUTURES", "OPTIONS"]
    side: Literal["BUY", "SELL"]
    requested_lots: int
    requested_quantity: int
    observed_snapshots: int
    filled_quantity: int
    remaining_quantity: int
    status: Literal["FILLED", "PARTIAL", "UNFILLED"]
    average_fill_price: float | None
    filled_notional: float
    fragment_fees_sum: float
    aggregate_fee_estimate: float
    conservative_fee_reserve: float
    signed_mid_shortfall: float
    conservative_execution_friction: float
    fill_ratio: float
    schedule_version: str
    fragments: tuple[Stage58ExecutionFragment, ...]
    # PERMANENTLY FALSE: neither this scenario nor its fill events are trades.
    depth_provenance_independently_authenticated: bool = False
    official_contract_master_independently_authenticated: bool = False
    official_fees_or_margin_verified: bool = False
    capital_reserved_in_any_account: bool = False
    broker_fill_reconciliation_verified: bool = False
    external_human_identity_verified: bool = False
    independent_risk_veto_enforced: bool = False
    approved_for_strategy_promotion: bool = False
    live_trading_enabled: bool = False
    live_orders_transmitted: int = 0
    production_ready: bool = False


def _aware(value: object) -> bool:
    return (isinstance(value, datetime) and value.tzinfo is not None
            and value.utcoffset() is not None)


def _limit_price_is_tick_aligned(value: float, tick: float) -> bool:
    # Avoid accepting 100.001 as a valid 0.05-increment option limit.
    multiple = value / tick
    return abs(multiple - round(multiple)) <= 1e-8


def simulate_stage58_synthetic_execution(
    observations: tuple[Stage58DisplayedObservation, ...],
    *,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    side: Literal["BUY", "SELL"],
    requested_lots: int,
    costs: IndianCostConfig,
    microstructure: MicrostructureConfig = MicrostructureConfig(),
    order_type: Literal["MARKET", "LIMIT"] = "MARKET",
    limit_price: float | None = None,
    max_spread_bps: int = 250,
    max_observations: int = 40,
) -> Stage58ExecutionScenario:
    """Simulate at most one fragment per strictly ordered displayed snapshot.

    Never infer quote depth from OHLCV volume, never reuse one snapshot as
    several separate depth replenishments, and never auto-continue an order
    past a missing/stale/off-session contract record. Malformed observations
    reject the ENTIRE scenario before any fragment is emitted.
    """
    if (not isinstance(contract, PointInTimeContractSpec)
            or contract.exchange.strip().upper() != "NSE"
            or contract.segment not in ("FUTURES", "OPTIONS")
            or not contract.source_verified or not contract.source_reference):
        raise Stage58ExecutionBlocked("Declared reviewed NSE F&O contract metadata required")
    if (not isinstance(calendar, MarketCalendar)
            or calendar.timezone_name != "Asia/Kolkata"):
        raise Stage58ExecutionBlocked("Explicit NSE India trading calendar required")
    if not isinstance(costs, IndianCostConfig):
        raise Stage58ExecutionBlocked("Explicit Indian cost schedule required")
    if not isinstance(microstructure, MicrostructureConfig):
        raise Stage58ExecutionBlocked("Explicit microstructure settings required")
    if (side not in ("BUY", "SELL") or order_type not in ("MARKET", "LIMIT")
            or type(requested_lots) is not int or not 1 <= requested_lots
            or requested_lots > contract.max_lots_per_trade
            or requested_lots * contract.lot_size > contract.freeze_quantity):
        raise Stage58ExecutionBlocked("Unsupported side, lots or contract order/freeze limit")
    if (type(max_observations) is not int or not 1 <= max_observations <= 100
            or type(max_spread_bps) is not int or not 1 <= max_spread_bps <= 2000):
        raise Stage58ExecutionBlocked("Observation/spread cap configuration invalid")
    if (not isinstance(observations, tuple) or not observations
            or len(observations) > max_observations):
        raise Stage58ExecutionBlocked("Nonempty bounded tuple of displayed snapshots required")
    if order_type == "MARKET" and limit_price is not None:
        raise Stage58ExecutionBlocked("MARKET request must not set a limit")
    if order_type == "LIMIT" and (
        type(limit_price) not in (int, float)
        or not math.isfinite(limit_price)
        or limit_price <= 0
        or not _limit_price_is_tick_aligned(float(limit_price), contract.tick_size)
    ):
        raise Stage58ExecutionBlocked("LIMIT price must be a positive exact instrument tick")
    # Validate the full trajectory before simulating any hypothetical fills.
    seen: set[str] = set()
    last: datetime | None = None
    for item in observations:
        if not isinstance(item, Stage58DisplayedObservation):
            raise Stage58ExecutionBlocked("Each snapshot requires source/depth metadata")
        if (not isinstance(item.event_id, str) or not item.event_id.strip()
                or len(item.event_id) > 80 or item.event_id in seen):
            raise Stage58ExecutionBlocked("Missing or repeated bounded snapshot event ID")
        seen.add(item.event_id)
        if (not _aware(item.observed_at)
                or not isinstance(item.book, OrderBookSnapshot)):
            raise Stage58ExecutionBlocked("Time-aware displayed order book required")
        stamp = datetime.fromisoformat(item.book.timestamp.replace("Z", "+00:00"))
        if item.observed_at != stamp or (last is not None and item.observed_at <= last):
            raise Stage58ExecutionBlocked("Depth and book clock must match and increase strictly")
        last = item.observed_at
        if (not isinstance(item.depth_source_reference, str)
                or not item.depth_source_reference.strip()
                or len(item.depth_source_reference) > 200
                or type(item.depth_source_declared_verified) is not bool
                or not item.depth_source_declared_verified):
            raise Stage58ExecutionBlocked("Declared independently collected displayed-depth source required")
        if (type(item.queue_traded_volume) is not int
                or item.queue_traded_volume < 0):
            raise Stage58ExecutionBlocked("Queue traded quantity must be a nonnegative integer")
        if (item.book.symbol != contract.symbol
                or item.book.tick_size != contract.tick_size):
            raise Stage58ExecutionBlocked("Displayed book symbol/tick mismatch with contract")
        day = item.observed_at.astimezone(calendar.zone).date()
        if (not contract.effective_from <= day <= contract.effective_to
                or contract.expiry_date is None or day > contract.expiry_date):
            raise Stage58ExecutionBlocked("Quote outside point-in-time contract/expiry window")
        if not calendar.is_open(item.observed_at):
            raise Stage58ExecutionBlocked("Snapshot outside supplied NSE trading session")
        if item.book.quote_age_ms > microstructure.max_quote_age_ms:
            raise Stage58ExecutionBlocked("Stale displayed quote; cannot simulate hypothetical fill")
        midpoint2 = item.book.bid_price + item.book.ask_price
        if (item.book.ask_price - item.book.bid_price) * 20000 > midpoint2 * max_spread_bps:
            raise Stage58ExecutionBlocked("Displayed quote spread exceeds configured cap")
        # Verify the explicit cost schedule is not FUTURE effective relative
        # to this historical snapshot. Official tariff authenticity remains
        # unverified and the caller must check applicability separately.
        try:
            from datetime import date
            effective = date.fromisoformat(costs.effective_date)
        except (AttributeError, ValueError, TypeError) as exc:
            raise Stage58ExecutionBlocked("Invalid explicit cost schedule effective date") from exc
        if effective > day:
            raise Stage58ExecutionBlocked("Future fee tariff cannot be applied to historical snapshot")

    quantity = requested_lots * contract.lot_size
    remaining = quantity
    simulator = MicrostructureSimulator(microstructure)
    fragments: list[Stage58ExecutionFragment] = []
    total_notional = total_fee_fragments = total_shortfall = pessimistic_shortfall = 0.0
    for item in observations:
        if remaining == 0:
            break
        outcome = simulator.evaluate_order_against_book(
            side=side, order_type=order_type, requested_qty=remaining,
            lot_size=contract.lot_size, book=item.book, limit_price=limit_price,
            queue_traded_volume=item.queue_traded_volume,
        )
        filled = outcome.filled_qty if outcome.accepted_for_fill else 0
        if (type(filled) is not int or filled < 0 or filled > remaining
                or filled % contract.lot_size != 0):
            raise Stage58ExecutionBlocked("Simulator returned invalid lot-aligned fragment")
        remaining -= filled
        fees = calculate_indian_trade_costs(
            side, outcome.execution_price, filled, contract.segment, costs,
        ) if filled else None
        mid = item.book.mid_price
        notional = round(outcome.execution_price * filled, 2) if filled else 0.0
        shortfall = round(
            ((outcome.execution_price - mid) if side == "BUY"
             else (mid - outcome.execution_price)) * filled, 2,
        ) if filled else 0.0
        total_notional += notional
        total_fee_fragments += fees.total_charges if fees else 0.0
        total_shortfall += shortfall
        pessimistic_shortfall += max(0.0, shortfall)
        fragments.append(Stage58ExecutionFragment(
            event_id=item.event_id, observed_at=item.observed_at,
            filled_quantity=filled, remaining_quantity=remaining,
            status=("UNFILLED" if not filled else "FILLED" if not remaining else "PARTIAL"),
            reason=outcome.status_reason,
            execution_price=outcome.execution_price if filled else None,
            notional=notional, fees=fees,
            mid_shortfall=shortfall,
            spread_cost_per_unit=outcome.spread_cost_per_unit if filled else 0.0,
            impact_slippage_per_unit=outcome.impact_slippage_per_unit if filled else 0.0,
            latency_drift_per_unit=outcome.latency_drift_per_unit if filled else 0.0,
        ))

    total_filled = quantity - remaining
    avg_price = round(total_notional / total_filled, 8) if total_filled else None
    aggregate = calculate_indian_trade_costs(
        side, avg_price, total_filled, contract.segment, costs,
    ).total_charges if total_filled else 0.0
    fee_sum = round(total_fee_fragments, 2)
    # Per-fragment brokerage / tax rounding can differ from one aggregate
    # calculation. Reserve the higher ONE, not their sum (double counting).
    reserve = max(fee_sum, aggregate)
    return Stage58ExecutionScenario(
        segment=contract.segment, side=side,
        requested_lots=requested_lots, requested_quantity=quantity,
        observed_snapshots=len(observations),
        filled_quantity=total_filled, remaining_quantity=remaining,
        status="UNFILLED" if total_filled == 0 else "FILLED" if remaining == 0 else "PARTIAL",
        average_fill_price=avg_price, filled_notional=round(total_notional, 2),
        fragment_fees_sum=fee_sum, aggregate_fee_estimate=aggregate,
        conservative_fee_reserve=reserve,
        signed_mid_shortfall=round(total_shortfall, 2),
        conservative_execution_friction=round(reserve + pessimistic_shortfall, 2),
        fill_ratio=round(total_filled / quantity, 8),
        schedule_version=costs.version, fragments=tuple(fragments),
    )
