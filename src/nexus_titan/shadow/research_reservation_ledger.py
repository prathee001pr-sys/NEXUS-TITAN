"""Stage 19: isolated SQLite research-only shadow reservation and replay ledger.

NOT connected to VirtualAccount, authoritative risk, brokers, order routing,
strategy promotion or live trading. BUY-only option-premium projections.
Persisting caller-supplied research events does NOT authenticate market fills.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.simulation.options_order_reconciliation import (
    ResearchFillEvent, reconcile_options_research_order,
)

_INDIA = ZoneInfo("Asia/Kolkata")
_CENT = Decimal("0.01")
_GENESIS = "0" * 64


class ResearchLedgerError(ValueError):
    """Reject an entire SQLite transaction without changing saved state."""


@dataclass(frozen=True, slots=True)
class ResearchLedgerStatus:
    account_id: str
    starting_capital: float
    cash_balance: float
    reserved_cash: float
    available_cash: float
    open_order_count: int
    closed_order_count: int
    cancelled_order_count: int
    option_inventory: tuple[tuple[str, int], ...]
    audit_event_count: int
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


def _money_cents(value: float, label: str, *, allow_zero: bool = True) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ResearchLedgerError(f"{label} must be finite money")
    try:
        amount = Decimal(str(value))
    except (ValueError, InvalidOperation) as exc:
        raise ResearchLedgerError(f"{label} must be finite money") from exc
    if not amount.is_finite() or amount < 0 or (not allow_zero and amount == 0):
        raise ResearchLedgerError(f"{label} must be finite {'non-negative' if allow_zero else 'positive'} money")
    try:
        rounded = amount.quantize(_CENT)
    except InvalidOperation as exc:
        raise ResearchLedgerError(f"{label} exceeds research account bounds") from exc
    if amount != rounded:
        raise ResearchLedgerError(f"{label} must be accurate to two decimal places")
    cents = int(amount * 100)
    if cents > 9_000_000_000_000:
        raise ResearchLedgerError(f"{label} exceeds research account bounds")
    return cents


def _valid_id(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ResearchLedgerError(f"{label} must be a non-empty identifier (max 128 chars)")
    return value.strip()


def _valid_contract(contract: PointInTimeContractSpec, when: datetime) -> None:
    if not isinstance(contract, PointInTimeContractSpec) or contract.exchange.upper() != "NSE" or contract.segment != "OPTIONS":
        raise ResearchLedgerError("NSE OPTIONS point-in-time contract required")
    if not contract.source_verified or not contract.source_reference or contract.expiry_date is None:
        raise ResearchLedgerError("Contract metadata needs an explicit reviewed source and expiry")
    day = when.astimezone(_INDIA).date()
    if not contract.effective_from <= day <= contract.effective_to or day > contract.expiry_date:
        raise ResearchLedgerError("Contract metadata not effective on requested India date")


def _instrument_key(contract: PointInTimeContractSpec, strike: float, option_type: str) -> str:
    if option_type not in ("CE", "PE"):
        raise ResearchLedgerError("option_type must be CE or PE")
    if isinstance(strike, bool) or not isinstance(strike, (int, float)) or not math.isfinite(strike) or strike <= 0:
        raise ResearchLedgerError("strike must be finite and positive")
    if (isinstance(contract.strike_step, bool) or not isinstance(contract.strike_step, (int, float))
            or not math.isfinite(contract.strike_step) or contract.strike_step <= 0):
        raise ResearchLedgerError("Contract strike-step metadata invalid")
    grid = Decimal(str(strike)) / Decimal(str(contract.strike_step))
    if abs(grid - grid.to_integral_value()) > Decimal("0.000001"):
        raise ResearchLedgerError("strike not on contract grid")
    return "|".join((
        "NSE", contract.symbol.strip().upper(), contract.underlying.strip().upper(),
        contract.expiry_date.isoformat(), str(Decimal(str(strike)).normalize()), option_type,
        str(contract.lot_size), contract.source_reference.strip(),
    ))


class DurableResearchShadowLedger:
    """Single-host, transactional, BUY-only, simulated capital-reservation ledger.

    Cross-process SQLite BEGIN IMMEDIATE serializes multi-order reservations.
    Existing account opening capital must match exactly on restart. All audit
    records have a SHA-256 link and a post-state digest (corruption detection,
    NOT adversarial authentication).
    """

    def __init__(self, db_path: str | Path, *, account_id: str, starting_capital: float) -> None:
        self.db_path = Path(db_path)
        if str(self.db_path) == ":memory:":
            raise ResearchLedgerError("Durability requires a file-backed SQLite path")
        self.account_id = _valid_id(account_id, "account_id")
        initial_cents = _money_cents(starting_capital, "starting_capital", allow_zero=False)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    initial_cents INTEGER NOT NULL,
                    cash_cents INTEGER NOT NULL,
                    reserved_cents INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reservations (
                    account_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    instrument_key TEXT NOT NULL,
                    option_type TEXT NOT NULL,
                    strike TEXT NOT NULL,
                    lots INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    max_price_cents INTEGER NOT NULL,
                    fee_buffer_cents INTEGER NOT NULL,
                    held_cents INTEGER NOT NULL,
                    as_of_utc TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED','CANCELLED')),
                    filled_quantity INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (account_id, order_id)
                );
                CREATE TABLE IF NOT EXISTS replay_ids (
                    account_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    PRIMARY KEY (account_id, event_id)
                );
                CREATE TABLE IF NOT EXISTS inventory (
                    account_id TEXT NOT NULL,
                    instrument_key TEXT NOT NULL,
                    quantity INTEGER NOT NULL CHECK(quantity >= 0),
                    PRIMARY KEY (account_id, instrument_key)
                );
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    record_hash TEXT NOT NULL
                );
            """)
            account = con.execute(
                "SELECT initial_cents FROM accounts WHERE account_id=?", (self.account_id,)
            ).fetchone()
            if account is None:
                con.execute(
                    "INSERT INTO accounts VALUES (?, ?, ?, 0)",
                    (self.account_id, initial_cents, initial_cents),
                )
                self._audit(con, {"type": "INITIAL", "capital_cents": initial_cents})
            elif account["initial_cents"] != initial_cents:
                raise ResearchLedgerError("Restart starting_capital differs from stored account")
            self._verify(con)

    @contextmanager
    def _transaction(self):
        con = sqlite3.connect(self.db_path, timeout=10.0)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA busy_timeout=10000")
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def _state_digest(self, con) -> str:
        ac = con.execute(
            "SELECT initial_cents,cash_cents,reserved_cents FROM accounts WHERE account_id=?",
            (self.account_id,),
        ).fetchone()
        if ac is None:
            raise ResearchLedgerError("Research account missing")
        orders = [tuple(row) for row in con.execute(
            "SELECT order_id,instrument_key,lots,quantity,max_price_cents,fee_buffer_cents,"
            "held_cents,as_of_utc,status,filled_quantity FROM reservations "
            "WHERE account_id=? ORDER BY order_id", (self.account_id,),
        )]
        inventory = [tuple(row) for row in con.execute(
            "SELECT instrument_key,quantity FROM inventory WHERE account_id=? ORDER BY instrument_key",
            (self.account_id,),
        )]
        replay = [tuple(row) for row in con.execute(
            "SELECT event_id,order_id FROM replay_ids WHERE account_id=? ORDER BY event_id",
            (self.account_id,),
        )]
        state = {"account": tuple(ac), "orders": orders, "inventory": inventory, "replay": replay}
        blob = json.dumps(state, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _audit(self, con, event: dict) -> None:
        previous = con.execute(
            "SELECT record_hash FROM audit WHERE account_id=? ORDER BY sequence DESC LIMIT 1",
            (self.account_id,),
        ).fetchone()
        prev = previous["record_hash"] if previous else _GENESIS
        payload = json.dumps(
            {"event": event, "post_state_sha256": self._state_digest(con)},
            sort_keys=True, separators=(",", ":"), allow_nan=False,
        )
        digest = hashlib.sha256((prev + "|" + payload).encode()).hexdigest()
        con.execute(
            "INSERT INTO audit(account_id,previous_hash,payload_json,record_hash) VALUES(?,?,?,?)",
            (self.account_id, prev, payload, digest),
        )

    def _verify(self, con) -> int:
        expected = _GENESIS
        rows = con.execute(
            "SELECT previous_hash,payload_json,record_hash FROM audit "
            "WHERE account_id=? ORDER BY sequence ASC", (self.account_id,),
        ).fetchall()
        if not rows:
            raise ResearchLedgerError("Missing durable audit chain")
        for row in rows:
            if row["previous_hash"] != expected or hashlib.sha256(
                (expected + "|" + row["payload_json"]).encode()
            ).hexdigest() != row["record_hash"]:
                raise ResearchLedgerError("Research ledger audit chain corrupted")
            expected = row["record_hash"]
        try:
            last = json.loads(rows[-1]["payload_json"])
            if last["post_state_sha256"] != self._state_digest(con):
                raise ResearchLedgerError("Research ledger state does not match audit")
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ResearchLedgerError("Research ledger audit payload invalid") from exc
        ac = con.execute(
            "SELECT cash_cents,reserved_cents FROM accounts WHERE account_id=?",
            (self.account_id,),
        ).fetchone()
        reserved = con.execute(
            "SELECT COALESCE(SUM(held_cents),0) AS held FROM reservations "
            "WHERE account_id=? AND status='OPEN'", (self.account_id,),
        ).fetchone()["held"]
        if ac["reserved_cents"] != reserved or ac["reserved_cents"] < 0 or ac["cash_cents"] < reserved:
            raise ResearchLedgerError("Research ledger reservation conservation failed")
        return len(rows)

    def verify_integrity(self) -> bool:
        with self._transaction() as con:
            self._verify(con)
        return True

    def reserve_buy(
        self, *, order_id: str, contract: PointInTimeContractSpec,
        strike: float, option_type: str, lots: int, as_of: datetime,
        max_unit_premium: float, fee_buffer: float = 25.0,
    ) -> None:
        """Reserve whole-lot premium and an explicit fee buffer atomically.

        This is only a research scenario; it does not authorize or route an order.
        """
        oid = _valid_id(order_id, "order_id")
        if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ResearchLedgerError("as_of must be timezone-aware")
        _valid_contract(contract, as_of)
        key = _instrument_key(contract, strike, option_type)
        if isinstance(lots, bool) or not isinstance(lots, int) or not 0 < lots <= contract.max_lots_per_trade:
            raise ResearchLedgerError("Invalid whole-lot order size")
        qty = lots * contract.lot_size
        if qty > contract.freeze_quantity:
            raise ResearchLedgerError("Order exceeds contract freeze quantity")
        premium_cents = _money_cents(max_unit_premium, "max_unit_premium", allow_zero=False)
        if Decimal(premium_cents) % (Decimal(str(contract.tick_size)) * 100) != 0:
            raise ResearchLedgerError("Maximum premium must align to the contract tick")
        fee_cents = _money_cents(fee_buffer, "fee_buffer")
        held = qty * premium_cents + fee_cents
        if held > 9_000_000_000_000:
            raise ResearchLedgerError("Reservation exceeds research account bounds")
        with self._transaction() as con:
            self._verify(con)
            ac = con.execute(
                "SELECT cash_cents,reserved_cents FROM accounts WHERE account_id=?",
                (self.account_id,),
            ).fetchone()
            if held > ac["cash_cents"] - ac["reserved_cents"]:
                raise ResearchLedgerError("Insufficient unreserved virtual cash")
            if con.execute(
                "SELECT 1 FROM reservations WHERE account_id=? AND order_id=?",
                (self.account_id, oid),
            ).fetchone():
                raise ResearchLedgerError("Duplicate/replayed order_id")
            con.execute(
                "INSERT INTO reservations (account_id,order_id,instrument_key,option_type,strike,"
                "lots,quantity,max_price_cents,fee_buffer_cents,held_cents,as_of_utc,status)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,'OPEN')",
                (self.account_id, oid, key, option_type, str(strike), lots, qty,
                 premium_cents, fee_cents, held, as_of.astimezone(timezone.utc).isoformat()),
            )
            con.execute(
                "UPDATE accounts SET reserved_cents=reserved_cents+? WHERE account_id=?",
                (held, self.account_id),
            )
            self._audit(con, {"type": "RESERVE_BUY", "order_id": oid, "held_cents": held})

    def cancel(self, order_id: str) -> None:
        oid = _valid_id(order_id, "order_id")
        with self._transaction() as con:
            self._verify(con)
            row = con.execute(
                "SELECT held_cents,status FROM reservations WHERE account_id=? AND order_id=?",
                (self.account_id, oid),
            ).fetchone()
            if row is None or row["status"] != "OPEN":
                raise ResearchLedgerError("Only OPEN research orders can be cancelled")
            con.execute(
                "UPDATE reservations SET status='CANCELLED',held_cents=0 "
                "WHERE account_id=? AND order_id=?", (self.account_id, oid),
            )
            con.execute(
                "UPDATE accounts SET reserved_cents=reserved_cents-? WHERE account_id=?",
                (row["held_cents"], self.account_id),
            )
            self._audit(con, {"type": "CANCEL", "order_id": oid})

    def settle_buy(
        self, *, order_id: str, contract: PointInTimeContractSpec, strike: float,
        option_type: str, events: list[ResearchFillEvent] | tuple[ResearchFillEvent, ...],
        cost_config: IndianCostConfig | None = None,
    ):
        """Reconcile a terminal simulated attempt, debit filled premium, release remainder.

        A PARTIAL result is terminal in this prototype; subsequent fragments
        require a new research order/reservation, not a reopened order.
        """
        oid = _valid_id(order_id, "order_id")
        if not isinstance(events, (tuple, list)) or not events:
            raise ResearchLedgerError("Non-empty simulated event sequence required")
        with self._transaction() as con:
            self._verify(con)
            row = con.execute(
                "SELECT * FROM reservations WHERE account_id=? AND order_id=?",
                (self.account_id, oid),
            ).fetchone()
            if row is None or row["status"] != "OPEN":
                raise ResearchLedgerError("Only OPEN research orders can be settled")
            as_of = datetime.fromisoformat(row["as_of_utc"])
            _valid_contract(contract, as_of)
            key = _instrument_key(contract, strike, option_type)
            if key != row["instrument_key"] or row["option_type"] != option_type or Decimal(str(strike)) != Decimal(row["strike"]):
                raise ResearchLedgerError("Contract/strike/side differ from reserved research order")
            if any(
                not isinstance(event, ResearchFillEvent)
                or not isinstance(event.observed_at, datetime)
                or event.observed_at.tzinfo is None
                or event.observed_at.utcoffset() is None
                or event.observed_at.astimezone(timezone.utc) < as_of
                for event in events
            ):
                raise ResearchLedgerError("Invalid or pre-reservation fill event timestamp")
            ac = con.execute(
                "SELECT cash_cents FROM accounts WHERE account_id=?",
                (self.account_id,),
            ).fetchone()
            report = reconcile_options_research_order(
                events, order_id=oid, contract=contract, strike=strike,
                option_type=option_type, side="BUY",
                requested_lots=row["lots"], starting_cash=ac["cash_cents"] / 100,
                starting_inventory_quantity=0, cost_config=cost_config,
            )
            if report.live_orders_transmitted != 0 or report.approved_for_strategy_promotion:
                raise ResearchLedgerError("Real order or promotion boundary violated")
            if report.average_fill_price is not None and (
                Decimal(str(report.average_fill_price)) > Decimal(row["max_price_cents"]) / 100
            ):
                raise ResearchLedgerError("Simulated fill exceeds reserved maximum premium")
            debit = _money_cents(
                report.filled_notional + report.conservative_fee_reserve, "total_debit",
            )
            if debit > row["held_cents"]:
                raise ResearchLedgerError("Fill and fees exceed reserved virtual capital")
            for event in events:
                try:
                    con.execute(
                        "INSERT INTO replay_ids(account_id,event_id,order_id) VALUES(?,?,?)",
                        (self.account_id, _valid_id(event.event_id, "event_id"), oid),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ResearchLedgerError("Duplicate/replayed simulated fill event across orders") from exc
            con.execute(
                "UPDATE accounts SET cash_cents=cash_cents-?, reserved_cents=reserved_cents-? "
                "WHERE account_id=?", (debit, row["held_cents"], self.account_id),
            )
            con.execute(
                "UPDATE reservations SET status='CLOSED', held_cents=0, filled_quantity=? "
                "WHERE account_id=? AND order_id=?", (report.filled_quantity, self.account_id, oid),
            )
            if report.filled_quantity:
                con.execute(
                    "INSERT INTO inventory(account_id,instrument_key,quantity) VALUES (?,?,?) "
                    "ON CONFLICT(account_id,instrument_key) DO UPDATE SET quantity=quantity+excluded.quantity",
                    (self.account_id, key, report.filled_quantity),
                )
            self._audit(con, {
                "type": "SETTLE_BUY", "order_id": oid, "simulated_event_ids": [e.event_id for e in events],
                "filled_quantity": report.filled_quantity, "debit_cents": debit,
                "released_cents": row["held_cents"] - debit,
            })
            return report

    def status(self) -> ResearchLedgerStatus:
        with self._transaction() as con:
            audited = self._verify(con)
            ac = con.execute(
                "SELECT initial_cents,cash_cents,reserved_cents FROM accounts WHERE account_id=?",
                (self.account_id,),
            ).fetchone()
            counts = {r["status"]: r["n"] for r in con.execute(
                "SELECT status, COUNT(*) AS n FROM reservations WHERE account_id=? GROUP BY status",
                (self.account_id,),
            )}
            inventory = tuple((r["instrument_key"], r["quantity"]) for r in con.execute(
                "SELECT instrument_key,quantity FROM inventory WHERE account_id=? ORDER BY instrument_key",
                (self.account_id,),
            ))
            return ResearchLedgerStatus(
                self.account_id, ac["initial_cents"] / 100, ac["cash_cents"] / 100,
                ac["reserved_cents"] / 100,
                (ac["cash_cents"] - ac["reserved_cents"]) / 100,
                counts.get("OPEN", 0), counts.get("CLOSED", 0), counts.get("CANCELLED", 0),
                inventory, audited,
            )
