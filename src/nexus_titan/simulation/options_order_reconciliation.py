"""Offline-only multi-fragment options order reconciliation.

Consumes research simulation fragments, NOT broker executions. The resulting
cash and inventory are a *scenario projection*, not an actual shadow-account
transaction, trade P&L, margin approval, or authorization for live orders.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from nexus_titan.cost.charges import IndianCostConfig, calculate_indian_trade_costs
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.simulation.options_research_execution import OptionResearchFill

_INDIA = ZoneInfo("Asia/Kolkata")
_TOLERANCE = 0.011


class OptionsReconciliationError(ValueError):
    """An entire research-order statement was rejected; no state changed."""


@dataclass(frozen=True, slots=True)
class ResearchFillEvent:
    event_id: str
    observed_at: datetime
    fragment: OptionResearchFill


@dataclass(frozen=True, slots=True)
class ResearchOptionsOrderStatement:
    order_id: str
    side: Literal["BUY", "SELL"]
    requested_quantity: int
    filled_quantity: int
    remaining_quantity: int
    fill_count: int
    unfilled_attempt_count: int
    status: Literal["FILLED", "PARTIAL", "UNFILLED"]
    average_fill_price: float | None
    filled_notional: float
    fragment_fee_sum: float
    recomputed_order_fee: float
    conservative_fee_reserve: float
    fee_model_difference: float
    total_execution_shortfall: float
    total_estimated_friction: float
    starting_cash: float
    projected_cash: float
    starting_inventory_quantity: int
    projected_inventory_quantity: int
    cost_schedule_version: str
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


def _int(name: str, value: int, *, zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if zero else 1):
        raise OptionsReconciliationError(f"{name} must be a {'non-negative' if zero else 'positive'} integer")


def _finite(name: str, value: float, *, zero: bool = True) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < (0 if zero else 0.000000001):
        raise OptionsReconciliationError(f"{name} must be finite and {'non-negative' if zero else 'positive'}")


def reconcile_options_research_order(
    events: list[ResearchFillEvent] | tuple[ResearchFillEvent, ...],
    *,
    order_id: str,
    contract: PointInTimeContractSpec,
    strike: float,
    option_type: Literal["CE", "PE"],
    side: Literal["BUY", "SELL"],
    requested_lots: int,
    starting_cash: float = 50_000.0,
    starting_inventory_quantity: int = 0,
    cost_config: IndianCostConfig | None = None,
    max_events: int = 1000,
) -> ResearchOptionsOrderStatement:
    """Reconcile one single-day research order, with zero overfills/replay.

    Each new simulation fragment's requested_quantity must equal the remaining
    quantity from previous attempts. Fees from each *filled* fragment are
    recomputed against the explicit charge schedule, plus a separate aggregate
    VWAP order-cost estimate. The higher estimate is reserved to avoid treating
    one broker's fee-rounding convention as verified.

    A SELL projection requires pre-existing option inventory (long-only). No
    naked short options, real broker balances or real orders are supported.
    """
    if not isinstance(order_id, str) or not order_id.strip():
        raise OptionsReconciliationError("order_id is required")
    if not isinstance(contract, PointInTimeContractSpec) or contract.segment != "OPTIONS" or contract.exchange.strip().upper() != "NSE":
        raise OptionsReconciliationError("NSE OPTIONS metadata is required")
    if not contract.source_verified or not contract.source_reference:
        raise OptionsReconciliationError("Reviewed contract source declaration required")
    if contract.expiry_date is None:
        raise OptionsReconciliationError("Contract expiry required")
    if option_type not in ("CE", "PE") or side not in ("BUY", "SELL"):
        raise OptionsReconciliationError("Invalid option_type or side")
    _finite("strike", strike, zero=False)
    _int("requested_lots", requested_lots)
    _int("starting_inventory_quantity", starting_inventory_quantity, zero=True)
    _int("max_events", max_events)
    _finite("starting_cash", starting_cash, zero=False)
    if not isinstance(events, (tuple, list)):
        raise OptionsReconciliationError("events must be a list or tuple")
    if not events or len(events) > max_events:
        raise OptionsReconciliationError("At least one event and bounded max_events required")
    if cost_config is not None and not isinstance(cost_config, IndianCostConfig):
        raise OptionsReconciliationError("Invalid cost schedule configuration")
    fees_config = cost_config or IndianCostConfig()

    requested = requested_lots * contract.lot_size
    if requested_lots > contract.max_lots_per_trade or requested > contract.freeze_quantity:
        raise OptionsReconciliationError("Requested order exceeds lot/freeze restrictions")
    if starting_inventory_quantity % contract.lot_size:
        raise OptionsReconciliationError("Initial inventory must be lot-aligned")
    if side == "SELL" and starting_inventory_quantity < requested:
        raise OptionsReconciliationError("SELL requires sufficient pre-existing long-option inventory")

    remaining = requested
    filled = 0
    executed_notional = 0.0
    per_fill_charges = 0.0
    shortfall = 0.0
    fill_count = no_fill_count = 0
    seen: set[str] = set()
    last_timestamp: datetime | None = None
    first_session_date = None

    for index, event in enumerate(events):
        if not isinstance(event, ResearchFillEvent):
            raise OptionsReconciliationError(f"Event {index}: invalid research fill event")
        if not isinstance(event.event_id, str) or not event.event_id.strip():
            raise OptionsReconciliationError(f"Event {index}: event_id required")
        if event.event_id in seen:
            raise OptionsReconciliationError(f"Event {index}: duplicate/replayed event_id")
        seen.add(event.event_id)
        t = event.observed_at
        if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
            raise OptionsReconciliationError(f"Event {index}: timestamp must be timezone-aware")
        utc = t.astimezone(timezone.utc)
        if last_timestamp is not None and utc <= last_timestamp:
            raise OptionsReconciliationError(f"Event {index}: timestamps must be strictly increasing")
        last_timestamp = utc
        local_date = t.astimezone(_INDIA).date()
        if first_session_date is None:
            first_session_date = local_date
        if local_date != first_session_date:
            raise OptionsReconciliationError("Research order cannot span multiple India trading dates")
        if not contract.effective_from <= local_date <= contract.effective_to or local_date > contract.expiry_date:
            raise OptionsReconciliationError(f"Event {index}: contract metadata expired or ineffective")

        frag = event.fragment
        if not isinstance(frag, OptionResearchFill):
            raise OptionsReconciliationError(f"Event {index}: OptionResearchFill required")
        if frag.option_type != option_type or frag.side != side or frag.strike != strike:
            raise OptionsReconciliationError(f"Event {index}: option identity/side mismatch")
        if frag.approved_for_strategy_promotion is not False or frag.live_orders_transmitted != 0:
            raise OptionsReconciliationError(f"Event {index}: promotion/live order boundary violated")
        for name in ("requested_quantity", "filled_quantity", "remaining_quantity"):
            _int(f"Event {index} {name}", getattr(frag, name), zero=name != "requested_quantity")
        if frag.requested_quantity != remaining:
            raise OptionsReconciliationError(f"Event {index}: requested quantity must equal remaining order quantity")
        if frag.filled_quantity > remaining or frag.remaining_quantity != remaining - frag.filled_quantity:
            raise OptionsReconciliationError(f"Event {index}: overfill or residual mismatch")
        if frag.filled_quantity % contract.lot_size or frag.remaining_quantity % contract.lot_size:
            raise OptionsReconciliationError(f"Event {index}: fragment quantity not lot-aligned")

        if frag.filled_quantity == 0:
            if frag.status != "UNFILLED" or frag.execution_price is not None or frag.fees_breakdown is not None:
                raise OptionsReconciliationError(f"Event {index}: unfilled outcome inconsistent")
            if any(abs(v) > _TOLERANCE for v in (frag.notional, frag.estimated_fees, frag.execution_shortfall_vs_mid, frag.total_estimated_friction)):
                raise OptionsReconciliationError(f"Event {index}: phantom unfilled charges")
            no_fill_count += 1
            continue

        if frag.status != ("FILLED" if frag.remaining_quantity == 0 else "PARTIAL"):
            raise OptionsReconciliationError(f"Event {index}: inconsistent fragment fill status")
        _finite("execution_price", frag.execution_price, zero=False)
        price = float(frag.execution_price)
        _finite("notional", frag.notional)
        _finite("estimated_fees", frag.estimated_fees)
        if abs(frag.notional - round(price * frag.filled_quantity, 2)) > _TOLERANCE:
            raise OptionsReconciliationError(f"Event {index}: notional does not reconcile to execution")
        expected_fee = calculate_indian_trade_costs(
            side, price, frag.filled_quantity, "OPTIONS", fees_config
        )
        if frag.fees_breakdown != expected_fee or abs(frag.estimated_fees - expected_fee.total_charges) > _TOLERANCE:
            raise OptionsReconciliationError(f"Event {index}: fragment fees differ from recomputed cost schedule")
        if not isinstance(frag.execution_shortfall_vs_mid, (int, float)) or not math.isfinite(frag.execution_shortfall_vs_mid):
            raise OptionsReconciliationError(f"Event {index}: invalid execution shortfall")
        if not isinstance(frag.total_estimated_friction, (int, float)) or not math.isfinite(frag.total_estimated_friction):
            raise OptionsReconciliationError(f"Event {index}: invalid total friction")
        if abs(frag.total_estimated_friction - round(frag.estimated_fees + frag.execution_shortfall_vs_mid, 2)) > _TOLERANCE:
            raise OptionsReconciliationError(f"Event {index}: friction double-count/mismatch")
        executed_notional += price * frag.filled_quantity
        per_fill_charges += expected_fee.total_charges
        shortfall += frag.execution_shortfall_vs_mid
        remaining -= frag.filled_quantity
        filled += frag.filled_quantity
        fill_count += 1

    if filled:
        vwap = executed_notional / filled
        order_fees = calculate_indian_trade_costs(side, vwap, filled, "OPTIONS", fees_config).total_charges
        total_notional = round(executed_notional, 2)
        fragment_fees = round(per_fill_charges, 2)
        # Reserve the worse of order-level and per-fragment fee models.
        reserved_fees = max(order_fees, fragment_fees)
        signed_cashflow = -total_notional - reserved_fees if side == "BUY" else total_notional - reserved_fees
    else:
        vwap = None
        total_notional = fragment_fees = order_fees = reserved_fees = 0.0
        signed_cashflow = 0.0
    projected_cash = round(starting_cash + signed_cashflow, 2)
    if projected_cash < -_TOLERANCE:
        raise OptionsReconciliationError("Insufficient virtual cash for simulated premium and fees")
    projected_inventory = starting_inventory_quantity + (filled if side == "BUY" else -filled)
    return ResearchOptionsOrderStatement(
        order_id=order_id.strip(), side=side, requested_quantity=requested,
        filled_quantity=filled, remaining_quantity=remaining, fill_count=fill_count,
        unfilled_attempt_count=no_fill_count,
        status="UNFILLED" if filled == 0 else "FILLED" if remaining == 0 else "PARTIAL",
        average_fill_price=round(vwap, 8) if vwap is not None else None,
        filled_notional=total_notional, fragment_fee_sum=fragment_fees,
        recomputed_order_fee=order_fees, conservative_fee_reserve=reserved_fees,
        fee_model_difference=round(fragment_fees - order_fees, 2),
        total_execution_shortfall=round(shortfall, 2),
        total_estimated_friction=round(shortfall + reserved_fees, 2),
        starting_cash=float(starting_cash), projected_cash=projected_cash,
        starting_inventory_quantity=starting_inventory_quantity,
        projected_inventory_quantity=projected_inventory,
        cost_schedule_version=fees_config.version,
    )
