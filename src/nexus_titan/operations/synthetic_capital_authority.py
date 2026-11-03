"""Stage53: atomic *local synthetic-budget holds* in ONE SQLite authority DB.

This bounded prototype reserves cent-exact amounts against its OWN starting
paper budget. It does not mutate or synchronize Stage43 VirtualAccount,
Stage19 research reservations, Stage49's separate coordinator, real brokers,
or a global Risk & Veto service. It is not wired to trading/order entry.

All holds are permanent until a future explicit, independently auditable
release/reconciliation workflow is designed. This conservative restriction
avoids allowing an unverifiable caller to restore spendable paper budget.

Only cooperative writers using the SAME SQLite file are serialized.
Unkeyed hash-chain checks detect accidental/unsophisticated alteration,
NOT tampering by an adversary controlling the DB. No real-money authority.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class Stage53BudgetBlocked(PermissionError):
    """No reliable new synthetic capital hold can be recorded."""


@dataclass(frozen=True, slots=True)
class Stage53BudgetPolicy:
    max_single_hold_bps: int = 2000
    max_aggregate_held_bps: int = 5000

    def __post_init__(self) -> None:
        for value in (self.max_single_hold_bps, self.max_aggregate_held_bps):
            if type(value) is not int or not 1 <= value <= 10000:
                raise Stage53BudgetBlocked("Risk cap bps must be integer from 1 to 10000")
        if self.max_single_hold_bps > self.max_aggregate_held_bps:
            raise Stage53BudgetBlocked("Per-hold cap cannot exceed aggregate cap")


@dataclass(frozen=True, slots=True)
class Stage53BudgetReceipt:
    account_id: str
    request_id: str
    held_cents: int
    total_held_cents: int
    remaining_cents: int
    revision: int
    audit_chain_tip: str
    synthetic_only: bool = True
    trading_authority: bool = False
    broker_orders_transmitted: int = 0


@dataclass(frozen=True, slots=True)
class Stage53BudgetStatus:
    account_id: str
    initial_cents: int
    held_cents: int | None
    remaining_cents: int | None
    hold_count: int | None
    revision: int | None
    audit_chain_tip: str | None
    local_integrity_verified: bool
    blockers: tuple[str, ...]
    max_single_hold_bps: int
    max_aggregate_held_bps: int
    # THESE FLAGS ARE ALWAYS FALSE.
    globally_mandatory_for_legacy_api: bool = False
    single_authority_for_existing_virtual_and_research_books: bool = False
    cross_database_atomicity_verified: bool = False
    independent_risk_veto_enforced: bool = False
    independent_authenticated_human_identity: bool = False
    external_quote_or_market_data_verified: bool = False
    signer_key_externally_isolated: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    production_ready: bool = False


_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_GENESIS_SHA = "0" * 64


def _identifier(value: object, kind: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise Stage53BudgetBlocked(f"{kind} must be bounded ASCII identifier")
    return value


def _cents(value: object, *, field: str) -> int:
    # No float rounding; callers must explicitly supply exact integer cents.
    if type(value) is not int or value <= 0 or value > 900_000_000_000_000:
        raise Stage53BudgetBlocked(f"{field} must be positive bounded integer cents")
    return value


def _scope_sha(*, account: str, capital: int, policy: Stage53BudgetPolicy, path: Path) -> str:
    payload = json.dumps(
        ["STAGE53_SYNTHETIC_BUDGET_V1", account, capital,
         policy.max_single_hold_bps, policy.max_aggregate_held_bps,
         str(path.resolve())],
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _event_hash(seq: int, request_id: str, amount: int, total: int,
                prev_sha: str) -> str:
    payload = json.dumps(
        ["STAGE53_HOLD_EVENT_V1", seq, request_id, amount, total, prev_sha],
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_db_path(db_path: Path, forbidden: tuple[Path, ...]) -> Path:
    if not isinstance(db_path, Path):
        raise TypeError("Explicit Path required for standalone budget SQLite")
    try:
        if db_path.name in ("", ".", "..") or db_path.is_dir():
            raise Stage53BudgetBlocked("SQLite budget must be a file path")
        real = db_path.resolve()
        if any(p.is_symlink() for p in (db_path, *db_path.parents)):
            raise Stage53BudgetBlocked("Symlinked budget DB or ancestor is unsupported")
        for item in forbidden:
            if not isinstance(item, Path):
                raise TypeError("Excluded ledger paths must be Path objects")
            if real == item.resolve():
                raise Stage53BudgetBlocked("Budget DB cannot alias another ledger")
        if db_path.exists() and not db_path.is_file():
            raise Stage53BudgetBlocked("Budget DB is not a regular file")
        return real
    except Stage53BudgetBlocked:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise Stage53BudgetBlocked("Budget DB path could not be verified") from exc


class Stage53SyntheticCapitalAuthority:
    """Durable cent-based holds for one synthetic account within one DB only.

    Does not submit orders, fill, sign, approve or release holds.
    Requires explicit excluded ledger paths when co-located with Stage43–49.
    NO export of trade authorization.
    """

    def __init__(
        self, *, db_path: Path, account_id: str, starting_cents: int,
        policy: Stage53BudgetPolicy = Stage53BudgetPolicy(),
        excluded_ledger_paths: tuple[Path, ...] = (),
    ) -> None:
        self.account_id = _identifier(account_id, "Account ID")
        self.initial_cents = _cents(starting_cents, field="Starting capital")
        if not isinstance(policy, Stage53BudgetPolicy):
            raise TypeError("Stage53BudgetPolicy required")
        if not isinstance(excluded_ledger_paths, tuple):
            raise TypeError("Excluded ledger paths must be explicit tuple")
        self.policy = policy
        self._path = db_path
        real = _safe_db_path(db_path, excluded_ledger_paths)
        self._scope_hash = _scope_sha(
            account=self.account_id, capital=self.initial_cents,
            policy=policy, path=real,
        )
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._conn() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS budget_scope (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    account_id TEXT NOT NULL,
                    initial_cents INTEGER NOT NULL,
                    scope_hash TEXT NOT NULL,
                    held_cents INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    chain_tip TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS budget_holds (
                    request_id TEXT PRIMARY KEY,
                    amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
                    seq INTEGER NOT NULL UNIQUE,
                    created_utc TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS budget_events (
                    seq INTEGER PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    amount_cents INTEGER NOT NULL,
                    total_held_cents INTEGER NOT NULL,
                    prev_sha TEXT NOT NULL,
                    event_sha TEXT NOT NULL
                )""")
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT account_id,initial_cents,scope_hash FROM budget_scope WHERE singleton=1"
                ).fetchone()
                if row is None:
                    # Reject a forged/missing scope on an existing populated
                    # database; a schema may not silently recreate its authority.
                    if conn.execute("SELECT 1 FROM budget_holds LIMIT 1").fetchone() or (
                        conn.execute("SELECT 1 FROM budget_events LIMIT 1").fetchone()
                    ):
                        raise Stage53BudgetBlocked("Missing budget scope with existing holds")
                    conn.execute(
                        "INSERT INTO budget_scope VALUES (1,?,?,?,?,?,?)",
                        (self.account_id, self.initial_cents, self._scope_hash,
                         0, 0, _GENESIS_SHA),
                    )
                elif tuple(row) != (self.account_id, self.initial_cents, self._scope_hash):
                    raise Stage53BudgetBlocked("Budget account, capital, policy or DB identity changed")
                self._checked(conn)
                conn.commit()
        except Stage53BudgetBlocked:
            raise
        except (sqlite3.Error, OSError, OverflowError) as exc:
            raise Stage53BudgetBlocked("Synthetic budget DB initialization failed") from exc

    @contextmanager
    def _conn(self):
        connection = sqlite3.connect(self._path, timeout=5.0, isolation_level=None)
        try:
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA journal_mode=WAL")
            yield connection
        finally:
            connection.close()

    def _checked(self, conn: sqlite3.Connection) -> tuple[int, int, str, int]:
        scope = conn.execute(
            "SELECT account_id,initial_cents,scope_hash,held_cents,revision,chain_tip "
            "FROM budget_scope WHERE singleton=1"
        ).fetchone()
        if scope is None or tuple(scope[:3]) != (
            self.account_id, self.initial_cents, self._scope_hash,
        ):
            raise Stage53BudgetBlocked("Synthetic budget authority scope mismatched")
        held, revision, tip = scope[3:]
        if (type(held) is not int or type(revision) is not int or
                held < 0 or held > self.initial_cents or revision < 0 or
                not isinstance(tip, str) or len(tip) != 64):
            raise Stage53BudgetBlocked("Budget head contains invalid numeric/hash fields")
        events = conn.execute(
            "SELECT seq,request_id,amount_cents,total_held_cents,prev_sha,event_sha "
            "FROM budget_events ORDER BY seq"
        ).fetchall()
        holds = conn.execute(
            "SELECT seq,request_id,amount_cents FROM budget_holds ORDER BY seq"
        ).fetchall()
        if len(events) != revision or len(holds) != revision:
            raise Stage53BudgetBlocked("Budget event/hold cardinality does not match revision")
        previous = _GENESIS_SHA
        total = 0
        for i, (event, hold) in enumerate(zip(events, holds), start=1):
            seq, rid, amount, recorded_total, prev, event_sha = event
            if (seq != i or hold != (seq, rid, amount) or
                    _ID_RE.fullmatch(rid) is None or
                    type(amount) is not int or amount <= 0 or
                    recorded_total != total + amount or
                    prev != previous or
                    _event_hash(i, rid, amount, recorded_total, prev) != event_sha):
                raise Stage53BudgetBlocked("Budget hash/hold history inconsistent")
            total = recorded_total
            previous = event_sha
        if total != held or previous != tip or total > self.initial_cents:
            raise Stage53BudgetBlocked("Budget hold sum/revision/hash is inconsistent")
        if held * 10000 > self.initial_cents * self.policy.max_aggregate_held_bps:
            raise Stage53BudgetBlocked("Existing holds exceed configured aggregate risk cap")
        return held, revision, tip, self.initial_cents - held

    def inspect(self) -> Stage53BudgetStatus:
        blockers: list[str] = []
        held = free = revision = count = None
        tip = None
        try:
            with self._conn() as conn:
                held, revision, tip, free = self._checked(conn)
                count = revision
        except (sqlite3.Error, OSError, Stage53BudgetBlocked, ValueError, TypeError):
            blockers.append("Budget SQLite scope, integrity or history cannot be verified")
        return Stage53BudgetStatus(
            account_id=self.account_id, initial_cents=self.initial_cents,
            held_cents=held, remaining_cents=free, hold_count=count,
            revision=revision, audit_chain_tip=tip,
            local_integrity_verified=not blockers, blockers=tuple(blockers),
            max_single_hold_bps=self.policy.max_single_hold_bps,
            max_aggregate_held_bps=self.policy.max_aggregate_held_bps,
        )

    def hold_for_synthetic_research(
        self, *, request_id: str, amount_cents: int,
    ) -> Stage53BudgetReceipt:
        """Atomically hold budget within this DB; NEVER issue an order.

        Once a request ID is used, it cannot be retried or overwritten.
        Holds have no release path until an independently-reviewed future
        reconciliation mechanism is implemented.
        """
        rid = _identifier(request_id, "Request ID")
        amount = _cents(amount_cents, field="New synthetic hold")
        if amount * 10000 > self.initial_cents * self.policy.max_single_hold_bps:
            raise Stage53BudgetBlocked("Hold exceeds configured per-request risk budget cap")
        try:
            with self._conn() as conn:
                conn.execute("BEGIN IMMEDIATE")
                held, revision, tip, free = self._checked(conn)
                if amount > free:
                    raise Stage53BudgetBlocked("Insufficient local synthetic free budget")
                if ((held + amount) * 10000 >
                        self.initial_cents * self.policy.max_aggregate_held_bps):
                    raise Stage53BudgetBlocked("Aggregate local synthetic budget cap reached")
                if conn.execute(
                    "SELECT 1 FROM budget_holds WHERE request_id=?", (rid,),
                ).fetchone():
                    raise Stage53BudgetBlocked("Duplicate synthetic request ID cannot be reused")
                seq = revision + 1
                total = held + amount
                new_tip = _event_hash(seq, rid, amount, total, tip)
                conn.execute(
                    "INSERT INTO budget_holds VALUES (?,?,?,?)",
                    (rid, amount, seq, datetime.now(timezone.utc).isoformat()),
                )
                conn.execute(
                    "INSERT INTO budget_events VALUES (?,?,?,?,?,?)",
                    (seq, rid, amount, total, tip, new_tip),
                )
                updated = conn.execute(
                    "UPDATE budget_scope SET held_cents=?,revision=?,chain_tip=? "
                    "WHERE singleton=1 AND revision=? AND chain_tip=?",
                    (total, seq, new_tip, revision, tip),
                ).rowcount
                if updated != 1:
                    raise Stage53BudgetBlocked("Budget compare-and-swap failed")
                # Validate the full trail INSIDE the write transaction.
                final_held, final_seq, final_tip, remaining = self._checked(conn)
                if (final_held, final_seq, final_tip) != (total, seq, new_tip):
                    raise Stage53BudgetBlocked("Budget audit after write did not match")
                conn.commit()
        except Stage53BudgetBlocked:
            raise
        except (sqlite3.Error, OSError, OverflowError) as exc:
            raise Stage53BudgetBlocked("Synthetic budget hold could not be committed") from exc
        return Stage53BudgetReceipt(
            account_id=self.account_id, request_id=rid,
            held_cents=amount, total_held_cents=total,
            remaining_cents=remaining, revision=seq,
            audit_chain_tip=new_tip,
        )
