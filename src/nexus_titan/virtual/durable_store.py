"""Durable SQLite event store for VirtualAccount order/fill/position/cash state and crash recovery."""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class StaleAccountSnapshotError(RuntimeError):
    """A different handle has already committed a newer account snapshot."""


class DurableAccountStore:
    """ACID SQLite persistence engine for virtual account state and recovery."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS account_state (
                    account_id TEXT PRIMARY KEY, initial_capital REAL NOT NULL,
                    added_capital REAL NOT NULL, withdrawn_capital REAL NOT NULL,
                    cash_balance REAL NOT NULL, blocked_margin REAL NOT NULL,
                    realized_pnl REAL NOT NULL, total_fees REAL NOT NULL,
                    peak_equity REAL NOT NULL DEFAULT 0, risk_per_trade_pct REAL NOT NULL DEFAULT 1.0,
                    max_portfolio_exposure_pct REAL NOT NULL DEFAULT 50.0,
                    initial_margin_pct REAL NOT NULL DEFAULT 20.0,
                    require_pretrade_risk_check INTEGER NOT NULL DEFAULT 1,
                    strict_paper_mode INTEGER NOT NULL DEFAULT 0,
                    revision INTEGER NOT NULL DEFAULT 0,
                    trading_mode TEXT NOT NULL, kill_switched INTEGER NOT NULL,
                    kill_metadata_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, order_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT NOT NULL, account_id TEXT NOT NULL, position_json TEXT NOT NULL,
                    PRIMARY KEY (account_id, symbol)
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    account_id TEXT NOT NULL, idem_key TEXT NOT NULL,
                    PRIMARY KEY (account_id, idem_key)
                );
                CREATE TABLE IF NOT EXISTS capital_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, event_json TEXT NOT NULL
                );
            """)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(account_state)").fetchall()}
            migrations = {
                "peak_equity": "REAL NOT NULL DEFAULT 0",
                "risk_per_trade_pct": "REAL NOT NULL DEFAULT 1.0",
                "max_portfolio_exposure_pct": "REAL NOT NULL DEFAULT 50.0",
                "initial_margin_pct": "REAL NOT NULL DEFAULT 20.0",
                "require_pretrade_risk_check": "INTEGER NOT NULL DEFAULT 1",
                "strict_paper_mode": "INTEGER NOT NULL DEFAULT 0",
                "revision": "INTEGER NOT NULL DEFAULT 0",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE account_state ADD COLUMN {column} {definition}")

    def save_snapshot(
        self, account_id: str, initial_capital: float, added_capital: float,
        withdrawn_capital: float, cash_balance: float, blocked_margin: float,
        realized_pnl: float, total_fees: float, peak_equity: float,
        risk_per_trade_pct: float, max_portfolio_exposure_pct: float,
        initial_margin_pct: float, require_pretrade_risk_check: bool,
        trading_mode: str, kill_switched: bool, kill_metadata: dict[str, Any],
        orders_dict: dict[str, Any], positions_dict: dict[str, Any],
        idem_keys: set[str], capital_history: list[Any],
        strict_paper_mode: bool = False,
        expected_revision: int | None = None,
    ) -> int:
        """Atomically persist the entire virtual-account snapshot.

        A durable strict-policy account cannot be silently downgraded by a
        normal snapshot update, even when the caller toggles a Python flag.
        """
        if not isinstance(strict_paper_mode, bool):
            raise ValueError("strict_paper_mode must be boolean")
        if expected_revision is not None and (
            isinstance(expected_revision, bool) or not isinstance(expected_revision, int)
            or expected_revision < 0
        ):
            raise ValueError("expected_revision must be a nonnegative integer or None")
        if strict_paper_mode and (
            trading_mode != "MANUAL_APPROVAL" or require_pretrade_risk_check is not True
        ):
            raise PermissionError("Strict paper account requires MANUAL_APPROVAL and risk checks")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE;")
            old = conn.execute(
                "SELECT strict_paper_mode,revision FROM account_state WHERE account_id=?",
                (account_id,),
            ).fetchone()
            previous = old["revision"] if old is not None else None
            if previous != expected_revision:
                raise StaleAccountSnapshotError(
                    "Stale account snapshot revision; reopen a fresh account handle before retrying"
                )
            if old is not None and old["strict_paper_mode"] == 1 and not strict_paper_mode:
                raise PermissionError("Durable strict paper mode cannot be downgraded")
            revision = (previous or 0) + 1
            conn.execute("""
                INSERT OR REPLACE INTO account_state (
                    account_id, initial_capital, added_capital, withdrawn_capital,
                    cash_balance, blocked_margin, realized_pnl, total_fees, peak_equity,
                    risk_per_trade_pct, max_portfolio_exposure_pct, initial_margin_pct,
                    require_pretrade_risk_check, strict_paper_mode, revision,
                    trading_mode, kill_switched, kill_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (account_id, initial_capital, added_capital, withdrawn_capital,
                  cash_balance, blocked_margin, realized_pnl, total_fees, peak_equity,
                  risk_per_trade_pct, max_portfolio_exposure_pct, initial_margin_pct,
                  1 if require_pretrade_risk_check else 0,
                  1 if strict_paper_mode else 0, revision, trading_mode,
                  1 if kill_switched else 0, json.dumps(kill_metadata)))
            conn.execute("DELETE FROM orders WHERE account_id = ?;", (account_id,))
            for oid, data in orders_dict.items():
                conn.execute("INSERT INTO orders VALUES (?, ?, ?);", (oid, account_id, json.dumps(data)))
            conn.execute("DELETE FROM positions WHERE account_id = ?;", (account_id,))
            for symbol, data in positions_dict.items():
                conn.execute("INSERT INTO positions VALUES (?, ?, ?);", (symbol, account_id, json.dumps(data)))
            for key in idem_keys:
                conn.execute("INSERT OR IGNORE INTO idempotency_keys VALUES (?, ?);", (account_id, key))
            conn.execute("DELETE FROM capital_events WHERE account_id = ?;", (account_id,))
            for event in capital_history:
                conn.execute("INSERT INTO capital_events (account_id, event_json) VALUES (?, ?);",
                             (account_id, json.dumps(event)))
            return revision

    def revision(self, account_id: str) -> int | None:
        """Current durable generation; no multi-table snapshots are exported."""
        with self._connect() as con:
            row = con.execute(
                "SELECT revision FROM account_state WHERE account_id=?", (account_id,)
            ).fetchone()
            return None if row is None else int(row["revision"])

    def strict_mode(self, account_id: str) -> bool:
        """Read persisted strict policy; this is not an external authority."""
        with self._connect() as con:
            row = con.execute(
                "SELECT strict_paper_mode FROM account_state WHERE account_id=?",
                (account_id,),
            ).fetchone()
            return bool(row and row["strict_paper_mode"] == 1)

    def load_snapshot(self, account_id: str) -> dict[str, Any] | None:
        """Recover a complete account snapshot from SQLite."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM account_state WHERE account_id = ?;", (account_id,)).fetchone()
            if not row:
                return None
            order_rows = conn.execute("SELECT order_id, order_json FROM orders WHERE account_id = ?;", (account_id,)).fetchall()
            position_rows = conn.execute("SELECT symbol, position_json FROM positions WHERE account_id = ?;", (account_id,)).fetchall()
            idem_rows = conn.execute("SELECT idem_key FROM idempotency_keys WHERE account_id = ?;", (account_id,)).fetchall()
            capital_rows = conn.execute("SELECT event_json FROM capital_events WHERE account_id = ? ORDER BY id ASC;", (account_id,)).fetchall()
            return {
                "state": dict(row),
                "orders": {r["order_id"]: json.loads(r["order_json"]) for r in order_rows},
                "positions": {r["symbol"]: json.loads(r["position_json"]) for r in position_rows},
                "idem_keys": {r["idem_key"] for r in idem_rows},
                "capital_history": [json.loads(r["event_json"]) for r in capital_rows],
            }
