"""Controlled paper/shadow account. Live order execution is intentionally impossible."""
from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Literal
from uuid import uuid4

from nexus_titan.cost.charges import InstrumentType, calculate_indian_trade_costs
from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
from nexus_titan.virtual.durable_store import DurableAccountStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"


class OrderState(str, Enum):
    NEW = "NEW"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TradingMode(str, Enum):
    MANUAL_APPROVAL = "MANUAL_APPROVAL"
    AUTO_PAPER = "AUTO_PAPER"
    LIVE_DISABLED = "LIVE_DISABLED"


@dataclass(frozen=True)
class ApprovalRecord:
    approval_id: str
    order_id: str
    actor: str
    order_snapshot_hash: str
    approved_quantity: int
    approved_limit_price: float | None
    approved_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class FillRecord:
    fill_id: str
    order_id: str
    price: float
    quantity: int
    fees: float
    instrument_type: str = "EQUITY_DELIVERY"
    timestamp: str = field(default_factory=_now)
    idempotency_key: str | None = None
    realized_pnl: float = 0.0


@dataclass(frozen=True)
class CapitalAdjustment:
    timestamp: str
    event_type: Literal["INITIAL", "TOP_UP", "WITHDRAWAL"]
    amount: float
    old_capital: float
    new_capital: float
    reason: str
    resulting_risk_budget: float
    user_confirmed: bool = True


@dataclass
class VirtualOrder:
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    instrument_type: InstrumentType = "EQUITY_DELIVERY"
    lot_size: int = 1
    filled_qty: int = 0
    limit_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    state: OrderState = OrderState.NEW
    fill_price: float | None = None
    fees_paid: float = 0.0
    fills: list[FillRecord] = field(default_factory=list)
    approval: ApprovalRecord | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    reject_reason: str | None = None
    is_emergency: bool = False

    @property
    def remaining_qty(self) -> int:
        return self.quantity - self.filled_qty

    def compute_snapshot_hash(self) -> str:
        raw = (f"{self.symbol}:{self.side.value}:{self.order_type.value}:{self.quantity}:"
               f"{self.instrument_type}:{self.lot_size}:{self.limit_price}:{self.stop_price}:"
               f"{self.target_price}:{self.is_emergency}")
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        data = asdict(self)
        data.update(side=self.side.value, order_type=self.order_type.value, state=self.state.value)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "VirtualOrder":
        return cls(
            order_id=data["order_id"], symbol=data["symbol"], side=OrderSide(data["side"]),
            order_type=OrderType(data["order_type"]), quantity=data["quantity"],
            instrument_type=data.get("instrument_type", "EQUITY_DELIVERY"),
            lot_size=data.get("lot_size", 1), filled_qty=data.get("filled_qty", 0),
            limit_price=data.get("limit_price"), stop_price=data.get("stop_price"),
            target_price=data.get("target_price"), state=OrderState(data["state"]),
            fill_price=data.get("fill_price"), fees_paid=data.get("fees_paid", 0.0),
            fills=[FillRecord(**item) for item in data.get("fills", [])],
            approval=ApprovalRecord(**data["approval"]) if data.get("approval") else None,
            created_at=data.get("created_at", ""), updated_at=data.get("updated_at", ""),
            reject_reason=data.get("reject_reason"), is_emergency=data.get("is_emergency", False),
        )


@dataclass
class VirtualPosition:
    symbol: str
    quantity: int
    average_entry_price: float
    current_ltp: float
    stop_loss: float
    instrument_type: InstrumentType = "EQUITY_DELIVERY"
    target: float | None = None
    realized_pnl: float = 0.0
    margin_used: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        return round((self.current_ltp - self.average_entry_price) * self.quantity, 2)


