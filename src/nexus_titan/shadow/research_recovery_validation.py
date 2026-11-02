"""Stage 20: offline, opt-in research ledger recovery and multi-session QA.

No broker connections, order routing, official NSE data, real P&L, or
automatic promotion. The submitted daily records are caller assertions.
"""
from __future__ import annotations

import math
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Sequence
from zoneinfo import ZoneInfo

from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerStatus,
)

_INDIA = ZoneInfo("Asia/Kolkata")


class ShadowEvidenceError(ValueError):
    """Fail closed if a recovery or research-history evidence gate fails."""


@dataclass(frozen=True, slots=True)
class ResearchRecoveryDrillReport:
    account_id: str
    backup_path: str
    original_audit_event_count: int
    restored_audit_event_count: int
    original_snapshot: ResearchLedgerStatus
    recovered_snapshot: ResearchLedgerStatus
    passed: bool
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


@dataclass(frozen=True, slots=True)
class DailyResearchShadowRecord:
    """Owner-supplied day-close state; not authenticated broker/exchange data."""

    session_date: date
    observed_at: datetime
    status: ResearchLedgerStatus
    expected_cash_change: float
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class MultiDayShadowEvidenceReport:
    account_id: str
    session_count: int
    missing_session_dates: tuple[date, ...]
    start_date: date | None
    end_date: date | None
    total_cash_change: float
    discrepancies: tuple[str, ...]
    data_source_authenticity_verified: bool = False
    external_broker_reconciliation_verified: bool = False
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False

    @property
    def is_structurally_valid(self) -> bool:
        return not self.discrepancies and not self.missing_session_dates


def run_research_shadow_recovery_drill(
    ledger: DurableResearchShadowLedger, *, backup_path: str | Path,
) -> ResearchRecoveryDrillReport:
    """SQLite online backup, reopen and compare; never overwrite an existing backup.

    Readable local SQLite backup proves only a *snapshot restore rehearsal*,
    not off-host recovery, hardware durability or external data authenticity.
    The original SQLite DB is never deleted, restored over, or modified by this
    function. A concurrent writer changing state during the drill fails closed.
    """
    if not isinstance(ledger, DurableResearchShadowLedger):
        raise ShadowEvidenceError("DurableResearchShadowLedger is required")
    if not isinstance(backup_path, (str, Path)) or not str(backup_path).strip():
        raise ShadowEvidenceError("backup_path must be a nonempty path")
    target = Path(backup_path)
    original = ledger.db_path.resolve()
    if target.resolve() == original:
        raise ShadowEvidenceError("Backup must never overwrite the source ledger")
    if target.exists():
        raise ShadowEvidenceError("Backup target already exists; refusing overwrite")
    if not target.parent.is_dir():
        raise ShadowEvidenceError("Backup parent directory must exist")
    if not ledger.verify_integrity():
        raise ShadowEvidenceError("Source ledger integrity verification failed")
    before = ledger.status()
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".titan-stage20-", suffix=".sqlite3", dir=target.parent, delete=False
        ) as handle:
            tmp_name = Path(handle.name)
        with sqlite3.connect(f"file:{original}?mode=ro", uri=True, timeout=10.0) as src:
            with sqlite3.connect(tmp_name, timeout=10.0) as dest:
                src.backup(dest)
        # Reopening the backup must independently pass the existing Stage19
        # audit+state verification (including persisted reservation/replay keys).
        recovered = DurableResearchShadowLedger(
            tmp_name, account_id=ledger.account_id, starting_capital=before.starting_capital
        )
        from_copy = recovered.status()
        after = ledger.status()
        if before != after or before != from_copy:
            raise ShadowEvidenceError("Recovery drill state mismatch / concurrent source update")
        if not recovered.verify_integrity():
            raise ShadowEvidenceError("Restored ledger integrity check failed")
        # Never replace a pre-existing path, even if it appeared after our precheck.
        if target.exists():
            raise ShadowEvidenceError("Backup target created concurrently; no overwrite")
        # os.link is exclusive and avoids os.replace silently clobbering target.
        os.link(tmp_name, target)
        return ResearchRecoveryDrillReport(
            ledger.account_id, str(target), before.audit_event_count,
            from_copy.audit_event_count, before, from_copy, True,
        )
    except (OSError, sqlite3.Error) as exc:
        raise ShadowEvidenceError(f"SQLite recovery drill failed: {exc}") from exc
    finally:
        if tmp_name is not None:
            tmp_name.unlink(missing_ok=True)


