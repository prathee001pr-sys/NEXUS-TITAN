"""Stage55: bounded, single-SQLite synthetic BUY lifecycle experiment.

ONE transaction domain contains the simulated BUY intent, reserved budget,
partial fill settlements, and cancellation release. It is *not connected* to
the existing Stage43/19/49/53 books, broker APIs, exchange prices, signed
approvals or global Risk & Veto. Its synthetic observations can be forged by
callers; no cash or order here authorizes trading.

Unkeyed hash-chain and head replay detect ordinary damage, not tampering by
someone who can rewrite all SQLite bytes. All prices/fees are integer cents.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from nexus_titan.operations.fo_risk_boundary import (
    SyntheticFOOperation, SyntheticFORiskBoundary, SyntheticFORiskBlocked,
    SyntheticFORiskPermit,
)

_MAX_CENTS = 900_000_000_000_000
_MAX_EVENTS = 500
_GENESIS = "0" * 64
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9._-]{0,29}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


@dataclass(frozen=True, slots=True)
class Stage82LocalSyntheticRiskState:
    account_id: str
    kill_switch_active: bool
    risk_revision: int
    book_revision: int
    local_integrity_verified: bool = True
    authenticated_risk_authority: bool = False
    globally_unbypassable: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE82_LOCAL_SQLITE_KILL_SWITCH_ONLY_NO_GO"


@dataclass(frozen=True, slots=True)
class Stage83LocalSyntheticOrder:
    order_id: str
    symbol: str
    state: str
    quantity: int
    filled_quantity: int
    unfilled_quantity: int
    open_hold_cents: int
    limit_price_cents: int = 0
    paid_notional_cents: int = 0
    paid_fees_cents: int = 0


@dataclass(frozen=True, slots=True)
class Stage83LocalSyntheticLedgerSnapshot:
    account_id: str
    initial_cents: int
    cash_cents: int
    reserved_cents: int
    available_cents: int
    paid_notional_cents: int
    paid_fees_cents: int
    journal_revision: int
    journal_tip: str
    kill_switch_active: bool
    risk_revision: int
    orders: tuple[Stage83LocalSyntheticOrder, ...]
    ledger_scope_sha256: str = ""
    local_integrity_verified: bool = True
    cross_ledger_authority_verified: bool = False
    real_market_data_authenticated: bool = False
    paper_order_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE83_ONE_SQLITE_SYNTHETIC_LEDGER_ONLY_NO_GO"


class Stage55SyntheticBookBlocked(PermissionError):
    """Fail-closed local synthetic accounting refusal; no broker order."""


@dataclass(frozen=True, slots=True)
class Stage55SyntheticPolicy:
    max_single_reserve_bps: int = 2000
    max_open_reserve_bps: int = 5000

    def __post_init__(self) -> None:
        if (type(self.max_single_reserve_bps) is not int
                or type(self.max_open_reserve_bps) is not int
                or not 1 <= self.max_single_reserve_bps <= 10000
                or not 1 <= self.max_open_reserve_bps <= 10000
                or self.max_single_reserve_bps > self.max_open_reserve_bps):
            raise Stage55SyntheticBookBlocked("Invalid synthetic reserve policy basis points")


@dataclass(frozen=True, slots=True)
class Stage55SyntheticReceipt:
    account_id: str
    operation_id: str
    order_id: str
    event_kind: str
    order_state: str
    filled_quantity: int
    cash_cents: int
    open_reserved_cents: int
    available_cents: int
    revision: int
    journal_tip: str
    synthetic_only: bool = True
    trading_authority: bool = False
    live_orders_transmitted: int = 0
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class Stage55SyntheticStatus:
    account_id: str
    initial_cents: int
    cash_cents: int | None
    open_reserved_cents: int | None
    available_cents: int | None
    paid_notional_cents: int | None
    paid_fees_cents: int | None
    total_orders: int | None
    pending_orders: int | None
    partially_filled_orders: int | None
    filled_orders: int | None
    cancelled_orders: int | None
    revision: int | None
    journal_tip: str | None
    local_integrity_verified: bool
    blockers: tuple[str, ...]
    synthetic_only: bool = True
    real_broker_fill_evidence_verified: bool = False
    existing_virtual_research_books_integrated: bool = False
    cross_database_atomicity_verified: bool = False
    external_human_identity_verified: bool = False
    independently_enforced_risk_veto: bool = False
    real_market_data_authenticated: bool = False
    unbypassable_global_entry: bool = False
    broker_orders_transmitted: int = 0
    live_trading_enabled: bool = False
    production_ready: bool = False


def _id(value: object, kind: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise Stage55SyntheticBookBlocked(f"{kind} is not a bounded ASCII identifier")
    return value


def _amount(value: object, kind: str, *, allow_zero: bool = False) -> int:
    if (type(value) is not int or value < (0 if allow_zero else 1)
            or value > _MAX_CENTS):
        raise Stage55SyntheticBookBlocked(f"{kind} must be a bounded integer-cent amount")
    return value


def _quantity(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 1_000_000:
        raise Stage55SyntheticBookBlocked("Quantity must be an explicit bounded positive integer")
    return value


def _hash_event(row: tuple) -> str:
    body = json.dumps(["STAGE55_EVENT_V1", *row], separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class Stage55IsolatedSyntheticExecutionBook:
    """Local atomic intent/hold/fill/cancel in ONE SQLite file; research only."""

    def __init__(
        self, *, db_path: Path, account_id: str, starting_cents: int,
        policy: Stage55SyntheticPolicy = Stage55SyntheticPolicy(),
        excluded_ledger_paths: tuple[Path, ...] = (),
        fo_boundary: SyntheticFORiskBoundary | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(db_path, Path):
            raise TypeError("Explicit SQLite Path required")
        if not isinstance(policy, Stage55SyntheticPolicy):
            raise TypeError("Stage55SyntheticPolicy required")
        if not isinstance(excluded_ledger_paths, tuple):
            raise TypeError("Excluded ledger paths must be a tuple")
        if fo_boundary is not None and not isinstance(fo_boundary, SyntheticFORiskBoundary):
            raise TypeError("Typed F&O risk boundary required")
        if not callable(clock):
            raise TypeError("Explicit synthetic clock must be callable")
        self.account_id = _id(account_id, "Account ID")
        self.starting_cents = _amount(starting_cents, "Starting cents")
        self.policy = policy
        self._path = db_path
        self._fo_boundary = fo_boundary
        self._clock = clock
        if fo_boundary is not None and (
            any(p.account_id != self.account_id or p.virtual_capital_cents != self.starting_cents
                for p in fo_boundary.packets)
            or policy.max_single_reserve_bps > fo_boundary.policy.max_single_debit_bps
            or policy.max_open_reserve_bps > fo_boundary.policy.max_portfolio_debit_bps
        ):
            raise Stage55SyntheticBookBlocked("F&O risk boundary account/capital/policy mismatch")
        try:
            if not db_path.name or db_path.is_dir() or any(
                p.is_symlink() for p in (db_path, *db_path.parents)
            ):
                raise Stage55SyntheticBookBlocked("Synthetic execution SQLite path is unsafe")
            canonical = db_path.resolve()
            for other in excluded_ledger_paths:
                if not isinstance(other, Path):
                    raise TypeError("Excluded ledger paths must be Paths")
                if other.resolve() == canonical:
                    raise Stage55SyntheticBookBlocked("Cannot reuse an existing ledger DB path")
            self._scope = hashlib.sha256(json.dumps(
                ["STAGE55_SINGLE_DB_ONLY_V1", self.account_id, self.starting_cents,
                 policy.max_single_reserve_bps, policy.max_open_reserve_bps,
                 str(canonical),
                 *([] if fo_boundary is None else ["MANDATORY_FO_V1", fo_boundary.digest])],
                separators=(",", ":"), ensure_ascii=False,
            ).encode("utf-8")).hexdigest()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._conn() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS execution_head(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    account_id TEXT NOT NULL, starting_cents INTEGER NOT NULL,
                    scope_sha TEXT NOT NULL, cash_cents INTEGER NOT NULL,
                    reserved_cents INTEGER NOT NULL, revision INTEGER NOT NULL,
                    event_sha TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS execution_events(
                    seq INTEGER PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL CHECK(kind IN ('OPEN','FILL','CANCEL')),
                    order_id TEXT NOT NULL, symbol TEXT NOT NULL, qty INTEGER NOT NULL,
                    price_cents INTEGER NOT NULL, fee_cents INTEGER NOT NULL,
                    fee_buffer_cents INTEGER NOT NULL,
                    previous_sha TEXT NOT NULL, event_sha TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS execution_local_risk(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    scope_sha TEXT NOT NULL, stopped INTEGER NOT NULL
                    CHECK(stopped IN (0,1)), risk_revision INTEGER NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS execution_fo_boundary(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    scope_sha TEXT NOT NULL, boundary_sha TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS execution_fo_permits(
                    seq INTEGER PRIMARY KEY, permit_json TEXT NOT NULL
                )""")
                conn.execute("BEGIN IMMEDIATE")
                head = conn.execute("SELECT 1 FROM execution_head WHERE singleton=1").fetchone()
                if head is None:
                    if conn.execute("SELECT 1 FROM execution_events LIMIT 1").fetchone():
                        raise Stage55SyntheticBookBlocked("Missing head with existing history")
                    conn.execute(
                        "INSERT INTO execution_head VALUES (1,?,?,?,?,?,?,?)",
                        (self.account_id, self.starting_cents, self._scope,
                         self.starting_cents, 0, 0, _GENESIS),
                    )
                    if fo_boundary is not None:
                        conn.execute("INSERT INTO execution_fo_boundary VALUES (1,?,?)",
                                     (self._scope, fo_boundary.digest))
                risk = conn.execute(
                    "SELECT scope_sha, stopped, risk_revision FROM execution_local_risk WHERE singleton=1"
                ).fetchone()
                if risk is None:
                    previous = conn.execute("SELECT revision FROM execution_head WHERE singleton=1").fetchone()
                    if previous is None or previous[0] != 0:
                        raise Stage55SyntheticBookBlocked(
                            "Existing nonempty book lacks local risk state; manual migration required"
                        )
                    conn.execute(
                        "INSERT INTO execution_local_risk VALUES (1, ?, 0, 0)", (self._scope,)
                    )
                else:
                    if (risk[0] != self._scope or type(risk[1]) is not int
                            or risk[1] not in (0, 1)
                            or type(risk[2]) is not int or not 0 <= risk[2] <= 100000):
                        raise Stage55SyntheticBookBlocked("Local synthetic risk state invalid")
                self._replay_checked(conn)
                conn.commit()
        except Stage55SyntheticBookBlocked:
            raise
        except (OSError, sqlite3.Error, OverflowError, ValueError) as exc:
            raise Stage55SyntheticBookBlocked("Synthetic execution book initialization failed") from exc

    @contextmanager
    def _conn(self):
        if self._path.is_symlink() or not self._path.parent.is_dir():
            raise Stage55SyntheticBookBlocked("Synthetic DB path changed")
        conn = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            yield conn
        finally:
            # A noncommitted BEGIN IMMEDIATE rolls back when closed.
            conn.close()

    def _replay_checked(self, conn):
        head = conn.execute(
            "SELECT account_id,starting_cents,scope_sha,cash_cents,reserved_cents,"
            "revision,event_sha FROM execution_head WHERE singleton=1"
        ).fetchone()
        if head is None or tuple(head[:3]) != (
            self.account_id, self.starting_cents, self._scope,
        ):
            raise Stage55SyntheticBookBlocked("Synthetic book scope/head changed")
        derived = self._derive(conn)
        if (head[3] != derived[1] or head[4] != derived[2]
                or head[5] != derived[5] or head[6] != derived[6]):
            raise Stage55SyntheticBookBlocked("Synthetic event/head balances disagree")
        self._check_fo_history(conn, derived[0])
        return derived

    def _check_fo_history(self, conn, orders):
        marker = conn.execute("SELECT scope_sha,boundary_sha FROM execution_fo_boundary WHERE singleton=1").fetchone()
        proofs = dict(conn.execute("SELECT seq,permit_json FROM execution_fo_permits").fetchall())
        boundary = self._fo_boundary
        if boundary is None:
            if marker is not None or proofs:
                raise Stage55SyntheticBookBlocked("Mandatory F&O boundary cannot be omitted")
            return
        if marker != (self._scope, boundary.digest):
            raise Stage55SyntheticBookBlocked("Mandatory F&O boundary missing or changed")
        rows = conn.execute("SELECT seq,operation_id,kind,order_id,symbol,qty,price_cents,fee_cents,fee_buffer_cents,previous_sha FROM execution_events WHERE kind!='CANCEL' ORDER BY seq").fetchall()
        if set(proofs) != {r[0] for r in rows}:
            raise Stage55SyntheticBookBlocked("Synthetic F&O risk journal coverage mismatch")
        try:
            for seq, op, kind, oid, sym, qty, price, fee, buffer, prev in rows:
                permit = SyntheticFORiskPermit.decode(proofs[seq])
                operation = SyntheticFOOperation(kind, op, oid, sym, qty, price, fee, buffer)
                boundary.verify(permit, operation, scope=self._scope, revision=seq-1,
                                tip=prev, risk_revision=permit.risk_revision, now_epoch=permit.issued_epoch)
                boundary.review(operation, permit.telemetry, permit.issued_epoch, False,
                                {k: v['symbol'] for k, v in orders.items()})
        except (SyntheticFORiskBlocked, ValueError, TypeError) as exc:
            raise Stage55SyntheticBookBlocked("Synthetic F&O risk journal verification failed") from exc

    def _derive(self, conn):
        events = conn.execute(
            "SELECT seq,operation_id,kind,order_id,symbol,qty,price_cents,"
            "fee_cents,fee_buffer_cents,previous_sha,event_sha "
            "FROM execution_events ORDER BY seq"
        ).fetchall()
        if len(events) > _MAX_EVENTS:
            raise Stage55SyntheticBookBlocked("Bounded synthetic journal capacity exceeded")
        cash = self.starting_cents
        reserved = 0
        paid_notional = paid_fees = 0
        previous = _GENESIS
        orders = {}
        operation_ids = set()
        for expected_seq, event in enumerate(events, start=1):
            seq, op, kind, oid, sym, qty, price, fee, buffer, prev, hashed = event
            core = event[:-1]
            if (seq != expected_seq or _ID.fullmatch(op or "") is None
                    or _ID.fullmatch(oid or "") is None or op in operation_ids
                    or prev != previous or hashed != _hash_event(core)):
                raise Stage55SyntheticBookBlocked("Synthetic journal sequence or hash altered")
            operation_ids.add(op)
            if kind == "OPEN":
                if (op != oid or oid in orders
                        or _SYMBOL.fullmatch(sym or "") is None
                        or not 1 <= qty <= 1_000_000 or not 1 <= price <= _MAX_CENTS
                        or not 0 <= buffer <= _MAX_CENTS or fee != 0):
                    raise Stage55SyntheticBookBlocked("Invalid synthetic opening event")
                held = qty * price + buffer
                if (held > _MAX_CENTS or held > cash - reserved
                        or held * 10000 > self.starting_cents * self.policy.max_single_reserve_bps
                        or (reserved + held) * 10000 >
                            self.starting_cents * self.policy.max_open_reserve_bps):
                    raise Stage55SyntheticBookBlocked("Synthetic opening exceeded budget policy")
                orders[oid] = dict(
                    symbol=sym, qty=qty, filled=0, limit=price,
                    fee_budget=buffer, fee_spent=0, state="PENDING_SYNTHETIC",
                    paid_notional=0,
                )
                reserved += held
            elif kind == "FILL":
                order = orders.get(oid)
                if (order is None or sym != "" or buffer != 0
                        or order["state"] not in ("PENDING_SYNTHETIC", "PARTIAL_SYNTHETIC")
                        or not 1 <= qty <= order["qty"] - order["filled"]
                        or not 1 <= price <= order["limit"]
                        or not 0 <= fee <= order["fee_budget"] - order["fee_spent"]):
                    raise Stage55SyntheticBookBlocked("Invalid synthetic fill event")
                paid = qty * price + fee
                # The price difference (limit - fill) becomes available.
                cash -= paid
                reserved -= qty * order["limit"] + fee
                order["filled"] += qty
                order["fee_spent"] += fee
                order["paid_notional"] += qty * price
                if order["filled"] == order["qty"]:
                    reserved -= order["fee_budget"] - order["fee_spent"]
                    order["state"] = "FILLED_SYNTHETIC"
                else:
                    order["state"] = "PARTIAL_SYNTHETIC"
                paid_notional += qty * price
                paid_fees += fee
            elif kind == "CANCEL":
                order = orders.get(oid)
                if (order is None or sym != "" or qty != 0 or price != 0
                        or fee != 0 or buffer != 0
                        or order["state"] not in ("PENDING_SYNTHETIC", "PARTIAL_SYNTHETIC")):
                    raise Stage55SyntheticBookBlocked("Invalid synthetic cancellation event")
                remaining = order["qty"] - order["filled"]
                reserved -= remaining * order["limit"] + (
                    order["fee_budget"] - order["fee_spent"]
                )
                order["state"] = "CANCELLED_SYNTHETIC"
            else:
                raise Stage55SyntheticBookBlocked("Unsupported synthetic event kind")
            if (cash < 0 or reserved < 0 or reserved > cash or cash > self.starting_cents
                    or paid_notional + paid_fees + cash != self.starting_cents):
                raise Stage55SyntheticBookBlocked("Synthetic cash conservation failed")
            self._check_fo_capital(orders, cash, reserved)
            previous = hashed
        recomputed = sum(
            (o["qty"] - o["filled"]) * o["limit"]
            + o["fee_budget"] - o["fee_spent"]
            for o in orders.values()
            if o["state"] in ("PENDING_SYNTHETIC", "PARTIAL_SYNTHETIC")
        )
        if recomputed != reserved:
            raise Stage55SyntheticBookBlocked("Synthetic open-order reserves disagree")
        return orders, cash, reserved, paid_notional, paid_fees, len(events), previous

    def _check_fo_capital(self, orders, cash, reserved):
        """Selected account's gross paid premium + fees + open holds, under lock."""
        boundary = self._fo_boundary
        if boundary is None:
            return
        committed = self.starting_cents - cash + reserved
        if committed * 10000 > self.starting_cents * boundary.policy.max_portfolio_debit_bps:
            raise Stage55SyntheticBookBlocked("Selected F&O account committed-capital limit exceeded")
        markets = {}
        for spec in boundary.instruments:
            units = debit = 0
            for order in orders.values():
                if order['symbol'] != spec.symbol:
                    continue
                pending = order['state'] in ('PENDING_SYNTHETIC', 'PARTIAL_SYNTHETIC')
                remaining = order['qty'] - order['filled'] if pending else 0
                units += order['filled'] + remaining
                debit += order['paid_notional'] + order['fee_spent']
                if pending:
                    debit += remaining * order['limit'] + order['fee_budget'] - order['fee_spent']
            # A signed research packet is a bounded allocation, not an endless
            # permission to reopen its full lot after each fill or partial cancel.
            if units > spec.quantity:
                raise Stage55SyntheticBookBlocked("Selected research allocation already committed")
            markets[spec.underlying] = markets.get(spec.underlying, 0) + debit
        if any(debit * 10000 > self.starting_cents * boundary.policy.max_per_underlying_debit_bps
               for debit in markets.values()):
            raise Stage55SyntheticBookBlocked("Selected F&O underlying committed-capital limit exceeded")

    def _write_event(self, conn, core: tuple, hashed: str) -> None:
        """Patchable test seam to simulate a crash before commit."""
        conn.execute("INSERT INTO execution_events VALUES (?,?,?,?,?,?,?,?,?,?,?)", (*core, hashed))

    def _record(self, *, operation_id: str, kind: str, order_id: str,
                symbol: str = "", qty: int = 0, price: int = 0,
                fee: int = 0, buffer: int = 0,
                expected_revision: int | None = None,
                expected_journal_tip: str | None = None,
                risk_permit: SyntheticFORiskPermit | None = None) -> Stage55SyntheticReceipt:
        op = _id(operation_id, "Operation ID")
        oid = _id(order_id, "Order ID")
        if (expected_revision is None) != (expected_journal_tip is None):
            raise Stage55SyntheticBookBlocked("Revision and journal head must be supplied together")
        if expected_revision is not None and (
            type(expected_revision) is not int or expected_revision < 0
            or not isinstance(expected_journal_tip, str)
            or _SHA256.fullmatch(expected_journal_tip) is None
        ):
            raise Stage55SyntheticBookBlocked("Invalid expected synthetic SQLite version")
        try:
            with self._conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                orders, cash, held, _, _, rev, previous = self._replay_checked(conn)
                risk_row = conn.execute(
                    "SELECT scope_sha, stopped, risk_revision FROM execution_local_risk WHERE singleton=1"
                ).fetchone()
                if (risk_row is None or risk_row[0] != self._scope
                        or type(risk_row[1]) is not int or risk_row[1] not in (0, 1)
                        or type(risk_row[2]) is not int or not 0 <= risk_row[2] <= 100000):
                    raise Stage55SyntheticBookBlocked("Local kill-switch state missing or invalid")
                # This condition is checked under the SAME BEGIN IMMEDIATE lock
                # as OPEN/FILL, including raw direct calls that omit Stage79 CAS.
                if risk_row[1] and kind != "CANCEL":
                    raise Stage55SyntheticBookBlocked("Local synthetic kill switch stops reserve and fill")
                # Compare a previously observed head WITHIN the same
                # BEGIN IMMEDIATE transaction that makes the mutation.
                # This is only one SQLite file; direct legacy writes can
                # still omit this optional, cooperative check.
                if expected_revision is not None and (
                    expected_revision != rev or expected_journal_tip != previous
                ):
                    raise Stage55SyntheticBookBlocked("Stale synthetic SQLite snapshot denied")
                existing_event = conn.execute(
                    "SELECT kind,order_id,symbol,qty,price_cents,fee_cents,fee_buffer_cents "
                    "FROM execution_events WHERE operation_id=?", (op,),
                ).fetchone()
                if existing_event is not None and self._fo_boundary is not None:
                    if existing_event != (kind, oid, symbol, qty, price, fee, buffer):
                        raise Stage55SyntheticBookBlocked("Idempotency ID conflicts with committed operation")
                    state = orders[oid]
                    # Read-only acknowledgement, including after lost response /
                    # restart. It grants no new permit and changes no journal row.
                    return Stage55SyntheticReceipt(
                        account_id=self.account_id, operation_id=op, order_id=oid,
                        event_kind=kind, order_state=state['state'],
                        filled_quantity=state['filled'], cash_cents=cash,
                        open_reserved_cents=held, available_cents=cash-held,
                        revision=rev, journal_tip=previous, replayed=True,
                    )
                if existing_event is not None:
                    raise Stage55SyntheticBookBlocked("Repeated operation ID denied")
                if rev >= _MAX_EVENTS:
                    raise Stage55SyntheticBookBlocked("Synthetic journal capacity reached")
                if self._fo_boundary is not None and kind != "CANCEL":
                    operation = SyntheticFOOperation(kind, op, oid, symbol, qty, price, fee, buffer)
                    now = int(self._clock())
                    self._fo_boundary.verify(
                        risk_permit, operation, scope=self._scope, revision=rev,
                        tip=previous, risk_revision=risk_row[2], now_epoch=now,
                    )
                    self._fo_boundary.review(
                        operation, risk_permit.telemetry, now, bool(risk_row[1]),
                        {k: v['symbol'] for k, v in orders.items()},
                    )
                if kind == "OPEN":
                    if oid in orders or op != oid:
                        raise Stage55SyntheticBookBlocked("Duplicate synthetic order ID denied")
                    budget = qty * price + buffer
                    if (budget > cash - held or
                            budget * 10000 > self.starting_cents *
                                self.policy.max_single_reserve_bps or
                            (held + budget) * 10000 > self.starting_cents *
                                self.policy.max_open_reserve_bps):
                        raise Stage55SyntheticBookBlocked("Synthetic reserve or risk cap exceeded")
                    trial = dict(orders)
                    trial[oid] = dict(symbol=symbol, qty=qty, filled=0, limit=price,
                                      fee_budget=buffer, fee_spent=0, paid_notional=0,
                                      state='PENDING_SYNTHETIC')
                    self._check_fo_capital(trial, cash, held+budget)
                else:
                    existing = orders.get(oid)
                    if existing is None or existing["state"] not in (
                        "PENDING_SYNTHETIC", "PARTIAL_SYNTHETIC"
                    ):
                        raise Stage55SyntheticBookBlocked("No open synthetic order to update")
                    if kind == "FILL":
                        if qty > existing["qty"] - existing["filled"] or (
                            price > existing["limit"] or
                            fee > existing["fee_budget"] - existing["fee_spent"]
                        ):
                            raise Stage55SyntheticBookBlocked("Synthetic fill exceeds remaining limits")
                    elif kind != "CANCEL":
                        raise Stage55SyntheticBookBlocked("Unknown synthetic operation")
                core = (rev + 1, op, kind, oid, symbol, qty, price, fee, buffer, previous)
                new_hash = _hash_event(core)
                self._write_event(conn, core, new_hash)
                if self._fo_boundary is not None and kind != "CANCEL":
                    conn.execute("INSERT INTO execution_fo_permits VALUES (?,?)",
                                 (rev+1, risk_permit.encode()))
                # Derive all balances in this SAME transaction from the
                # immutable event history. The head is the second committed
                # half of the same SQLite transaction, not another DB.
                calculated = self._derive(conn)
                updated = conn.execute(
                    "UPDATE execution_head SET cash_cents=?,reserved_cents=?,"
                    "revision=?,event_sha=? WHERE singleton=1 AND revision=? AND event_sha=?",
                    (calculated[1], calculated[2], rev + 1, new_hash, rev, previous),
                ).rowcount
                if updated != 1:
                    raise Stage55SyntheticBookBlocked("Synthetic head compare-and-swap failed")
                checked = self._replay_checked(conn)
                if checked[5] != rev + 1 or checked[6] != new_hash:
                    raise Stage55SyntheticBookBlocked("Post-event verification failed")
                state = checked[0][oid]
                conn.commit()
                return Stage55SyntheticReceipt(
                    account_id=self.account_id, operation_id=op,
                    order_id=oid, event_kind=kind,
                    order_state=state["state"], filled_quantity=state["filled"],
                    cash_cents=checked[1], open_reserved_cents=checked[2],
                    available_cents=checked[1] - checked[2],
                    revision=checked[5], journal_tip=checked[6],
                )
        except Stage55SyntheticBookBlocked:
            raise
        except SyntheticFORiskBlocked as exc:
            raise Stage55SyntheticBookBlocked("Mandatory synthetic F&O risk veto: " + str(exc)) from exc
        except (OSError, sqlite3.Error, OverflowError, TypeError, ValueError) as exc:
            raise Stage55SyntheticBookBlocked("Local synthetic transaction failed") from exc

    def reserve_synthetic_buy(self, *, request_id: str, symbol: str,
                              quantity: int, limit_price_cents: int,
                              fee_buffer_cents: int,
                              expected_revision: int | None = None,
                              expected_journal_tip: str | None = None,
                              risk_permit: SyntheticFORiskPermit | None = None) -> Stage55SyntheticReceipt:
        if not isinstance(symbol, str) or _SYMBOL.fullmatch(symbol) is None:
            raise Stage55SyntheticBookBlocked("Only bounded uppercase synthetic equity symbols supported")
        qty = _quantity(quantity)
        price = _amount(limit_price_cents, "Synthetic limit price")
        buffer = _amount(fee_buffer_cents, "Synthetic fee buffer", allow_zero=True)
        if qty * price + buffer > _MAX_CENTS:
            raise Stage55SyntheticBookBlocked("Synthetic order exceeds bounded monetary amount")
        return self._record(
            operation_id=request_id, kind="OPEN", order_id=request_id,
            symbol=symbol, qty=qty, price=price, buffer=buffer,
            expected_revision=expected_revision,
            expected_journal_tip=expected_journal_tip,
            risk_permit=risk_permit,
        )

    def record_simulated_fill(self, *, order_id: str, fill_id: str,
                              quantity: int, price_cents: int,
                              fee_cents: int, evidence_source: str,
                              expected_revision: int | None = None,
                              expected_journal_tip: str | None = None,
                              risk_permit: SyntheticFORiskPermit | None = None) -> Stage55SyntheticReceipt:
        if evidence_source != "LOCAL_SYNTHETIC_TEST_ONLY":
            raise Stage55SyntheticBookBlocked("Only explicitly synthetic local fills can be recorded")
        return self._record(
            operation_id=fill_id, kind="FILL", order_id=order_id,
            qty=_quantity(quantity),
            price=_amount(price_cents, "Synthetic fill price"),
            fee=_amount(fee_cents, "Synthetic fees", allow_zero=True),
            expected_revision=expected_revision,
            expected_journal_tip=expected_journal_tip,
            risk_permit=risk_permit,
        )

    def cancel_unfilled(self, *, order_id: str, cancel_id: str,
                        evidence_source: str,
                        expected_revision: int | None = None,
                        expected_journal_tip: str | None = None) -> Stage55SyntheticReceipt:
        if evidence_source != "LOCAL_SYNTHETIC_TEST_ONLY":
            raise Stage55SyntheticBookBlocked("Only synthetic cancellation simulation accepted")
        return self._record(
            operation_id=cancel_id, kind="CANCEL", order_id=order_id,
            expected_revision=expected_revision,
            expected_journal_tip=expected_journal_tip,
        )

    def snapshot_local_synthetic_portfolio(self) -> Stage83LocalSyntheticLedgerSnapshot:
        """One coherent read-only SQLite snapshot of orders, holds and stop.

        This is NOT a global capital balance or a real F&O positions book.
        """
        try:
            with self._conn() as conn:
                conn.execute("BEGIN")
                entries, cash, reserved, notional, fees, rev, tip = self._replay_checked(conn)
                risk = conn.execute(
                    "SELECT scope_sha,stopped,risk_revision FROM execution_local_risk WHERE singleton=1"
                ).fetchone()
                if (risk is None or risk[0] != self._scope
                        or type(risk[1]) is not int or risk[1] not in (0, 1)
                        or type(risk[2]) is not int or risk[2] < 0):
                    raise Stage55SyntheticBookBlocked("Snapshot local risk state invalid")
                rows = []
                total_held = 0
                for oid, item in sorted(entries.items()):
                    pending = item["state"] in ("PENDING_SYNTHETIC", "PARTIAL_SYNTHETIC")
                    unfilled = item["qty"] - item["filled"]
                    hold = (unfilled * item["limit"] +
                            item["fee_budget"] - item["fee_spent"]) if pending else 0
                    total_held += hold
                    rows.append(Stage83LocalSyntheticOrder(
                        order_id=oid, symbol=item["symbol"],
                        state=item["state"], quantity=item["qty"],
                        filled_quantity=item["filled"],
                        unfilled_quantity=unfilled, open_hold_cents=hold,
                        limit_price_cents=item['limit'],
                        paid_notional_cents=item['paid_notional'],
                        paid_fees_cents=item['fee_spent'],
                    ))
                if total_held != reserved:
                    raise Stage55SyntheticBookBlocked("Snapshot holds do not match replay")
                conn.commit()
                return Stage83LocalSyntheticLedgerSnapshot(
                    account_id=self.account_id, initial_cents=self.starting_cents,
                    cash_cents=cash, reserved_cents=reserved,
                    available_cents=cash-reserved,
                    paid_notional_cents=notional, paid_fees_cents=fees,
                    journal_revision=rev, journal_tip=tip,
                    kill_switch_active=bool(risk[1]), risk_revision=risk[2],
                    orders=tuple(rows),
                    ledger_scope_sha256=self._scope,
                )
        except sqlite3.Error as exc:
            raise Stage55SyntheticBookBlocked("Local portfolio snapshot unavailable") from exc

    def inspect_local_synthetic_risk_state(self) -> Stage82LocalSyntheticRiskState:
        """Read local same-DB stop flag; NOT authenticated owner/risk telemetry."""
        try:
            with self._conn() as conn:
                ledger = self._replay_checked(conn)
                row = conn.execute(
                    "SELECT scope_sha, stopped, risk_revision FROM execution_local_risk WHERE singleton=1"
                ).fetchone()
                if (row is None or row[0] != self._scope
                        or type(row[1]) is not int or row[1] not in (0, 1)
                        or type(row[2]) is not int or row[2] < 0):
                    raise Stage55SyntheticBookBlocked("Local synthetic risk state unavailable")
                return Stage82LocalSyntheticRiskState(
                    account_id=self.account_id, kill_switch_active=bool(row[1]),
                    risk_revision=row[2], book_revision=ledger[5],
                )
        except sqlite3.Error as exc:
            raise Stage55SyntheticBookBlocked("Failed to inspect local synthetic risk state") from exc

    @property
    def selected_fo_boundary_sha256(self) -> str | None:
        """Configuration identity only; never exports the verification key."""
        return self._fo_boundary.digest if self._fo_boundary is not None else None

    def selected_fo_source_contract(self, symbol: str) -> tuple[str, str, str]:
        """Public research provenance hashes only, with no key or authority."""
        packets = [] if self._fo_boundary is None else [
            p for p in self._fo_boundary.packets if p.option_symbol == symbol
        ]
        if len(packets) != 1:
            raise Stage55SyntheticBookBlocked("Unknown selected F&O research contract")
        p = packets[0]
        return p.source_stage71_sha256, p.source_stage72_sha256, p.stage73_review_sha256

    def set_local_synthetic_kill_switch(
        self, *, active: bool, operation_id: str,
    ) -> Stage82LocalSyntheticRiskState:
        """UNAUTHENTICATED test-only stop/resume. No global safety authority."""
        if type(active) is not bool:
            raise Stage55SyntheticBookBlocked("Local kill switch requires explicit bool")
        _id(operation_id, "Local risk operation ID")
        if self._fo_boundary is not None and not active:
            raise Stage55SyntheticBookBlocked("Protected synthetic F&O stop cannot be rearmed by legacy API")
        try:
            with self._conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                ledger = self._replay_checked(conn)
                row = conn.execute(
                    "SELECT scope_sha, stopped, risk_revision FROM execution_local_risk WHERE singleton=1"
                ).fetchone()
                if (row is None or row[0] != self._scope
                        or type(row[1]) is not int or row[1] not in (0, 1)
                        or type(row[2]) is not int or not 0 <= row[2] < 100000):
                    raise Stage55SyntheticBookBlocked("Invalid local kill switch revision")
                updated = conn.execute(
                    "UPDATE execution_local_risk SET stopped=?, risk_revision=? "
                    "WHERE singleton=1 AND scope_sha=? AND risk_revision=?",
                    (int(active), row[2] + 1, self._scope, row[2]),
                ).rowcount
                if updated != 1:
                    raise Stage55SyntheticBookBlocked("Local kill switch CAS failed")
                conn.commit()
                return Stage82LocalSyntheticRiskState(
                    account_id=self.account_id, kill_switch_active=active,
                    risk_revision=row[2] + 1, book_revision=ledger[5],
                )
        except sqlite3.Error as exc:
            raise Stage55SyntheticBookBlocked("Local risk state update failed") from exc

    def inspect(self) -> Stage55SyntheticStatus:
        try:
            with self._conn() as conn:
                orders, cash, held, notional, fees, rev, tip = self._replay_checked(conn)
            counts = {state: sum(x["state"] == state for x in orders.values())
                      for state in ("PENDING_SYNTHETIC", "PARTIAL_SYNTHETIC",
                                    "FILLED_SYNTHETIC", "CANCELLED_SYNTHETIC")}
            return Stage55SyntheticStatus(
                self.account_id, self.starting_cents, cash, held, cash - held,
                notional, fees, len(orders), counts["PENDING_SYNTHETIC"],
                counts["PARTIAL_SYNTHETIC"], counts["FILLED_SYNTHETIC"],
                counts["CANCELLED_SYNTHETIC"], rev, tip, True, (),
            )
        except (Stage55SyntheticBookBlocked, sqlite3.Error, OSError, ValueError, TypeError):
            return Stage55SyntheticStatus(
                self.account_id, self.starting_cents, None, None, None,
                None, None, None, None, None, None, None,
                None, None, False,
                ("Single-DB synthetic journal or head integrity unavailable",),
            )
