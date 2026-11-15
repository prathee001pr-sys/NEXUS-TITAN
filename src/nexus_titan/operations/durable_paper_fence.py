"""Stage49: durable, one-shot synthetic-paper *admission fence*.

A cooperative SQLite admission coordinator serializes *Stage49* new BUY
intents, commits a PREPARING marker BEFORE touching the virtual account,
and keeps that marker permanently. A crash, unknown outcome, replay, or
second request fails closed pending manual reconciliation.

It is NOT a unified capital ledger or transaction spanning the independent
VirtualAccount and Stage19 research SQLite databases. Older APIs, other
coordinator paths, the approval/fill lifecycle and external processes are
not globally fenced. No broker/live trading, genuine market feeds or F&O.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from nexus_titan.operations.offline_entry_readiness import inspect_stage45_offline_entry
from nexus_titan.operations.offline_risk_veto import (
    Stage47RiskVetoPolicy, SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.signed_paper_approval import Stage48SignedPaperSession
from nexus_titan.shadow.paper_intent_gateway import PaperIntentResult


class Stage49AdmissionBlocked(PermissionError):
    """The coordinator cannot safely admit a new synthetic paper BUY."""


@dataclass(frozen=True, slots=True)
class Stage49AdmissionStatus:
    account_id: str
    coordinator_bound: bool
    separate_ledgers_currently_flat: bool
    starting_cash_cents: int
    virtual_cash_cents: int | None
    research_cash_cents: int | None
    attempt_count: int
    latest_attempt_state: str | None
    blockers: tuple[str, ...]
    can_request_first_synthetic_buy: bool
    # Never imply complete security from cooperative third-book fencing.
    global_legacy_entrypoints_fenced: bool = False
    cross_ledger_atomicity_verified: bool = False
    one_unified_cash_authority_verified: bool = False
    independent_external_identity_verified: bool = False
    licensed_real_market_data_verified: bool = False
    broker_orders_transmitted: int = 0
    production_ready: bool = False


def _cents(value: object, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise Stage49AdmissionBlocked("Capital amount must be a finite numeric value")
    try:
        d = Decimal(str(value))
        if (not d.is_finite() or d < 0 or (positive and d == 0)
                or d * 100 != (d * 100).to_integral_value()):
            raise Stage49AdmissionBlocked("Capital amount must be positive/cent-exact and finite")
        cents = int(d * 100)
        if cents > 900_000_000_000_000:
            raise Stage49AdmissionBlocked("Capital amount outside bounded range")
        return cents
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise Stage49AdmissionBlocked("Invalid capital precision") from exc


def _request_id(value: object) -> str:
    import re
    if (not isinstance(value, str) or len(value) > 80
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", value) is None):
        raise Stage49AdmissionBlocked("Request ID must be safe nonempty ASCII, <=80 chars")
    return value


class Stage49DurablePaperFence:
    """One-lifetime BUY coordinator for a shared, explicitly scoped SQLite path.

    One account, one starting-capital identity, ONE first BUY ever through
    this coordinator. Additional entries require a separate future approved
    reconciliation workflow; do NOT delete/reset the coordinator as a
    workaround. All attempts, including failed/unknown, reserve the slot.
    """

    def __init__(self, session: Stage48SignedPaperSession, *, db_path: Path):
        if not isinstance(session, Stage48SignedPaperSession):
            raise TypeError("Stage48SignedPaperSession required")
        if not isinstance(db_path, Path):
            raise TypeError("Explicit SQLite coordinator Path required")
        self._session = session
        self._deployment = session._deployment
        cfg = self._deployment.config
        durable = cfg.virtual_state_dir / f"{cfg.account_id}_durable.db"
        other_paths = (durable, cfg.research_db_path, Path(session._verifier.db_path))
        if db_path.is_symlink() or any(x.is_symlink() for x in other_paths):
            raise Stage49AdmissionBlocked("Coordinated SQLite paths cannot be symlinks")
        try:
            real = db_path.resolve()
            others = tuple(x.resolve() for x in other_paths)
            if real in others:
                raise Stage49AdmissionBlocked("Coordinator DB must be independent of all ledgers")
            if db_path.exists() and not db_path.is_file():
                raise Stage49AdmissionBlocked("Coordinator DB must be a regular file")
        except Stage49AdmissionBlocked:
            # PermissionError subclasses OSError; preserve intentional denials.
            raise
        except (OSError, ValueError) as exc:
            raise Stage49AdmissionBlocked("Cannot validate coordinator DB path") from exc
        self._db_path = db_path
        self._account_id = cfg.account_id
        self._starting_cents = _cents(cfg.starting_capital, positive=True)
        # Binds one *cooperating* account/store layout to this SQLite DB.
        self._scope_hash = hashlib.sha256(json.dumps(
            ["STAGE49_SCOPE_V1", self._account_id, self._starting_cents,
             str(real), *(str(x) for x in others)],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS coordinator_scope (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    account_id TEXT NOT NULL, starting_cents INTEGER NOT NULL,
                    scope_hash TEXT NOT NULL
                )""")
                conn.execute("""CREATE TABLE IF NOT EXISTS admission_attempts (
                    request_id TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('PREPARING','PENDING','UNKNOWN')),
                    reference_exposure_cents INTEGER NOT NULL,
                    risk_policy_hash TEXT NOT NULL,
                    virtual_revision INTEGER NOT NULL,
                    order_id TEXT, created_at_utc TEXT NOT NULL
                )""")
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT account_id,starting_cents,scope_hash FROM coordinator_scope WHERE singleton=1"
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO coordinator_scope VALUES (1,?,?,?)",
                        (self._account_id, self._starting_cents, self._scope_hash),
                    )
                elif tuple(row) != (self._account_id, self._starting_cents, self._scope_hash):
                    raise Stage49AdmissionBlocked(
                        "Coordinator belongs to a different account, capital or durable store layout"
                    )
                conn.commit()
        except Stage49AdmissionBlocked:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise Stage49AdmissionBlocked("Coordinator SQLite init/integrity failed") from exc

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path, timeout=5.0, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
        finally:
            # SQLite's own context manager does not close handles.
            # Leaving a transaction uncommitted rolls it back here.
            conn.close()

    def _verify_scope(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT account_id,starting_cents,scope_hash FROM coordinator_scope WHERE singleton=1"
        ).fetchone()
        if row != (self._account_id, self._starting_cents, self._scope_hash):
            raise Stage49AdmissionBlocked("Coordinator scope mismatch or corrupted")

    def _flat_cash(self) -> tuple[int | None, int | None, tuple[str, ...]]:
        deployment = self._deployment
        blockers: list[str] = []
        v_cash: int | None = None
        r_cash: int | None = None
        try:
            report = inspect_stage45_offline_entry(deployment)
            blockers.extend(report.blockers)
            v = deployment.virtual_account
            r = deployment.research_ledger.status()
            v_cash, r_cash = _cents(v.cash_balance), _cents(r.cash_balance)
            if v_cash != r_cash or v_cash != self._starting_cents:
                blockers.append("Virtual and research book cash mismatch or changed capital")
            if v.account_id != r.account_id or r.account_id != self._account_id:
                blockers.append("Two paper account IDs differ")
        except Exception:
            blockers.append("One or both paper ledgers could not be reconciled")
        return v_cash, r_cash, tuple(dict.fromkeys(blockers))

    def inspect(self) -> Stage49AdmissionStatus:
        problems: list[str] = []
        vc, rc, flat_blockers = self._flat_cash()
        problems.extend(flat_blockers)
        count = 0
        latest = None
        bound = False
        try:
            with self._connect() as conn:
                self._verify_scope(conn)
                bound = True
                rows = conn.execute(
                    "SELECT status FROM admission_attempts ORDER BY rowid DESC LIMIT 2"
                ).fetchall()
                count = conn.execute("SELECT COUNT(*) FROM admission_attempts").fetchone()[0]
                latest = rows[0][0] if rows else None
                if count:
                    problems.append("Coordinator has a prior or unresolved BUY attempt; manual audit required")
        except (OSError, sqlite3.Error, Stage49AdmissionBlocked):
            problems.append("Coordinator SQLite status or scope unverified")
        return Stage49AdmissionStatus(
            account_id=self._account_id, coordinator_bound=bound,
            separate_ledgers_currently_flat=not flat_blockers,
            starting_cash_cents=self._starting_cents,
            virtual_cash_cents=vc, research_cash_cents=rc,
            attempt_count=count, latest_attempt_state=latest,
            blockers=tuple(dict.fromkeys(problems)),
            can_request_first_synthetic_buy=not problems,
        )

    def request_first_synthetic_buy(
        self, *, request_id: str, proposal: SyntheticBuyProposal,
        quote: SyntheticQuoteEvidence,
        policy: Stage47RiskVetoPolicy = Stage47RiskVetoPolicy(),
    ) -> PaperIntentResult:
        """Persist PREPARING first; any uncertainty freezes further admissions.

        SQLite only serializes clients using this exact Stage49 DB path.
        Underlying VirtualAccount + research ledgers are still **separate**.
        """
        command = _request_id(request_id)
        if not isinstance(proposal, SyntheticBuyProposal) or not isinstance(quote, SyntheticQuoteEvidence):
            raise Stage49AdmissionBlocked("Valid synthetic proposal and quote required")
        # Reject obviously invalid money before allocating the permanent slot.
        try:
            notional = _cents(Decimal(str(quote.ask)) * proposal.quantity, positive=True)
        except (TypeError, ValueError, ArithmeticError, Stage49AdmissionBlocked) as exc:
            raise Stage49AdmissionBlocked("Requested synthetic notional is invalid") from exc
        if notional > self._starting_cents:
            raise Stage49AdmissionBlocked("Paper notional exceeds starting cash")

        # Risk, quote and Stage45 are all checked *again* by Stage48 after
        # the durable marker is committed.
        preflight = self._session._entry.inspect(proposal, quote, policy=policy)
        if not preflight.new_synthetic_buy_permitted:
            raise Stage49AdmissionBlocked("Stage47 Risk & Veto refused first synthetic BUY")
        starting = self.inspect()
        if not starting.can_request_first_synthetic_buy:
            raise Stage49AdmissionBlocked("Stage49 admission refused: " + "; ".join(starting.blockers))
        v = self._deployment.virtual_account
        try:
            revision = v._snapshot_revision
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
                raise Stage49AdmissionBlocked("Durable virtual revision missing")
            risk_hash = v._risk_policy_fingerprint()
            if not isinstance(risk_hash, str) or len(risk_hash) != 64:
                raise Stage49AdmissionBlocked("Virtual risk policy fingerprint missing")
            # Begin/write/COMMIT BEFORE the Stage48 account call. A crash
            # between those writes leaves PREPARING and permanently blocks
            # any automatic retry or double reservation.
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._verify_scope(conn)
                if conn.execute("SELECT 1 FROM admission_attempts LIMIT 1").fetchone():
                    raise Stage49AdmissionBlocked("Existing coordinator attempt: no duplicate BUY")
                vc, rc, problems = self._flat_cash()
                if problems or vc != self._starting_cents or rc != vc:
                    raise Stage49AdmissionBlocked("Cross-book drift before durable admission")
                if v._snapshot_revision != revision or v._risk_policy_fingerprint() != risk_hash:
                    raise Stage49AdmissionBlocked("Stale virtual policy/revision before coordinator commit")
                conn.execute(
                    "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
                    (command, self._account_id, "PREPARING", notional,
                     risk_hash, revision, None,
                     datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
        except (OSError, sqlite3.Error) as exc:
            raise Stage49AdmissionBlocked("Coordinator admission SQLite failure") from exc

        # No resetting the PREPARING record if order creation fails: a
        # distinct account DB might have persisted an order before an error.
        try:
            response = self._session.request_synthetic_buy(proposal, quote, policy=policy)
            if not isinstance(response, PaperIntentResult) or response.status != "PENDING_APPROVAL":
                raise Stage49AdmissionBlocked("Stage48 did not return an unfilled pending paper order")
        except Exception as exc:
            try:
                with self._connect() as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    self._verify_scope(conn)
                    conn.execute(
                        "UPDATE admission_attempts SET status='UNKNOWN' "
                        "WHERE request_id=? AND status='PREPARING'", (command,),
                    )
                    conn.commit()
            except Exception:
                pass  # Preserve original denial; never claim the state was reset.
            raise Stage49AdmissionBlocked(
                "Paper admission outcome uncertain/blocked; coordinator frozen for manual audit"
            ) from exc
        try:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._verify_scope(conn)
                updated = conn.execute(
                    "UPDATE admission_attempts SET status='PENDING', order_id=? "
                    "WHERE request_id=? AND status='PREPARING'",
                    (response.order_id, command),
                ).rowcount
                if updated != 1:
                    raise Stage49AdmissionBlocked("Persisted preparing marker missing; manual audit required")
                conn.commit()
        except (OSError, sqlite3.Error, Stage49AdmissionBlocked) as exc:
            raise Stage49AdmissionBlocked(
                "Paper intent may exist but coordinator finalization failed; manual audit required"
            ) from exc
        return response
