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
from nexus_titan.virtual.durable_store import (
    DurableAccountStore, StaleAccountSnapshotError,
)


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
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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
    unamortized_entry_fees: float | None = None

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
        strict_paper_mode: bool = False,
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
        if not isinstance(strict_paper_mode, bool):
            raise ValueError("strict_paper_mode must be an explicit boolean")
        if strict_paper_mode and (
            state_dir is None or TradingMode(trading_mode) is not TradingMode.MANUAL_APPROVAL
            or require_pretrade_risk_check is not True
            or not callable(approval_authorizer)
        ):
            raise PermissionError(
                "Strict paper mode requires durable state, manual approval, risk checks and identity callback"
            )
        self._strict_paper_requested = strict_paper_mode
        self.strict_paper_mode = strict_paper_mode
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
        self._snapshot_revision: int | None = None
        self._stale_snapshot_detected = False
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
        # Internal-only virtual protective exits; deliberately not restored
        # across restart: ambiguous in-flight emergency orders fail closed.
        self._internal_emergency_order_ids: set[str] = set()
        self.positions: dict[str, VirtualPosition] = {}
        self.capital_history = [CapitalAdjustment(
            _now(), "INITIAL", self.initial_capital, 0.0, self.initial_capital,
            "Initial account setup", round(self.initial_capital * self.risk_per_trade_pct / 100, 2))]
        self._load_persistent_state()
        # Persist a new strict policy at account creation, *before* any order.
        # Restart must never silently fall back to an empty legacy account.
        if (self.strict_paper_mode and self.durable_store
                and self.durable_store.load_snapshot(self.account_id) is None):
            self._sync_durable_store()

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

    def _assert_current_revision(self) -> None:
        """Every mutation needs the latest account generation on this handle."""
        if self._stale_snapshot_detected:
            raise StaleAccountSnapshotError(
                "Account handle is stale after a rejected write; reopen before retry"
            )
        if self.durable_store:
            actual = self.durable_store.revision(self.account_id)
            if actual != self._snapshot_revision:
                self._stale_snapshot_detected = True
                raise StaleAccountSnapshotError(
                    "Account snapshot changed in another process; reopen before retry"
                )

    def _sync_durable_store(self) -> None:
        if not self.durable_store:
            return
        self._assert_current_revision()
        try:
            self._snapshot_revision = self.durable_store.save_snapshot(
            account_id=self.account_id, initial_capital=self.initial_capital,
            added_capital=self.added_capital, withdrawn_capital=self.withdrawn_capital,
            cash_balance=self.cash_balance, blocked_margin=self.blocked_margin,
            realized_pnl=self.realized_pnl, total_fees=self.total_fees,
            peak_equity=self.peak_equity, risk_per_trade_pct=self.risk_per_trade_pct,
            max_portfolio_exposure_pct=self.max_portfolio_exposure_pct,
            initial_margin_pct=self.initial_margin_pct,
            require_pretrade_risk_check=self.require_pretrade_risk_check,
            strict_paper_mode=self.strict_paper_mode,
            trading_mode=self.trading_mode.value, kill_switched=self.kill_switched,
            kill_metadata=self.kill_switch_metadata,
            orders_dict={k: v.to_dict() for k, v in self.orders.items()},
            positions_dict={k: asdict(v) for k, v in self.positions.items()},
            idem_keys=self.processed_fill_idempotency_keys,
            capital_history=[asdict(v) for v in self.capital_history],
            expected_revision=self._snapshot_revision)
        except StaleAccountSnapshotError:
            self._stale_snapshot_detected = True
            raise

    def _load_persistent_state(self) -> None:
        if self.durable_store:
            snap = self.durable_store.load_snapshot(self.account_id)
            if snap:
                st = snap["state"]
                self._snapshot_revision = int(st.get("revision", 0))
                stored_initial_capital = float(st.get("initial_capital", 0.0))
                if not math.isclose(stored_initial_capital, self.initial_capital, rel_tol=0.0, abs_tol=0.01):
                    raise ValueError(
                        "Durable account starting capital does not match the requested baseline; "
                        "use the same account_id with its original starting_capital or a new account_id."
                    )
                for name in ("initial_capital", "added_capital", "withdrawn_capital", "cash_balance",
                             "blocked_margin", "realized_pnl", "total_fees", "peak_equity",
                             "risk_per_trade_pct", "max_portfolio_exposure_pct", "initial_margin_pct"):
                    setattr(self, name, float(st[name]))
                saved_strict = st.get("strict_paper_mode", 0)
                if saved_strict not in (0, 1):
                    raise PermissionError("Durable strict-paper policy value invalid")
                if self._strict_paper_requested and saved_strict != 1:
                    raise PermissionError(
                        "Legacy account cannot silently upgrade to strict paper; use enable_strict_paper_mode on empty account"
                    )
                self.strict_paper_mode = (saved_strict == 1)
                self.require_pretrade_risk_check = bool(st["require_pretrade_risk_check"])
                self.trading_mode = TradingMode(st["trading_mode"])
                if self.strict_paper_mode and (
                    not self.require_pretrade_risk_check
                    or self.trading_mode is not TradingMode.MANUAL_APPROVAL
                ):
                    raise PermissionError("Saved strict paper account violates manual/risk invariants")
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
                # The filesystem lock marker is an independent, fail-closed safety
                # record. It must override an older SQLite snapshot if the DB write
                # failed after the marker was made durable.
                self._restore_lock_file_fail_closed()
                return
        self._restore_lock_file_fail_closed()
        if self.idempotency_file and self.idempotency_file.exists():
            import json
            try:
                keys = json.loads(self.idempotency_file.read_text(encoding="utf-8"))
                if isinstance(keys, list):
                    self.processed_fill_idempotency_keys = set(keys)
            except (OSError, ValueError, TypeError):
                pass

    def _restore_lock_file_fail_closed(self) -> None:
        """Restore the durable emergency marker; any unreadable marker locks trading."""
        if not self.lock_file or not self.lock_file.exists():
            return
        import json
        try:
            state = json.loads(self.lock_file.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or state.get("kill_switched") is not True:
                raise ValueError("Lock marker does not explicitly assert an active lockout.")
            self.kill_switched = True
            self.kill_switch_metadata = state
        except (OSError, ValueError, TypeError, UnicodeError):
            self.kill_switched = True
            self.kill_switch_metadata = {
                "kill_switched": True,
                "reason": "Emergency lock marker is unreadable or invalid; trading remains locked.",
                "recovery_required": True,
            }

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
        self._assert_current_revision()
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

    def _assert_strict_paper_policy(self) -> None:
        """Check persisted policy before any paper order state mutation."""
        self._assert_current_revision()
        saved_strict = bool(
            self.durable_store and self.durable_store.strict_mode(self.account_id)
        )
        if saved_strict and self.strict_paper_mode is not True:
            raise PermissionError("Durable strict paper account cannot be downgraded in memory")
        if self.strict_paper_mode and (
            not self.durable_store or
            self.trading_mode is not TradingMode.MANUAL_APPROVAL
            or self.require_pretrade_risk_check is not True
            or not callable(self.approval_authorizer)
        ):
            raise PermissionError("Strict paper account requires manual/risk/auth safety invariants")

    def enable_strict_paper_mode(self) -> None:
        """Explicit opt-in migration for a flat account with durable state."""
        self._assert_current_revision()
        if self.strict_paper_mode:
            self._assert_strict_paper_policy()
            return
        if (self.durable_store is None
                or self.trading_mode is not TradingMode.MANUAL_APPROVAL
                or self.require_pretrade_risk_check is not True
                or not callable(self.approval_authorizer)
                or self.positions
                or any(o.state in (
                    OrderState.NEW, OrderState.ACCEPTED, OrderState.PENDING_APPROVAL,
                    OrderState.PARTIALLY_FILLED,
                ) for o in self.orders.values())):
            raise PermissionError("Strict paper migration requires flat durable manual account and risk/auth gate")
        self.strict_paper_mode = True
        try:
            self._sync_durable_store()
        except Exception:
            self.strict_paper_mode = False
            raise
        self._assert_strict_paper_policy()

    def set_trading_mode(
        self, mode: TradingMode | str, *, actor: str | None = None,
    ) -> None:
        """Changing MANUAL_APPROVAL to AUTO_PAPER is permission escalation.

        A connected, authenticated callback is mandatory for escalation.
        Switching into MANUAL_APPROVAL is always conservative. No transition
        grants real brokerage access. This is application policy, not OS
        isolation or a global independent identity verification service.
        """
        selected = TradingMode(mode)
        if selected == TradingMode.LIVE_DISABLED:
            raise ValueError("Live trading is strictly disabled in this environment.")
        self._assert_strict_paper_policy()
        if self.strict_paper_mode and selected is TradingMode.AUTO_PAPER:
            raise PermissionError("Strict paper mode permanently requires MANUAL_APPROVAL")
        if selected == self.trading_mode:
            return
        if self.kill_switched and selected == TradingMode.AUTO_PAPER:
            raise PermissionError("Emergency kill switch prohibits paper mode escalation")
        if self.trading_mode == TradingMode.MANUAL_APPROVAL and selected == TradingMode.AUTO_PAPER:
            resource = "MODE:MANUAL_APPROVAL->AUTO_PAPER"
            if (not isinstance(actor, str) or not actor.strip()
                    or self.approval_authorizer is None
                    or self.approval_authorizer(actor.strip(), resource) is not True):
                raise PermissionError("Authenticated approval required to enable AUTO_PAPER from MANUAL_APPROVAL")
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
        if is_emergency is not False:
            raise PermissionError(
                "Public submit_order cannot grant emergency status; use monitored protective exit or emergency_square_off."
            )
        self._assert_strict_paper_policy()
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
        if self.strict_paper_mode and side_enum is OrderSide.SELL:
            key = symbol.strip().upper()
            position = self.positions.get(key)
            if position is None or position.quantity < quantity:
                raise PermissionError("Strict paper SELL requires existing long inventory")
            if any(o.symbol == key and o.side is OrderSide.SELL
                   and o.state in (
                       OrderState.NEW, OrderState.ACCEPTED,
                       OrderState.PENDING_APPROVAL, OrderState.PARTIALLY_FILLED,
                   ) for o in self.orders.values()):
                raise PermissionError("Strict paper SELL cannot duplicate unfinished close")
        indicative = entry_price if entry_price is not None else (limit_price if type_enum == OrderType.LIMIT else None)
        if side_enum == OrderSide.BUY and self.require_pretrade_risk_check and not is_emergency:
            if indicative is None or stop_price is None:
                raise ValueError("Pre-trade risk gate requires indicative entry_price and protective stop_price before a BUY order can be accepted.")
            if stop_price >= indicative or (target_price is not None and target_price <= indicative):
                raise ValueError("BUY protective stop must be below entry and target above entry.")
            risk_result = self.risk_engine.size_and_validate(
                capital=self.current_capital,
                entry_price=float(indicative),
                stop_price=float(stop_price),
                symbol=symbol,
                lot_size=lot_size,
                current_exposure=self.current_exposure,
                current_open_positions=len(self.positions),
                realized_daily_loss_pct=self._daily_loss_pct(),
                consecutive_losses=self._consecutive_losses(),
                current_drawdown_pct=self.current_drawdown_pct,
            )
            if not risk_result.approved or quantity > risk_result.quantity:
                raise ValueError(
                    f"Authoritative risk gate rejected order: {risk_result.reason} "
                    f"Requested quantity {quantity}; maximum permitted {risk_result.quantity}."
                )
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

    def _submit_internal_protective_exit(self, position: VirtualPosition) -> VirtualOrder:
        """Create only a position-reducing SELL under internal paper monitor.

        No arbitrary caller-supplied symbol/quantity/side is accepted here.
        This is an in-process safety boundary, NOT cryptographic authorization.
        """
        self._assert_current_revision()
        if not isinstance(position, VirtualPosition) or position.quantity < 1:
            raise ValueError("Protective close requires an existing long position")
        current = self.positions.get(position.symbol)
        if current is not position or position.quantity < 1:
            raise ValueError("Protective close position no longer matches account")
        order = VirtualOrder(
            f"ORD-{uuid4().hex[:8].upper()}", position.symbol, OrderSide.SELL,
            OrderType.MARKET, position.quantity,
            instrument_type=position.instrument_type,
            lot_size=1, is_emergency=True,
            state=OrderState.ACCEPTED,
        )
        self.orders[order.order_id] = order
        self._internal_emergency_order_ids.add(order.order_id)
        self._sync_durable_store()
        return order

    def approve_order(self, order_id: str, actor: str = "HUMAN_OPERATOR") -> VirtualOrder:
        self._assert_strict_paper_policy()
        order = self.orders.get(order_id)
        if not order or order.state != OrderState.PENDING_APPROVAL:
            raise ValueError("Order is missing or is not pending approval.")
        if self.kill_switched:
            raise PermissionError("Emergency kill switch prohibits order approval")
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
        self._assert_strict_paper_policy()
        order = self.orders.get(order_id)
        if not order:
            raise ValueError("Unknown order.")
        if (isinstance(fill_price, bool) or not isinstance(fill_price, (int, float))
                or not math.isfinite(fill_price) or fill_price <= 0):
            raise ValueError("Fill price must be finite and positive.")
        if fill_qty is not None and (
                isinstance(fill_qty, bool) or not isinstance(fill_qty, int) or fill_qty < 1):
            raise ValueError("Fill quantity must be a positive integer.")
        if idempotency_key is not None:
            if (not isinstance(idempotency_key, str) or not idempotency_key.strip()
                    or len(idempotency_key) > 200):
                raise ValueError("Invalid idempotency key.")
            prior = None
            prior_order = None
            for candidate_order in self.orders.values():
                for candidate_fill in candidate_order.fills:
                    if candidate_fill.idempotency_key == idempotency_key:
                        prior, prior_order = candidate_fill, candidate_order
                        break
                if prior is not None:
                    break
            if prior is not None:
                same_request = (
                    prior_order.order_id == order_id
                    and prior.order_id == order_id
                    and prior.price == float(fill_price)
                    and (fill_qty is None or prior.quantity == fill_qty)
                )
                if same_request:
                    return prior_order
                raise ValueError(
                    "Idempotency key conflict: key is already bound to a different order or fill request."
                )
            if idempotency_key in self.processed_fill_idempotency_keys:
                raise ValueError(
                    "Idempotency key exists without a matching fill record; refusing unsafe replay."
                )
        if order.is_emergency and order_id not in self._internal_emergency_order_ids:
            raise PermissionError("Emergency order has no current internal protective-exit provenance")
        if self.strict_paper_mode and not order.is_emergency:
            if (order.approval is None or
                    order.approval.order_id != order.order_id or
                    order.approval.order_snapshot_hash != order.compute_snapshot_hash()):
                raise PermissionError("Strict paper fill requires intact authenticated manual approval")
        # Kill-switch is durable and must be checked at the FILL boundary,
        # not only at submission. Previously PARTIALLY_FILLED BUY remained
        # fillable after emergency lockout because only ACCEPTED was cancelled.
        if self.kill_switched and order.side == OrderSide.BUY:
            raise PermissionError("Emergency kill switch prohibits all further BUY fills")
        if order.state not in (OrderState.ACCEPTED, OrderState.PARTIALLY_FILLED):
            raise ValueError(f"Order cannot be filled in state {order.state.value}.")
        if order.approval is not None and order.compute_snapshot_hash() != order.approval.order_snapshot_hash:
            order.state = OrderState.REJECTED
            order.reject_reason = "Order modified after manual approval; approval invalidated."
            order.updated_at = _now()
            self._sync_durable_store()
            raise ValueError("Approval integrity violation: order was modified after approval.")
        qty = order.remaining_qty if fill_qty is None else fill_qty
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1 or qty > order.remaining_qty:
            raise ValueError("Fill quantity must be positive and cannot overfill the order.")
        if qty % order.lot_size != 0:
            raise ValueError(
                f"Fill quantity ({qty}) must be a multiple of instrument lot_size ({order.lot_size})."
            )
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
                prev_unamortized = (
                    pos.unamortized_entry_fees
                    if pos.unamortized_entry_fees is not None
                    else calculate_indian_trade_costs("BUY", pos.average_entry_price, pos.quantity, pos.instrument_type).total_charges
                )
                new_qty = pos.quantity + qty
                pos.average_entry_price = (pos.average_entry_price * pos.quantity + fill_price * qty) / new_qty
                pos.quantity = new_qty
                pos.current_ltp = float(fill_price)
                pos.margin_used += margin if future else 0.0
                pos.unamortized_entry_fees = round(prev_unamortized + fee, 4)
                if order.stop_price:
                    pos.stop_loss = order.stop_price
                if order.target_price:
                    pos.target = order.target_price
            else:
                self.positions[order.symbol] = VirtualPosition(
                    order.symbol, qty, float(fill_price), float(fill_price),
                    order.stop_price or fill_price * 0.98, order.instrument_type,
                    order.target_price, 0.0, margin if future else 0.0,
                    unamortized_entry_fees=round(fee, 4))
        else:
            pos = self.positions.get(order.symbol)
            if not pos or pos.quantity < qty:
                return self._reject(order, "Insufficient open position to sell.")
            total_unamortized = (
                pos.unamortized_entry_fees
                if pos.unamortized_entry_fees is not None
                else calculate_indian_trade_costs("BUY", pos.average_entry_price, pos.quantity, pos.instrument_type).total_charges
            )
            allocated_entry_fee = total_unamortized if qty == pos.quantity else round(total_unamortized * (qty / pos.quantity), 4)
            pos.unamortized_entry_fees = round(max(0.0, total_unamortized - allocated_entry_fee), 4)
            gross = (fill_price - pos.average_entry_price) * qty
            realized_fill_pnl = round(gross - fee - allocated_entry_fee, 2)
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
        self._assert_current_revision()
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
        self._assert_current_revision()
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
                order = self._submit_internal_protective_exit(pos)
                self.execute_fill(order.order_id, float(price))
                order.reject_reason = f"Protective {reason} trigger executed by virtual price monitor."
                triggered.append(order)
        self.peak_equity = max(self.peak_equity, self.current_equity)
        self._sync_durable_store()
        return triggered

    def activate_emergency_kill_switch(self, reason: str = "Manual emergency lockout",
                                       actor: str = "OPERATOR") -> None:
        self._assert_current_revision()
        if self.kill_switched:
            return
        self.kill_switched = True
        for order in self.orders.values():
            if order.side == OrderSide.BUY and order.state in (
                OrderState.ACCEPTED, OrderState.PENDING_APPROVAL, OrderState.PARTIALLY_FILLED
            ):
                order.state = OrderState.CANCELLED
                order.reject_reason = f"Cancelled by emergency kill switch: {reason}"
        self._persist_lock_state(reason, actor)

    def emergency_square_off(self, current_prices: dict[str, float]) -> list[VirtualOrder]:
        self._assert_current_revision()
        self.activate_emergency_kill_switch("Emergency square-off triggered")
        exits = []
        for symbol in list(self.positions):
            position = self.positions[symbol]
            price = current_prices.get(symbol, position.current_ltp)
            order = self._submit_internal_protective_exit(position)
            self.execute_fill(order.order_id, price)
            exits.append(order)
        return exits

    def reconcile(self) -> ReconciliationReport:
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        open_locked = sum(
            (p.margin_used if p.instrument_type == "FUTURES" else p.average_entry_price * p.quantity)
            + (
                p.unamortized_entry_fees
                if p.unamortized_entry_fees is not None
                else calculate_indian_trade_costs("BUY", p.average_entry_price, p.quantity, p.instrument_type).total_charges
            )
            for p in self.positions.values())
        expected_cash = round(self.current_capital + self.realized_pnl - open_locked, 2)
        discrepancy = round(abs(self.cash_balance - expected_cash), 2)
        return ReconciliationReport(
            self.account_id, round(self.initial_capital, 2), round(self.added_capital, 2),
            round(self.withdrawn_capital, 2), round(self.current_capital, 2),
            round(self.cash_balance, 2), round(self.blocked_margin, 2),
            round(self.realized_pnl, 2), round(unrealized, 2), round(self.total_fees, 2),
            round(self.current_equity, 2), discrepancy, discrepancy < 0.05)
