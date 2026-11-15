"""Stage54: read-only comparison of INDEPENDENT paper accounting books.

Stages 43/19/49/53 are four separate SQLite persistence domains. This
inspector cross-checks the local synthetic records and classifies uncertain
recovery states, but NEVER changes them, releases holds, reconciles orders,
creates an approval, or permits trading.

Database reads are sequential and NOT a cross-DB atomic snapshot. Python
objects and legacy APIs remain mutable/bypassable. All authority flags are
false regardless of how clean the local observations appear.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import quote

from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.synthetic_capital_authority import (
    Stage53SyntheticCapitalAuthority,
)


class Stage54ReconciliationBlocked(PermissionError):
    """An actual cross-book authority cannot be established or used."""


@dataclass(frozen=True, slots=True)
class Stage54RecoveryAssessment:
    account_id: str
    observed_initial_cents: int
    virtual_cash_cents: int | None
    research_cash_cents: int | None
    separate_book_cash_equal: bool
    virtual_internal_reconciled: bool
    research_local_integrity_verified: bool
    stage49_coordinator_scope_verified: bool
    coordinator_attempt_count: int | None
    coordinator_state: str | None
    coordinator_order_link_observed: bool
    coordinator_linked_virtual_order_state: str | None
    budget_local_integrity_verified: bool
    stage53_synthetic_held_cents: int | None
    stage53_synthetic_remaining_cents: int | None
    stage53_hold_count: int | None
    identified_unlinked_paper_orders: int | None
    recovery_classification: str
    manual_recovery_required: bool
    diagnostic_codes: tuple[str, ...]
    manual_review_instructions: tuple[str, ...]
    # Crucial: four ledgers are NOT a pooled account. Never sum their cash.
    combined_available_capital_cents: None = None
    automatic_hold_release_enabled: bool = False
    automatic_order_replay_enabled: bool = False
    automatic_write_repair_enabled: bool = False
    cross_database_atomicity_verified: bool = False
    globally_mandatory_entrypoint: bool = False
    externally_authenticated_human_identity: bool = False
    independent_risk_veto_enforced: bool = False
    real_market_data_authenticated: bool = False
    broker_orders_transmitted: int = 0
    live_trading_enabled: bool = False
    production_ready: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cent_exact(value: object) -> int:
    if type(value) not in (int, float, Decimal):
        raise Stage54ReconciliationBlocked("Non-numeric paper balance")
    try:
        decimal = Decimal(str(value))
        if not decimal.is_finite() or decimal < 0 or decimal * 100 != (decimal * 100).to_integral_value():
            raise Stage54ReconciliationBlocked("Paper balance is not finite exact cents")
        cents = int(decimal * 100)
        if cents > 900_000_000_000_000:
            raise Stage54ReconciliationBlocked("Paper balance exceeds bounded range")
        return cents
    except (ValueError, InvalidOperation, OverflowError) as exc:
        raise Stage54ReconciliationBlocked("Cannot represent paper cash as exact cents") from exc


def _read_only_sqlite(path: Path) -> sqlite3.Connection:
    """Read-only SQLite handle: never creates a missing DB or a new scope."""
    if not path.is_file() or path.is_symlink():
        raise Stage54ReconciliationBlocked("Coordinator database missing or symlinked")
    url = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    connection = sqlite3.connect(url, uri=True, timeout=3.0)
    connection.execute("PRAGMA query_only=ON")
    return connection


class Stage54ReadOnlyMultiLedgerAudit:
    """Opt-in local reconciliation, NOT a new gateway or capital controller."""

    def __init__(
        self, *, paper_fence: Stage49DurablePaperFence,
        synthetic_budget: Stage53SyntheticCapitalAuthority,
    ) -> None:
        if not isinstance(paper_fence, Stage49DurablePaperFence):
            raise TypeError("Stage49 paper fence required")
        if not isinstance(synthetic_budget, Stage53SyntheticCapitalAuthority):
            raise TypeError("Stage53 synthetic capital budget required")
        deployment = paper_fence._deployment
        account = deployment.config.account_id
        if paper_fence._account_id != account or synthetic_budget.account_id != account:
            raise Stage54ReconciliationBlocked("All participating local account IDs must match")
        if paper_fence._starting_cents != synthetic_budget.initial_cents:
            raise Stage54ReconciliationBlocked("Stage49 and Stage53 starting capital differs")
        if _cent_exact(deployment.config.starting_capital) != paper_fence._starting_cents:
            raise Stage54ReconciliationBlocked("Stage43 capital and Stage49 authority scope differ")
        paths = (
            paper_fence._db_path,
            synthetic_budget._path,
            deployment.config.research_db_path,
            deployment.config.virtual_state_dir / f"{account}_durable.db",
            Path(paper_fence._session._verifier.db_path),
        )
        if any(path.is_symlink() for path in paths):
            raise Stage54ReconciliationBlocked("Ledger/approval/coordinator DB symlink is unsupported")
        resolved = [path.resolve() for path in paths]
        if len(set(resolved)) != len(resolved):
            raise Stage54ReconciliationBlocked("Independent ledger DB files must not alias")
        self._fence = paper_fence
        self._budget = synthetic_budget
        self._paths = tuple(resolved)

    def inspect(self) -> Stage54RecoveryAssessment:
        """Read evidence, return manual-review classification; never act."""
        deployment = self._fence._deployment
        virtual = deployment.virtual_account
        issues: list[str] = []
        v_cash: int | None = None
        r_cash: int | None = None
        v_ok = r_ok = coordinator_ok = budget_ok = linked = False
        order_state = None
        attempt_count: int | None = None
        attempt_state = None
        unlinked_orders: int | None = None
        budget_held = budget_free = budget_count = None
        initial = self._fence._starting_cents

        # Reconcile each book independently. This is a series of local
        # inspections, NOT one common transaction across databases.
        try:
            rev = virtual._snapshot_revision
            if type(rev) is not int or rev < 0:
                issues.append("VIRTUAL_REVISION_UNVERIFIED")
            v_cash = _cent_exact(virtual.cash_balance)
            if virtual.account_id != deployment.config.account_id:
                issues.append("VIRTUAL_ACCOUNT_ID_MISMATCH")
            report = virtual.reconcile()
            v_ok = bool(report.is_reconciled)
            if not v_ok:
                issues.append("VIRTUAL_INTERNAL_RECONCILIATION_FAILED")
            if virtual.kill_switched:
                issues.append("EMERGENCY_KILL_SWITCH_ACTIVE")
        except Exception:
            issues.append("VIRTUAL_BOOK_UNAVAILABLE")
            rev = None

        try:
            ledger = deployment.research_ledger
            r_ok = bool(ledger.guarded_paper_mode and ledger.verify_integrity())
            research = ledger.status()
            r_cash = _cent_exact(research.cash_balance)
            if research.account_id != deployment.config.account_id:
                issues.append("RESEARCH_ACCOUNT_ID_MISMATCH")
            if _cent_exact(research.starting_capital) != initial:
                issues.append("RESEARCH_STARTING_CAPITAL_MISMATCH")
            if not r_ok:
                issues.append("RESEARCH_INTEGRITY_FAILED")
            if (research.open_order_count > 0 or research.reserved_cash != 0
                    or research.option_inventory):
                issues.append("RESEARCH_OUTSTANDING_RESERVATIONS_OR_INVENTORY")
            if research.live_orders_transmitted or research.approved_for_strategy_promotion:
                issues.append("RESEARCH_FORBIDDEN_AUTHORITY_CLAIM")
        except Exception:
            issues.append("RESEARCH_BOOK_UNAVAILABLE")

        if v_cash is None or r_cash is None or v_cash != r_cash:
            issues.append("SEPARATE_BOOK_CASH_MISMATCH_OR_UNAVAILABLE")
        if v_cash is not None and v_cash != initial:
            issues.append("VIRTUAL_CASH_CHANGED_FROM_INITIAL")
        if r_cash is not None and r_cash != initial:
            issues.append("RESEARCH_CASH_CHANGED_FROM_INITIAL")

        try:
            with closing(_read_only_sqlite(self._fence._db_path)) as conn:
                conn.execute("BEGIN")
                self._fence._verify_scope(conn)
                row = conn.execute(
                    "SELECT request_id,status,order_id,reference_exposure_cents,"
                    "virtual_revision,risk_policy_hash "
                    "FROM admission_attempts ORDER BY rowid"
                ).fetchall()
                coordinator_ok = True
                attempt_count = len(row)
                if attempt_count > 1:
                    issues.append("MULTIPLE_COORDINATOR_ATTEMPTS")
                if row:
                    rid, state, oid, exposure, reserved_revision, policy_hash = row[-1]
                    if state not in ("PREPARING", "PENDING", "UNKNOWN"):
                        issues.append("UNKNOWN_COORDINATOR_STATE")
                    attempt_state = state
                    if (not isinstance(rid, str) or not rid
                            or type(exposure) is not int or exposure <= 0
                            or type(reserved_revision) is not int or reserved_revision < 0
                            or not isinstance(policy_hash, str) or len(policy_hash) != 64):
                        issues.append("COORDINATOR_MARKER_FIELDS_INVALID")
                    if state == "PENDING":
                        if not isinstance(oid, str) or not oid:
                            issues.append("PENDING_COORDINATOR_MISSING_ORDER_ID")
                        elif oid not in virtual.orders:
                            issues.append("COORDINATOR_REFERENCES_MISSING_VIRTUAL_ORDER")
                        else:
                            linked = True
                            order_state = virtual.orders[oid].state.value
                    if state == "PREPARING":
                        issues.append("PREPARING_AFTER_CRASH_NEEDS_MANUAL_REVIEW")
                        if oid is not None:
                            issues.append("PREPARING_MARKER_HAS_UNEXPECTED_ORDER")
                    elif state == "UNKNOWN":
                        issues.append("UNKNOWN_ATTEMPT_OUTCOME_NEEDS_MANUAL_REVIEW")
                    elif state == "PENDING":
                        issues.append("PENDING_ATTEMPT_NEEDS_MANUAL_REVIEW")
                conn.rollback()  # end the read-only SQLite snapshot
        except (sqlite3.Error, OSError, ValueError, TypeError, Stage54ReconciliationBlocked, PermissionError):
            issues.append("COORDINATOR_SCOPE_OR_HISTORY_UNAVAILABLE")

        try:
            b = self._budget.inspect()
            budget_ok = b.local_integrity_verified
            if not budget_ok:
                issues.append("STAGE53_BUDGET_INTEGRITY_UNVERIFIED")
            if b.account_id != deployment.config.account_id or b.initial_cents != initial:
                issues.append("STAGE53_BUDGET_IDENTITY_MISMATCH")
            budget_held = b.held_cents
            budget_free = b.remaining_cents
            budget_count = b.hold_count
            if budget_count is not None and budget_count > 0:
                issues.append("UNLINKED_STANDALONE_BUDGET_HOLDS_NEED_MANUAL_REVIEW")
        except Exception:
            issues.append("STAGE53_BUDGET_UNAVAILABLE")

        try:
            total_orders = len(virtual.orders)
            unlinked_orders = total_orders - (1 if linked else 0)
            if unlinked_orders < 0:
                issues.append("VIRTUAL_ORDER_COUNT_CONTRADICTION")
                unlinked_orders = None
            elif unlinked_orders > 0:
                issues.append("VIRTUAL_ORDERS_OUTSIDE_STAGE49_MARKER")
            if type(rev) is int and virtual._snapshot_revision != rev:
                issues.append("VIRTUAL_REVISION_MOVED_DURING_AUDIT")
        except Exception:
            issues.append("VIRTUAL_ORDER_INVENTORY_UNAVAILABLE")

        # Explicitly independent business-state checks, not a global
        # transaction or a conclusion that outstanding holds are "free".
        if not coordinator_ok:
            issues.append("STAGE49_COORDINATOR_NOT_VERIFIED")
        if not budget_ok:
            issues.append("STAGE53_LOCAL_CAPITAL_NOT_VERIFIED")
        if not v_ok or not r_ok:
            issues.append("SOME_BOOK_INTEGRITY_NOT_VERIFIED")

        problems = tuple(dict.fromkeys(issues))
        manual = bool(problems)
        if "UNKNOWN_ATTEMPT_OUTCOME_NEEDS_MANUAL_REVIEW" in problems:
            disposition = "UNKNOWN_OUTCOME_QUARANTINE"
        elif "PREPARING_AFTER_CRASH_NEEDS_MANUAL_REVIEW" in problems:
            disposition = "PREPARING_CRASH_QUARANTINE"
        elif "PENDING_ATTEMPT_NEEDS_MANUAL_REVIEW" in problems:
            disposition = "PENDING_ORDER_MANUAL_REVIEW"
        elif problems:
            disposition = "INCONSISTENCY_MANUAL_REVIEW"
        else:
            disposition = "LOCAL_FLAT_COMPARISON_ONLY"
        steps = (
            "Do not create/replay paper orders or release synthetic budget holds automatically.",
            "Keep all four database files and audit evidence unchanged; acquire an independent operator review.",
            "Review Stage49 marker, exact virtual order state and Stage53 hold history against independent source records.",
            "Resolve any crash/missing order/fee/cash inconsistency using a separately reviewed recovery procedure.",
            "Re-run the full integrity/identity/risk audit before designing any write recovery or release.",
        ) if manual else (
            "Local separate-book snapshot appears flat; it is NOT an atomic shared capital ledger.",
            "Do not treat this read-only comparison as paper or live trading admission.",
        )

        return Stage54RecoveryAssessment(
            account_id=deployment.config.account_id,
            observed_initial_cents=initial,
            virtual_cash_cents=v_cash,
            research_cash_cents=r_cash,
            separate_book_cash_equal=(v_cash is not None and v_cash == r_cash == initial),
            virtual_internal_reconciled=v_ok,
            research_local_integrity_verified=r_ok,
            stage49_coordinator_scope_verified=coordinator_ok,
            coordinator_attempt_count=attempt_count,
            coordinator_state=attempt_state,
            coordinator_order_link_observed=linked,
            coordinator_linked_virtual_order_state=order_state,
            budget_local_integrity_verified=budget_ok,
            stage53_synthetic_held_cents=budget_held,
            stage53_synthetic_remaining_cents=budget_free,
            stage53_hold_count=budget_count,
            identified_unlinked_paper_orders=unlinked_orders,
            recovery_classification=disposition,
            manual_recovery_required=manual,
            diagnostic_codes=problems,
            manual_review_instructions=steps,
        )