def inspect_multiday_shadow_evidence(
    records: Sequence[DailyResearchShadowRecord],
    *,
    calendar: MarketCalendar,
    max_days: int = 366,
    max_missing_examples: int = 25,
    cash_tolerance: float = 0.01,
    require_no_overnight_reservations: bool = True,
) -> MultiDayShadowEvidenceReport:
    """Check one day-close record per *configured* exchange trading session.

    Checks are between the first and last *provided* dates only. No record
    proves the original feed was genuine; no evidence triggers live trading.
    Expected cash changes are independently supplied research assumptions.
    """
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise ShadowEvidenceError("Reviewed Asia/Kolkata market calendar is required")
    if not isinstance(records, (list, tuple)):
        raise ShadowEvidenceError("records must be a bounded list or tuple")
    for field, value in (("max_days", max_days), ("max_missing_examples", max_missing_examples)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ShadowEvidenceError(f"{field} must be a positive integer")
    if (isinstance(cash_tolerance, bool) or not isinstance(cash_tolerance, (float, int))
            or not math.isfinite(cash_tolerance) or cash_tolerance < 0):
        raise ShadowEvidenceError("cash_tolerance must be finite and non-negative")
    if not isinstance(require_no_overnight_reservations, bool):
        raise ShadowEvidenceError("require_no_overnight_reservations must be boolean")
    if not records:
        return MultiDayShadowEvidenceReport("", 0, (), None, None, 0.0, ("No daily evidence provided",))
    if len(records) > max_days:
        raise ShadowEvidenceError("Daily evidence exceeds max_days")
    issues: list[str] = []
    account_id = None
    previous_date = None
    previous_cash = None
    previous_initial = None
    previous_audit_count = 0
    previous_terminal_orders = 0
    previous_inventory: dict[str, int] = {}
    previous_status: ResearchLedgerStatus | None = None
    total_delta = 0.0
    for index, item in enumerate(records):
        if not isinstance(item, DailyResearchShadowRecord):
            raise ShadowEvidenceError(f"Day {index}: DailyResearchShadowRecord required")
        day = item.session_date
        if not isinstance(day, date) or isinstance(day, datetime):
            raise ShadowEvidenceError(f"Day {index}: session_date must be a date")
        if previous_date is not None and day <= previous_date:
            issues.append(f"Day {index}: duplicate or out-of-order session date")
        previous_date = day
        if not calendar.is_trading_day(day):
            issues.append(f"Day {index}: date is not an exchange session")
        if (not isinstance(item.observed_at, datetime) or item.observed_at.tzinfo is None
                or item.observed_at.utcoffset() is None):
            issues.append(f"Day {index}: observed_at must be timezone-aware")
        else:
            local = item.observed_at.astimezone(_INDIA)
            if local.date() != day:
                issues.append(f"Day {index}: observation local date mismatches session date")
            sessions = calendar.sessions_for_date(day)
            if sessions and local.timetz().replace(tzinfo=None) < max(s.closes for s in sessions):
                issues.append(f"Day {index}: day-close observation before configured session close")

        status = item.status
        if not isinstance(status, ResearchLedgerStatus):
            raise ShadowEvidenceError(f"Day {index}: ResearchLedgerStatus required")
        if status.live_orders_transmitted != 0 or status.approved_for_strategy_promotion is not False:
            issues.append(f"Day {index}: live/promotion boundary violated")
        if not isinstance(item.evidence_reference, str) or not item.evidence_reference.strip():
            issues.append(f"Day {index}: missing daily evidence reference")
        if account_id is None:
            account_id = status.account_id
        elif account_id != status.account_id:
            issues.append(f"Day {index}: research account changed")
        if not isinstance(status.account_id, str) or not status.account_id.strip():
            issues.append(f"Day {index}: invalid account_id")
        amounts = (
            status.starting_capital, status.cash_balance, status.reserved_cash,
            status.available_cash, item.expected_cash_change,
        )
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in amounts):
            issues.append(f"Day {index}: non-finite money")
            continue
        if status.starting_capital <= 0 or status.cash_balance < 0 or status.reserved_cash < 0 or status.available_cash < 0:
            issues.append(f"Day {index}: invalid account funds")
        if abs(status.available_cash - (status.cash_balance - status.reserved_cash)) > cash_tolerance:
            issues.append(f"Day {index}: available-cash reservation mismatch")
        if require_no_overnight_reservations and (status.open_order_count > 0 or status.reserved_cash > cash_tolerance):
            issues.append(f"Day {index}: unresolved overnight virtual reservations")
        ints = (status.open_order_count, status.closed_order_count,
                status.cancelled_order_count, status.audit_event_count)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in ints):
            issues.append(f"Day {index}: invalid account/order counters")
        if previous_initial is not None and abs(status.starting_capital - previous_initial) > cash_tolerance:
            issues.append(f"Day {index}: opening capital changed")
        previous_initial = status.starting_capital
        if status.audit_event_count < previous_audit_count or status.audit_event_count < 1:
            issues.append(f"Day {index}: audit-event count regressed or vanished")
        if previous_status is not None and (
            status.cash_balance != previous_status.cash_balance
            or status.reserved_cash != previous_status.reserved_cash
            or status.open_order_count != previous_status.open_order_count
            or status.closed_order_count != previous_status.closed_order_count
            or status.cancelled_order_count != previous_status.cancelled_order_count
            or status.option_inventory != previous_status.option_inventory
        ) and status.audit_event_count <= previous_audit_count:
            issues.append(f"Day {index}: state changed without advancing audit evidence")
        previous_audit_count = status.audit_event_count
        previous_status = status
        terminal = status.closed_order_count + status.cancelled_order_count
        if terminal < previous_terminal_orders:
            issues.append(f"Day {index}: terminal order count regressed")
        previous_terminal_orders = terminal
        try:
            inventory = dict(status.option_inventory)
            if len(inventory) != len(status.option_inventory) or any(
                not isinstance(k, str) or not k or isinstance(q, bool)
                or not isinstance(q, int) or q < 0 for k, q in status.option_inventory
            ):
                raise ValueError("invalid inventory")
            if any(inventory.get(k, 0) < q for k, q in previous_inventory.items()):
                issues.append(f"Day {index}: BUY-only inventory unexpectedly decreased")
            previous_inventory = inventory
        except (TypeError, ValueError):
            issues.append(f"Day {index}: malformed inventory snapshot")

        opening = status.starting_capital if previous_cash is None else previous_cash
        actual_delta = round(status.cash_balance - opening, 2)
        expected_delta = round(item.expected_cash_change, 2)
        if actual_delta > cash_tolerance:
            issues.append(f"Day {index}: BUY-only research account cash increased unexpectedly")
        if abs(actual_delta - expected_delta) > cash_tolerance:
            issues.append(f"Day {index}: independent cash delta reconciliation failed")
        total_delta = round(total_delta + actual_delta, 2)
        previous_cash = status.cash_balance

    first_day, last_day = records[0].session_date, records[-1].session_date
    gap_days = (last_day - first_day).days
    if gap_days < 0 or gap_days > max_days:
        issues.append("Daily evidence calendar-span limit exceeded or reversed")
        return MultiDayShadowEvidenceReport(
            account_id or "", len(records), (), first_day, last_day, total_delta, tuple(issues)
        )
    actual_dates = {r.session_date for r in records}
    missing: list[date] = []
    for delta in range(gap_days + 1):
        d = first_day + timedelta(days=delta)
        if calendar.is_trading_day(d) and d not in actual_dates:
            if len(missing) < max_missing_examples:
                missing.append(d)
            else:
                issues.append("Missing session examples truncated; validation still blocked")
                break
    if missing:
        issues.append("Missing required configured exchange session records")
    return MultiDayShadowEvidenceReport(
        account_id or "", len(records), tuple(missing), first_day,
        last_day, total_delta, tuple(issues),
    )