@dataclass(frozen=True)
class ReconciliationReport:
    account_id: str
    initial_capital: float
    total_added_capital: float
    total_withdrawn_capital: float
    current_effective_capital: float
    cash_balance: float
    blocked_margin: float
    realized_pnl: float
    unrealized_pnl: float
    total_fees: float
    total_equity: float
    balance_discrepancy: float
    is_reconciled: bool


class VirtualAccount:
    """SQLite-durable paper account with approval, risk, fill and kill-switch controls."""

    def __init__(
        self, account_id: str = "TITAN-SHADOW-ACCOUNT",
        starting_capital: float | None = None, risk_per_trade_pct: float = 1.0,
        max_portfolio_exposure_pct: float = 50.0,
        trading_mode: TradingMode = TradingMode.AUTO_PAPER,
        state_dir: str | Path | None = None,
        require_pretrade_risk_check: bool = True,
        initial_margin_pct: float = 20.0,
        approval_authorizer: Callable[[str, str], bool] | None = None,
    ):
        if starting_capital is None:
            raise ValueError("Starting capital must be explicitly configured.")
        for name, value in (("starting_capital", starting_capital),
                            ("risk_per_trade_pct", risk_per_trade_pct),
                            ("max_portfolio_exposure_pct", max_portfolio_exposure_pct),
                            ("initial_margin_pct", initial_margin_pct)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number.")
        if starting_capital <= 0 or not 0 < risk_per_trade_pct <= 100 or not 0 < max_portfolio_exposure_pct <= 100:
            raise ValueError("Capital must be positive; risk/exposure percentages must be between 0 and 100.")
        if not 1 <= initial_margin_pct <= 100 or not isinstance(require_pretrade_risk_check, bool):
            raise ValueError("Invalid margin percentage or risk-check setting.")
        if not isinstance(account_id, str) or not account_id.strip():
            raise ValueError("account_id is required.")
        self.account_id = account_id
        self.initial_capital = float(starting_capital)
        self.added_capital = 0.0
        self.withdrawn_capital = 0.0
        self.cash_balance = float(starting_capital)
        self.blocked_margin = 0.0
        self.realized_pnl = 0.0
        self.total_fees = 0.0
        self.risk_per_trade_pct = float(risk_per_trade_pct)
        self.max_portfolio_exposure_pct = float(max_portfolio_exposure_pct)
        self.initial_margin_pct = float(initial_margin_pct)
        self.require_pretrade_risk_check = require_pretrade_risk_check
        self.approval_authorizer = approval_authorizer
        self.risk_engine = AuthoritativeRiskEngine(PortfolioRiskConfig(
            max_risk_per_trade_pct=self.risk_per_trade_pct,
            max_portfolio_exposure_pct=self.max_portfolio_exposure_pct,
        ))
        self.trading_mode = TradingMode(trading_mode)
        if self.trading_mode == TradingMode.LIVE_DISABLED:
            # This value is a sentinel, never an enabled operating mode.
            raise ValueError("Live trading is strictly disabled.")
        self.peak_equity = float(starting_capital)
        self.state_dir = Path(state_dir) if state_dir is not None else None
        self.durable_store = None
        self.lock_file = None
        self.idempotency_file = None
        if self.state_dir is not None:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self.durable_store = DurableAccountStore(self.state_dir / f"{account_id}_durable.db")
            self.lock_file = self.state_dir / f"{account_id}_lockout.json"
            self.idempotency_file = self.state_dir / f"{account_id}_idempotency.json"
        self.kill_switched = False
        self.kill_switch_metadata: dict = {}
        self.processed_fill_idempotency_keys: set[str] = set()
        self.orders: dict[str, VirtualOrder] = {}
        self.positions: dict[str, VirtualPosition] = {}
        self.capital_history = [CapitalAdjustment(
            _now(), "INITIAL", self.initial_capital, 0.0, self.initial_capital,
            "Initial account setup", round(self.initial_capital * self.risk_per_trade_pct / 100, 2))]
        self._load_persistent_state()

    @property
    def current_capital(self) -> float:
        return self.initial_capital + self.added_capital - self.withdrawn_capital

    @property
    def current_exposure(self) -> float:
        return sum(p.current_ltp * p.quantity for p in self.positions.values())

    @property
    def current_equity(self) -> float:
        values = sum(p.current_ltp * p.quantity for p in self.positions.values()
                     if p.instrument_type != "FUTURES")
        futures_pnl = sum(p.unrealized_pnl for p in self.positions.values()
                          if p.instrument_type == "FUTURES")
        return round(self.cash_balance + self.blocked_margin + values + futures_pnl, 2)

    @property
    def current_drawdown_pct(self) -> float:
        return max(0.0, (self.peak_equity - self.current_equity) / self.peak_equity * 100) if self.peak_equity > 0 else 0.0

    def _sync_durable_store(self) -> None:
        if not self.durable_store:
            return
        self.durable_store.save_snapshot(
            account_id=self.account_id, initial_capital=self.initial_capital,
            added_capital=self.added_capital, withdrawn_capital=self.withdrawn_capital,
            cash_balance=self.cash_balance, blocked_margin=self.blocked_margin,
            realized_pnl=self.realized_pnl, total_fees=self.total_fees,
            peak_equity=self.peak_equity, risk_per_trade_pct=self.risk_per_trade_pct,
            max_portfolio_exposure_pct=self.max_portfolio_exposure_pct,
            initial_margin_pct=self.initial_margin_pct,
            require_pretrade_risk_check=self.require_pretrade_risk_check,
            trading_mode=self.trading_mode.value, kill_switched=self.kill_switched,
            kill_metadata=self.kill_switch_metadata,
            orders_dict={k: v.to_dict() for k, v in self.orders.items()},
            positions_dict={k: asdict(v) for k, v in self.positions.items()},
            idem_keys=self.processed_fill_idempotency_keys,
            capital_history=[asdict(v) for v in self.capital_history])

    def _load_persistent_state(self) -> None:
        if self.durable_store:
            snap = self.durable_store.load_snapshot(self.account_id)
            if snap:
                st = snap["state"]
                for name in ("initial_capital", "added_capital", "withdrawn_capital", "cash_balance",
                             "blocked_margin", "realized_pnl", "total_fees", "peak_equity",
                             "risk_per_trade_pct", "max_portfolio_exposure_pct", "initial_margin_pct"):
                    setattr(self, name, float(st[name]))
                self.require_pretrade_risk_check = bool(st["require_pretrade_risk_check"])
                self.trading_mode = TradingMode(st["trading_mode"])
                self.kill_switched = bool(st["kill_switched"])
                import json
                self.kill_switch_metadata = json.loads(st["kill_metadata_json"])
                self.orders = {k: VirtualOrder.from_dict(v) for k, v in snap["orders"].items()}
                self.positions = {k: VirtualPosition(**v) for k, v in snap["positions"].items()}
                self.processed_fill_idempotency_keys = set(snap["idem_keys"])
                self.capital_history = [CapitalAdjustment(**v) for v in snap["capital_history"]]
                self.risk_engine = AuthoritativeRiskEngine(PortfolioRiskConfig(
                    max_risk_per_trade_pct=self.risk_per_trade_pct,
                    max_portfolio_exposure_pct=self.max_portfolio_exposure_pct))
                return
        if self.lock_file and self.lock_file.exists():
            import json
            try:
                state = json.loads(self.lock_file.read_text(encoding="utf-8"))
                self.kill_switched = bool(state.get("kill_switched"))
                self.kill_switch_metadata = state
            except (OSError, ValueError, TypeError):
                self.kill_switched = True
        if self.idempotency_file and self.idempotency_file.exists():
            import json
            try:
                keys = json.loads(self.idempotency_file.read_text(encoding="utf-8"))
                if isinstance(keys, list):
                    self.processed_fill_idempotency_keys = set(keys)
            except (OSError, ValueError, TypeError):
                pass

    def _persist_lock_state(self, reason: str, actor: str = "SYSTEM") -> None:
        self.kill_switch_metadata = {"kill_switched": True, "locked_at": _now(),
                                     "reason": reason, "actor": actor}
        if self.lock_file:
            import json
            self.lock_file.write_text(json.dumps(self.kill_switch_metadata, indent=2), encoding="utf-8")
        self._sync_durable_store()

    def _daily_loss_pct(self) -> float:
        today = datetime.now(timezone.utc).date()
        pnl = sum(fill.realized_pnl for order in self.orders.values() if order.side == OrderSide.SELL
                  for fill in order.fills if datetime.fromisoformat(fill.timestamp).date() == today)
        return max(0.0, -pnl / max(self.current_capital, 1) * 100)

    def _consecutive_losses(self) -> int:
        rows = [(f.timestamp, f.realized_pnl) for o in self.orders.values()
                if o.side == OrderSide.SELL for f in o.fills]
        count = 0
        for _, pnl in sorted(rows, reverse=True):
            if pnl < 0:
                count += 1
            else:
                break
        return count

    def adjust_capital(self, amount: float, event_type: Literal["TOP_UP", "WITHDRAWAL"],
                       reason: str = "User capital adjustment", user_confirmed: bool = True) -> CapitalAdjustment:
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount <= 0:
            raise ValueError("Adjustment amount must be a finite positive number.")
        event = event_type.upper()
        if event not in ("TOP_UP", "WITHDRAWAL"):
            raise ValueError("event_type must be TOP_UP or WITHDRAWAL.")
        if not isinstance(user_confirmed, bool) or not user_confirmed:
            raise PermissionError("Capital adjustment requires explicit user confirmation.")
        old = self.current_capital
        if event == "TOP_UP":
            self.added_capital += amount
            self.cash_balance += amount
        else:
            if amount > self.cash_balance or old - amount <= 0:
                raise ValueError("Withdrawal exceeds free cash or would reduce capital to zero.")
            if self.current_exposure > (old - amount) * self.max_portfolio_exposure_pct / 100:
                raise ValueError("Withdrawal would breach the portfolio exposure cap.")
            self.withdrawn_capital += amount
            self.cash_balance -= amount
        item = CapitalAdjustment(_now(), event, float(amount), old, self.current_capital,
                                 str(reason), round(self.current_capital * self.risk_per_trade_pct / 100, 2),
                                 user_confirmed)
        self.capital_history.append(item)
        self._sync_durable_store()
        return item

    def set_trading_mode(self, mode: TradingMode | str) -> None:
        selected = TradingMode(mode)
        if selected == TradingMode.LIVE_DISABLED:
            raise ValueError("Live trading is strictly disabled in this environment.")
        self.trading_mode = selected
        self._sync_durable_store()

    def _reject(self, order: VirtualOrder, reason: str) -> VirtualOrder:
        order.state = OrderState.REJECTED
        order.reject_reason = reason
        order.updated_at = _now()
        self.orders[order.order_id] = order
        self._sync_durable_store()
        return order

    def submit_order(
        self, symbol: str, side: OrderSide | str, quantity: int,
        order_type: OrderType | str = OrderType.MARKET, limit_price: float | None = None,
        stop_price: float | None = None, instrument_type: InstrumentType = "EQUITY_DELIVERY",
        lot_size: int = 1, is_emergency: bool = False, entry_price: float | None = None,
        target_price: float | None = None,
    ) -> VirtualOrder:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("A non-empty symbol is required.")
        try:
            side_enum = OrderSide(side.upper() if isinstance(side, str) else side)
            type_enum = OrderType(order_type.upper() if isinstance(order_type, str) else order_type)
        except (ValueError, AttributeError):
            raise ValueError("Unsupported order side or order type.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Quantity must be a positive whole number.")
        if isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size < 1 or quantity % lot_size:
            raise ValueError("Quantity must be a multiple of a positive lot_size.")
        if instrument_type not in ("EQUITY_DELIVERY", "EQUITY_INTRADAY", "FUTURES", "OPTIONS"):
            raise ValueError("Unsupported instrument_type.")
        for label, value in (("limit_price", limit_price), ("stop_price", stop_price),
                             ("entry_price", entry_price), ("target_price", target_price)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value <= 0):
                raise ValueError(f"{label} must be a finite positive number.")
        if type_enum == OrderType.LIMIT and limit_price is None:
            raise ValueError("LIMIT orders require limit_price.")
        if type_enum == OrderType.STOP_LOSS and stop_price is None:
            raise ValueError("STOP_LOSS orders require stop_price.")
        indicative = entry_price if entry_price is not None else (limit_price if type_enum == OrderType.LIMIT else None)
        if side_enum == OrderSide.BUY and self.require_pretrade_risk_check and not is_emergency:
            if indicative is None or stop_price is None:
                raise ValueError("Pre-trade risk requires entry_price and protective stop_price.")
            if stop_price >= indicative or (target_price is not None and target_price <= indicative):
                raise ValueError("BUY protective stop must be below entry and target above entry.")
        oid = f"ORD-{uuid4().hex[:8].upper()}"
        order = VirtualOrder(oid, symbol.strip().upper(), side_enum, type_enum, quantity,
                             instrument_type, lot_size, limit_price=limit_price,
                             stop_price=stop_price, target_price=target_price, is_emergency=is_emergency)
        if self.kill_switched and not is_emergency:
            return self._reject(order, "Trading is locked by the emergency kill switch.")
        if self.trading_mode == TradingMode.MANUAL_APPROVAL and not is_emergency:
            order.state = OrderState.PENDING_APPROVAL
        else:
            order.state = OrderState.ACCEPTED
        order.updated_at = _now()
        self.orders[oid] = order
        self._sync_durable_store()
        return order

    def approve_order(self, order_id: str, actor: str = "HUMAN_OPERATOR") -> VirtualOrder:
        order = self.orders.get(order_id)
        if not order or order.state != OrderState.PENDING_APPROVAL:
            raise ValueError("Order is missing or is not pending approval.")
        if not actor.strip() or self.approval_authorizer is None:
            raise PermissionError("An authenticated approval_authorizer is required.")
        if not self.approval_authorizer(actor.strip(), order_id):
            raise PermissionError("Approval was rejected by the configured identity provider.")
        order.approval = ApprovalRecord(
            f"APP-{uuid4().hex[:8].upper()}", order_id, actor.strip(),
            order.compute_snapshot_hash(), order.quantity, order.limit_price)
        order.state = OrderState.ACCEPTED
        order.updated_at = _now()
        self._sync_durable_store()
        return order

    def execute_fill(self, order_id: str, fill_price: float, fill_qty: int | None = None,
                     idempotency_key: str | None = None) -> VirtualOrder:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError("Unknown order.")
        if order.state not in (OrderState.ACCEPTED, OrderState.PARTIALLY_FILLED):
            raise ValueError(f"Order cannot be filled in state {order.state.value}.")
        if (isinstance(fill_price, bool) or not isinstance(fill_price, (int, float))
                or not math.isfinite(fill_price) or fill_price <= 0):
            raise ValueError("Fill price must be finite and positive.")
        qty = order.remaining_qty if fill_qty is None else fill_qty
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1 or qty > order.remaining_qty:
            raise ValueError("Fill quantity must be positive and cannot overfill the order.")
        if idempotency_key:
            if idempotency_key in self.processed_fill_idempotency_keys:
                return order
            if not isinstance(idempotency_key, str) or len(idempotency_key) > 200:
                raise ValueError("Invalid idempotency key.")
        if order.order_type == OrderType.LIMIT:
            if order.side == OrderSide.BUY and fill_price > (order.limit_price or 0):
                raise ValueError("BUY limit fill price cannot exceed limit_price.")
            if order.side == OrderSide.SELL and fill_price < (order.limit_price or 0):
                raise ValueError("SELL limit fill price cannot be below limit_price.")
        fee = calculate_indian_trade_costs(order.side.value, float(fill_price), qty, order.instrument_type).total_charges
        realized_fill_pnl = 0.0
        if order.side == OrderSide.BUY:
            if order.symbol in self.positions and self.positions[order.symbol].instrument_type != order.instrument_type:
                raise ValueError("Cannot mix different instrument types in the same position.")
            if self.require_pretrade_risk_check and not order.is_emergency:
                indicative_stop = order.stop_price or (fill_price * 0.98)
                result = self.risk_engine.size_and_validate(
                    capital=self.current_capital, entry_price=float(fill_price), stop_price=indicative_stop,
                    symbol=order.symbol, lot_size=order.lot_size, current_exposure=self.current_exposure,
                    current_open_positions=len(self.positions), realized_daily_loss_pct=self._daily_loss_pct(),
                    consecutive_losses=self._consecutive_losses(), current_drawdown_pct=self.current_drawdown_pct)
                if not result.approved or qty > result.quantity:
                    return self._reject(order, "Pre-trade risk check rejected fill: " + result.reason)
            future = order.instrument_type == "FUTURES"
            margin = fill_price * qty * self.initial_margin_pct / 100 if future else fill_price * qty
            needed = margin + fee
            if self.cash_balance < needed:
                return self._reject(order, "Insufficient cash/margin for fill.")
            self.cash_balance -= needed
            if future:
                self.blocked_margin += margin
            pos = self.positions.get(order.symbol)
            if pos:
                new_qty = pos.quantity + qty
                pos.average_entry_price = (pos.average_entry_price * pos.quantity + fill_price * qty) / new_qty
                pos.quantity = new_qty
                pos.current_ltp = float(fill_price)
                pos.margin_used += margin if future else 0.0
                if order.stop_price:
                    pos.stop_loss = order.stop_price
                if order.target_price:
                    pos.target = order.target_price
            else:
                self.positions[order.symbol] = VirtualPosition(
                    order.symbol, qty, float(fill_price), float(fill_price),
                    order.stop_price or fill_price * 0.98, order.instrument_type,
                    order.target_price, 0.0, margin if future else 0.0)
        else:
            pos = self.positions.get(order.symbol)
            if not pos or pos.quantity < qty:
                return self._reject(order, "Insufficient open position to sell.")
            entry_fee = calculate_indian_trade_costs("BUY", pos.average_entry_price, qty, pos.instrument_type).total_charges
            gross = (fill_price - pos.average_entry_price) * qty
            realized_fill_pnl = round(gross - fee - entry_fee, 2)
            if pos.instrument_type == "FUTURES":
                release = pos.margin_used * qty / pos.quantity
                self.cash_balance += release + gross - fee
                pos.margin_used -= release
                self.blocked_margin -= release
            else:
                self.cash_balance += fill_price * qty - fee
            self.realized_pnl += realized_fill_pnl
            pos.realized_pnl += realized_fill_pnl
            pos.quantity -= qty
            pos.current_ltp = float(fill_price)
            if pos.quantity == 0:
                del self.positions[order.symbol]
        self.total_fees += fee
        order.fills.append(FillRecord(
            f"FILL-{uuid4().hex[:8].upper()}", order_id, float(fill_price), qty, fee,
            order.instrument_type, _now(), idempotency_key, realized_fill_pnl))
        order.filled_qty += qty
        order.fill_price = float(fill_price)
        order.fees_paid += fee
        order.state = OrderState.FILLED if order.remaining_qty == 0 else OrderState.PARTIALLY_FILLED
        order.updated_at = _now()
        self.peak_equity = max(self.peak_equity, self.current_equity)
        if idempotency_key:
            self.processed_fill_idempotency_keys.add(idempotency_key)
        self._sync_durable_store()
        return order

    def cancel_order(self, order_id: str) -> VirtualOrder:
        order = self.orders.get(order_id)
        if not order:
            raise ValueError("Unknown order.")
        if order.state == OrderState.CANCELLED:
            return order
        if order.state == OrderState.FILLED or order.state not in (
                OrderState.ACCEPTED, OrderState.PARTIALLY_FILLED, OrderState.PENDING_APPROVAL):
            raise ValueError(f"Cannot cancel order in state {order.state.value}.")
        order.state = OrderState.CANCELLED
        order.updated_at = _now()
        self._sync_durable_store()
        return order

    def mark_to_market(self, prices: dict[str, float], *, trigger_exits: bool = True) -> list[VirtualOrder]:
        if not isinstance(prices, dict):
            raise ValueError("prices must be a symbol-to-price dictionary.")
        triggered = []
        for symbol, price in prices.items():
            if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
                raise ValueError(f"Invalid mark price for {symbol}.")
            pos = self.positions.get(symbol.upper())
            if not pos:
                continue
            pos.current_ltp = float(price)
            reason = "STOP_LOSS" if trigger_exits and price <= pos.stop_loss else (
                "TARGET" if trigger_exits and pos.target is not None and price >= pos.target else None)
            if reason:
                order = self.submit_order(pos.symbol, OrderSide.SELL, pos.quantity,
                                          instrument_type=pos.instrument_type, is_emergency=True)
                self.execute_fill(order.order_id, float(price))
                order.reject_reason = f"Protective {reason} trigger executed by virtual price monitor."
                triggered.append(order)
        self.peak_equity = max(self.peak_equity, self.current_equity)
        self._sync_durable_store()
        return triggered

    def activate_emergency_kill_switch(self, reason: str = "Manual emergency lockout",
                                       actor: str = "OPERATOR") -> None:
        if self.kill_switched:
            return
        self.kill_switched = True
        for order in self.orders.values():
            if order.side == OrderSide.BUY and order.state in (OrderState.ACCEPTED, OrderState.PENDING_APPROVAL):
                order.state = OrderState.CANCELLED
                order.reject_reason = f"Cancelled by emergency kill switch: {reason}"
        self._persist_lock_state(reason, actor)

    def emergency_square_off(self, current_prices: dict[str, float]) -> list[VirtualOrder]:
        self.activate_emergency_kill_switch("Emergency square-off triggered")
        exits = []
        for symbol in list(self.positions):
            position = self.positions[symbol]
            price = current_prices.get(symbol, position.current_ltp)
            order = self.submit_order(symbol, OrderSide.SELL, position.quantity,
                                      instrument_type=position.instrument_type, is_emergency=True)
            self.execute_fill(order.order_id, price)
            exits.append(order)
        return exits

    def reconcile(self) -> ReconciliationReport:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        open_locked = sum(
            (p.margin_used if p.instrument_type == "FUTURES" else p.average_entry_price * p.quantity)
            + calculate_indian_trade_costs("BUY", p.average_entry_price, p.quantity, p.instrument_type).total_charges
            for p in self.positions.values())
        expected_cash = round(self.current_capital + self.realized_pnl - open_locked, 2)
        discrepancy = round(abs(self.cash_balance - expected_cash), 2)
        return ReconciliationReport(
            self.account_id, round(self.initial_capital, 2), round(self.added_capital, 2),
            round(self.withdrawn_capital, 2), round(self.current_capital, 2),
            round(self.cash_balance, 2), round(self.blocked_margin, 2),
            round(self.realized_pnl, 2), round(unrealized, 2), round(self.total_fees, 2),
            round(self.current_equity, 2), discrepancy, discrepancy < 0.05)
