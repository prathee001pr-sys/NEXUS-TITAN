"""Intraday Microstructure Simulator, Calibrated Slippage/Queue/Market Impact, and ₹50,000 Shadow Account Runner (Workstreams I, J, L, P)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from nexus_titan.cost.charges import InstrumentType
from nexus_titan.risk.portfolio_risk import round_to_tick
from nexus_titan.virtual.order_manager import OrderSide, OrderType, VirtualAccount, VirtualOrder


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Top-of-book and displayed depth snapshot with quote age and circuit/halt flags (Workstream I)."""

    symbol: str
    timestamp: str
    bid_price: float
    ask_price: float
    bid_qty: int
    ask_qty: int
    last_traded_price: float
    quote_age_ms: float = 50.0
    volatility_annualized: float = 0.15
    is_halted: bool = False
    is_circuit_locked: bool = False
    tick_size: float = 0.05

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("Order book symbol is required.")
        try:
            parsed = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ValueError("Order book timestamp must be ISO-8601 with an explicit timezone.") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("Order book timestamp must include a UTC offset/timezone.")
        for name, value in (("bid_price", self.bid_price), ("ask_price", self.ask_price),
                            ("last_traded_price", self.last_traded_price),
                            ("quote_age_ms", self.quote_age_ms),
                            ("volatility_annualized", self.volatility_annualized),
                            ("tick_size", self.tick_size)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        if min(self.bid_price, self.ask_price, self.last_traded_price, self.tick_size) <= 0:
            raise ValueError("Book prices and tick_size must be positive.")
        if self.bid_price > self.ask_price:
            raise ValueError("Order book is crossed: bid_price cannot exceed ask_price.")
        if self.quote_age_ms < 0 or self.volatility_annualized < 0:
            raise ValueError("Quote age and annualized volatility cannot be negative.")
        for name, value in (("bid_qty", self.bid_qty), ("ask_qty", self.ask_qty)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")

    @property
    def mid_price(self) -> float:
        return 0.5 * (self.bid_price + self.ask_price)

    @property
    def spread(self) -> float:
        return round(self.ask_price - self.bid_price, 4)


@dataclass(frozen=True)
class MicrostructureConfig:
    """Conservative execution calibration settings (Workstreams I, J, L)."""

    max_quote_age_ms: float = 2_000.0
    arrival_latency_ms: float = 120.0
    max_participation_rate: float = 0.25  # Fill at most 25% of displayed top-of-book depth per tick
    impact_coefficient_bps: float = 15.0  # Square-root market impact coefficient in bps
    queue_ahead_fraction: float = 0.50    # Fraction of displayed depth ahead of a resting limit order
    allow_optimistic_mid_fills: bool = False

    def __post_init__(self) -> None:
        if self.allow_optimistic_mid_fills:
            raise ValueError("Optimistic mid-price fills are blocked by default per Workstream J.")
        for name, value in (("max_quote_age_ms", self.max_quote_age_ms),
                            ("arrival_latency_ms", self.arrival_latency_ms),
                            ("max_participation_rate", self.max_participation_rate),
                            ("impact_coefficient_bps", self.impact_coefficient_bps),
                            ("queue_ahead_fraction", self.queue_ahead_fraction)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        if (self.max_quote_age_ms <= 0 or self.arrival_latency_ms < 0
                or not 0 < self.max_participation_rate <= 1.0
                or self.impact_coefficient_bps < 0
                or not 0 <= self.queue_ahead_fraction <= 1.0):
            raise ValueError("Invalid quote age, latency, participation, impact, or queue setting.")


@dataclass(frozen=True)
class SimulatedExecutionOutcome:
    """Result of evaluating an order against an OrderBookSnapshot."""

    accepted_for_fill: bool
    filled_qty: int
    residual_qty: int
    execution_price: float
    spread_cost_per_unit: float
    impact_slippage_per_unit: float
    latency_drift_per_unit: float
    status_reason: str


class MicrostructureSimulator:
    """Simulate realistic spread crossing, queue priority, market impact, stale-quote rejection, and partial fills."""

    def __init__(self, config: MicrostructureConfig = MicrostructureConfig()) -> None:
        self.config = config

    def evaluate_order_against_book(
        self,
        *,
        side: Literal["BUY", "SELL"],
        order_type: Literal["MARKET", "LIMIT"],
        requested_qty: int,
        lot_size: int,
        book: OrderBookSnapshot,
        limit_price: float | None = None,
        queue_traded_volume: int = 0,
    ) -> SimulatedExecutionOutcome:
        if side not in ("BUY", "SELL"):
            raise ValueError("side must be exactly BUY or SELL.")
        if order_type not in ("MARKET", "LIMIT"):
            raise ValueError("order_type must be exactly MARKET or LIMIT.")
        if isinstance(requested_qty, bool) or not isinstance(requested_qty, int) or requested_qty < 1:
            raise ValueError("requested_qty must be a positive integer.")
        if isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size < 1 or requested_qty % lot_size != 0:
            raise ValueError("requested_qty must be a positive multiple of lot_size.")
        if isinstance(queue_traded_volume, bool) or not isinstance(queue_traded_volume, int) or queue_traded_volume < 0:
            raise ValueError("queue_traded_volume must be a non-negative integer.")
        if order_type == "LIMIT":
            if limit_price is None or isinstance(limit_price, bool) or not isinstance(limit_price, (int, float)) or not math.isfinite(limit_price) or limit_price <= 0:
                raise ValueError("LIMIT orders require a finite positive limit_price.")
            rounded_limit = round_to_tick(float(limit_price), book.tick_size)
            if abs(rounded_limit - float(limit_price)) > max(1e-9, book.tick_size * 1e-8):
                raise ValueError("limit_price must already align to the instrument tick size.")
        elif limit_price is not None:
            raise ValueError("limit_price is only valid for LIMIT orders.")
        if book.is_halted or book.is_circuit_locked:
            return SimulatedExecutionOutcome(
                False, 0, requested_qty, 0.0, 0.0, 0.0, 0.0,
                "REJECTED_OR_HELD: Market is halted or locked in upper/lower circuit.",
            )
        if book.quote_age_ms > self.config.max_quote_age_ms:
            return SimulatedExecutionOutcome(
                False, 0, requested_qty, 0.0, 0.0, 0.0, 0.0,
                f"STALE_QUOTE_BLOCKED: Quote age {book.quote_age_ms:.0f}ms exceeds {self.config.max_quote_age_ms:.0f}ms.",
            )
        if book.bid_price <= 0 or book.ask_price <= 0 or book.bid_price > book.ask_price:
            return SimulatedExecutionOutcome(
                False, 0, requested_qty, 0.0, 0.0, 0.0, 0.0,
                "INVALID_BOOK: Crossed or non-positive bid/ask prices.",
            )

        is_buy = side == "BUY"
        displayed_depth = book.ask_qty if is_buy else book.bid_qty
        touch_price = book.ask_price if is_buy else book.bid_price
        half_spread = 0.5 * (book.ask_price - book.bid_price)

        if order_type == "LIMIT":
            crosses_spread = (is_buy and limit_price >= book.ask_price) or (not is_buy and limit_price <= book.bid_price)
            if not crosses_spread:
                # Resting in queue: check whether traded volume clears the queue ahead
                resting_touch = (is_buy and limit_price >= book.bid_price) or (not is_buy and limit_price <= book.ask_price)
                if not resting_touch:
                    return SimulatedExecutionOutcome(
                        False, 0, requested_qty, 0.0, 0.0, 0.0, 0.0,
                        "RESTING_OUT_OF_TOUCH: Limit price away from best bid/ask.",
                    )
                same_side_depth = book.bid_qty if is_buy else book.ask_qty
                queue_ahead = math.ceil(same_side_depth * self.config.queue_ahead_fraction)
                available_after_queue = max(0, queue_traded_volume - queue_ahead)
                fill_lots = min(requested_qty, available_after_queue) // lot_size
                fill_qty = fill_lots * lot_size
                if fill_qty < lot_size:
                    return SimulatedExecutionOutcome(
                        False, 0, requested_qty, 0.0, 0.0, 0.0, 0.0,
                        f"QUEUE_WAITING: Queue ahead ({queue_ahead}) not cleared by traded volume ({queue_traded_volume}).",
                    )
                exec_px = round_to_tick(limit_price, book.tick_size)
                return SimulatedExecutionOutcome(
                    True, fill_qty, requested_qty - fill_qty, exec_px, 0.0, 0.0, 0.0,
                    "PASSIVE_QUEUE_FILL: Resting limit order filled after clearing queue.",
                )

        # Aggressive order crossing the spread (MARKET or marketable LIMIT)
        max_fillable = math.floor(displayed_depth * self.config.max_participation_rate)
        fill_lots = min(requested_qty, max_fillable) // lot_size
        fill_qty = fill_lots * lot_size
        if fill_qty < lot_size:
            return SimulatedExecutionOutcome(
                False, 0, requested_qty, 0.0, 0.0, 0.0, 0.0,
                f"INSUFFICIENT_DISPLAYED_LIQUIDITY: Top-of-book depth ({displayed_depth}) below participation cap for 1 lot ({lot_size}).",
            )

        participation = fill_qty / max(displayed_depth, 1)
        impact_bps = self.config.impact_coefficient_bps * math.sqrt(participation) * (book.volatility_annualized / 0.15)
        impact_per_unit = touch_price * (impact_bps / 10_000.0)
        latency_drift = touch_price * (book.volatility_annualized / math.sqrt(252 * 375 * 60_000)) * math.sqrt(self.config.arrival_latency_ms)

        raw_exec = touch_price + impact_per_unit + latency_drift if is_buy else max(book.tick_size, touch_price - impact_per_unit - latency_drift)
        exec_px = round_to_tick(raw_exec, book.tick_size)

        if order_type == "LIMIT" and limit_price is not None:
            if (is_buy and exec_px > limit_price) or (not is_buy and exec_px < limit_price):
                return SimulatedExecutionOutcome(
                    False, 0, requested_qty, 0.0, round(half_spread, 4), round(impact_per_unit, 4), round(latency_drift, 4),
                    "LIMIT_SLIPPAGE_GUARD: Market impact pushed fill price beyond limit_price.",
                )

        return SimulatedExecutionOutcome(
            True,
            fill_qty,
            requested_qty - fill_qty,
            exec_px,
            round(half_spread, 4),
            round(impact_per_unit, 4),
            round(latency_drift, 4),
            "AGGRESSIVE_SPREAD_CROSS_FILL",
        )


@dataclass(frozen=True)
class ShadowDailyStatement:
    """Daily reconciled statement for the ₹50,000 Shadow Account (Workstream P / PAPER-001..010)."""

    statement_date: str
    account_id: str
    starting_capital: float
    ending_equity: float
    cash_balance: float
    blocked_margin: float
    realized_pnl: float
    unrealized_pnl: float
    total_fees_paid: float
    orders_submitted: int
    orders_filled: int
    orders_partially_filled: int
    orders_rejected: int
    open_positions_count: int
    balance_discrepancy: float
    is_reconciled: bool
    live_orders_transmitted: int = 0


class ShadowPaperRunner:
    """Dedicated ₹50,000 Virtual Live / Shadow Mode runner combining VirtualAccount and MicrostructureSimulator (Workstream P)."""

    def __init__(
        self,
        *,
        starting_capital: float = 50_000.0,
        account_id: str = "TITAN-50K-SHADOW",
        microstructure: MicrostructureSimulator | None = None,
        state_dir: str | Path | None = "data/shadow_accounts",
    ) -> None:
        if starting_capital <= 0 or not math.isfinite(starting_capital):
            raise ValueError("Shadow account starting_capital must be positive.")
        self.account = VirtualAccount(
            account_id=account_id, starting_capital=starting_capital, state_dir=state_dir
        )
        self.simulator = microstructure or MicrostructureSimulator()

    def route_shadow_order(
        self,
        *,
        book: OrderBookSnapshot,
        side: Literal["BUY", "SELL"],
        quantity: int,
        order_type: Literal["MARKET", "LIMIT"] = "MARKET",
        instrument_type: InstrumentType = "EQUITY_DELIVERY",
        lot_size: int = 1,
        stop_price: float | None = None,
        target_price: float | None = None,
        limit_price: float | None = None,
        queue_traded_volume: int = 0,
    ) -> tuple[VirtualOrder, SimulatedExecutionOutcome]:
        """Submit a local shadow order and evaluate realistic microstructure fill/partial-fill."""
        indicative_entry = limit_price if order_type == "LIMIT" and limit_price else (
            book.ask_price if side == "BUY" else book.bid_price
        )
        order = self.account.submit_order(
            symbol=book.symbol,
            side=OrderSide(side),
            quantity=quantity,
            order_type=OrderType(order_type),
            limit_price=limit_price,
            stop_price=stop_price,
            target_price=target_price,
            instrument_type=instrument_type,
            lot_size=lot_size,
            entry_price=indicative_entry,
        )
        if order.state.value == "REJECTED":
            return order, SimulatedExecutionOutcome(
                False, 0, quantity, 0.0, 0.0, 0.0, 0.0, f"ORDER_REJECTED: {order.reject_reason}"
            )
        sim = self.simulator.evaluate_order_against_book(
            side=side,
            order_type=order_type,
            requested_qty=order.remaining_qty,
            lot_size=lot_size,
            book=book,
            limit_price=limit_price,
            queue_traded_volume=queue_traded_volume,
        )
        if sim.accepted_for_fill and sim.filled_qty > 0:
            order = self.account.execute_fill(
                order.order_id,
                fill_price=sim.execution_price,
                fill_qty=sim.filled_qty,
                idempotency_key=f"{order.order_id}:{book.timestamp}:{sim.filled_qty}",
            )
        return order, sim

    def generate_daily_statement(self, statement_date: str | None = None) -> ShadowDailyStatement:
        rec = self.account.reconcile()
        date_str = statement_date or datetime.now(timezone.utc).date().isoformat()
        orders = list(self.account.orders.values())
        return ShadowDailyStatement(
            statement_date=date_str,
            account_id=self.account.account_id,
            starting_capital=rec.current_effective_capital,
            ending_equity=rec.total_equity,
            cash_balance=rec.cash_balance,
            blocked_margin=rec.blocked_margin,
            realized_pnl=rec.realized_pnl,
            unrealized_pnl=rec.unrealized_pnl,
            total_fees_paid=rec.total_fees,
            orders_submitted=len(orders),
            orders_filled=sum(1 for o in orders if o.state.value == "FILLED"),
            orders_partially_filled=sum(1 for o in orders if o.state.value == "PARTIALLY_FILLED"),
            orders_rejected=sum(1 for o in orders if o.state.value == "REJECTED"),
            open_positions_count=len(self.account.positions),
            balance_discrepancy=rec.balance_discrepancy,
            is_reconciled=rec.is_reconciled,
            live_orders_transmitted=0,
        )
