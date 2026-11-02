"""Stage 21: conservative offline shadow evidence *review-preparation* gate.

Submitted hashes and references are operator declarations, NOT independent
verification. Nothing in this module approves real trading or strategies.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError, ResearchLedgerStatus,
)
from nexus_titan.shadow.research_recovery_validation import (
    DailyResearchShadowRecord, ResearchRecoveryDrillReport,
    inspect_multiday_shadow_evidence,
)

REQUIRED_CATEGORIES: tuple[str, ...] = (
    "licensed_market_data", "official_contract_calendar",
    "broker_cost_schedule", "execution_calibration",
    "independent_security_assessment", "offsite_recovery_drill",
    "real_feed_multiday_shadow", "owner_signoff",
)
_SHA = re.compile(r"[a-fA-F0-9]{64}")


class ShadowReadinessError(ValueError):
    """No release can occur when research evidence is invalid."""


@dataclass(frozen=True, slots=True)
class ExternalEvidenceSubmission:
    category: str
    evidence_id: str
    reference: str
    claimed_sha256: str
    submitted_at: datetime


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    status: Literal["RESEARCH_PASS", "BLOCKED", "SUBMITTED_UNVERIFIED", "MISSING"]
    detail: str


@dataclass(frozen=True, slots=True)
class UnifiedShadowReadinessReport:
    account_id: str
    structural_session_count: int
    claimed_closed_trade_count: int
    evidence_submission_count: int
    checks: tuple[ReadinessCheck, ...]
    review_candidate: bool
    release_decision: Literal[
        "BLOCKED_STRUCTURAL_VALIDATION", "BLOCKED_EXTERNAL_EVIDENCE",
        "INDEPENDENT_REVIEW_REQUIRED",
    ]
    live_trading_enabled: bool = False
    automatic_strategy_promotion: bool = False
    external_authenticity_verified: bool = False
    official_market_data_verified: bool = False

    @property
    def blocked_checks(self) -> tuple[str, ...]:
        return tuple(x.name for x in self.checks if x.status in ("BLOCKED", "MISSING"))


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _check_int(value: int, name: str, *, zero: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < (0 if zero else 1):
        raise ShadowReadinessError(f"{name} must be a {'non-negative' if zero else 'positive'} integer")


def _submission_valid(item: ExternalEvidenceSubmission, as_of: datetime) -> tuple[bool, str]:
    if not isinstance(item, ExternalEvidenceSubmission):
        return False, "Not an ExternalEvidenceSubmission"
    if item.category not in REQUIRED_CATEGORIES:
        return False, "Unknown evidence category"
    if not isinstance(item.evidence_id, str) or not item.evidence_id.strip() or len(item.evidence_id) > 128:
        return False, "Invalid evidence ID"
    if not isinstance(item.reference, str) or not item.reference.strip() or len(item.reference) > 1024:
        return False, "Missing or oversized source reference"
    if not isinstance(item.claimed_sha256, str) or not _SHA.fullmatch(item.claimed_sha256):
        return False, "Invalid claimed SHA-256"
    if not _aware(item.submitted_at) or item.submitted_at > as_of:
        return False, "Missing or future submission timestamp"
    return True, "Document pointer and caller-provided digest only; source not authenticated"


def _local_recovery_check(
    ledger: DurableResearchShadowLedger,
    recovery: ResearchRecoveryDrillReport | None,
    current: ResearchLedgerStatus,
) -> tuple[bool, str]:
    if not isinstance(recovery, ResearchRecoveryDrillReport) or recovery.passed is not True:
        return False, "No successful local Stage20 recovery report"
    if (recovery.account_id != current.account_id or
            recovery.original_snapshot != current or
            recovery.recovered_snapshot != current or
            recovery.original_audit_event_count != current.audit_event_count or
            recovery.restored_audit_event_count != current.audit_event_count or
            recovery.live_orders_transmitted != 0 or
            recovery.approved_for_strategy_promotion is not False):
        return False, "Recovery report does not match current research account"
    try:
        backup = Path(recovery.backup_path)
        if not backup.is_file() or backup.is_symlink() or backup.resolve() == ledger.db_path.resolve():
            return False, "Backup is missing, linked, or unsafe"
        restored = DurableResearchShadowLedger(
            backup, account_id=current.account_id, starting_capital=current.starting_capital
        )
        if not restored.verify_integrity() or restored.status() != current:
            return False, "Actual reopened SQLite backup differs from research account"
    except (OSError, TypeError, ValueError, sqlite3.Error) as exc:
        return False, f"Recovery backup read failed: {type(exc).__name__}"
    return True, "Local SQLite restore matched; independent offsite recovery NOT verified"


def prepare_unified_shadow_readiness(
    *,
    ledger: DurableResearchShadowLedger,
    daily_records: list[DailyResearchShadowRecord] | tuple[DailyResearchShadowRecord, ...],
    calendar: MarketCalendar,
    recovery: ResearchRecoveryDrillReport | None,
    evidence_submissions: list[ExternalEvidenceSubmission] | tuple[ExternalEvidenceSubmission, ...],
    claimed_closed_trades: int = 0,
    minimum_sessions: int = 20,
    minimum_closed_trades: int = 30,
    as_of: datetime,
) -> UnifiedShadowReadinessReport:
    """Prepare an evidence checklist only, never an approval to deploy/live trade.

    Submitted real-feed/session/trade counts and document hashes can be faked
    by a caller. Even a complete packet only advances to independent review.
    """
    if not isinstance(ledger, DurableResearchShadowLedger):
        raise ShadowReadinessError("Stage19 durable research ledger required")
    if not _aware(as_of):
        raise ShadowReadinessError("as_of must be timezone-aware")
    for name, val, zero in (
        ("claimed_closed_trades", claimed_closed_trades, True),
        ("minimum_sessions", minimum_sessions, False),
        ("minimum_closed_trades", minimum_closed_trades, False),
    ):
        _check_int(val, name, zero=zero)
    if not isinstance(daily_records, (tuple, list)) or not isinstance(evidence_submissions, (tuple, list)):
        raise ShadowReadinessError("Bounded lists or tuples required")
    if len(evidence_submissions) > len(REQUIRED_CATEGORIES):
        raise ShadowReadinessError("Too many evidence submissions")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise ShadowReadinessError("Reviewed Asia/Kolkata MarketCalendar required")

    try:
        current = ledger.status()
        ledger_ok = ledger.verify_integrity()
    except (ResearchLedgerError, OSError, sqlite3.Error, ValueError) as exc:
        raise ShadowReadinessError("Research account fails source integrity checks") from exc

    checks: list[ReadinessCheck] = [ReadinessCheck(
        "research_ledger_integrity", "RESEARCH_PASS" if ledger_ok else "BLOCKED",
        "Stage19 local SQLite chain and conservation only; exchange authenticity not established",
    )]
    structural_ok = ledger_ok
    quality = inspect_multiday_shadow_evidence(daily_records, calendar=calendar)
    dates_ok = quality.is_structurally_valid and quality.account_id == current.account_id
    if daily_records and daily_records[-1].status != current:
        dates_ok = False
    if daily_records and any(
        not _aware(item.observed_at) or item.observed_at > as_of for item in daily_records
    ):
        dates_ok = False
    checks.append(ReadinessCheck(
        "multi_day_structural_continuity",
        "RESEARCH_PASS" if dates_ok else "BLOCKED",
        "Operator-supplied daily records only" if dates_ok else "; ".join(quality.discrepancies[:6]) or "Latest day disagrees with SQLite",
    ))
    structural_ok &= dates_ok
    enough_sessions = dates_ok and quality.session_count >= minimum_sessions
    checks.append(ReadinessCheck(
        "minimum_research_sessions",
        "RESEARCH_PASS" if enough_sessions else "BLOCKED",
        f"{quality.session_count}/{minimum_sessions} submitted structural sessions; not authenticated real-feed days",
    ))
    structural_ok &= enough_sessions
    restored_ok, restored_detail = _local_recovery_check(ledger, recovery, current)
    checks.append(ReadinessCheck(
        "local_sqlite_recovery_drill",
        "RESEARCH_PASS" if restored_ok else "BLOCKED", restored_detail,
    ))
    structural_ok &= restored_ok
    enough_trades = claimed_closed_trades >= minimum_closed_trades
    checks.append(ReadinessCheck(
        "claimed_trade_count_for_review",
        "RESEARCH_PASS" if enough_trades else "BLOCKED",
        f"{claimed_closed_trades}/{minimum_closed_trades} operator-claimed closed trades; "
        "Stage19 BUY-only orders cannot verify completed round trips",
    ))
    structural_ok &= enough_trades

    seen_categories: set[str] = set()
    seen_ids: set[str] = set()
    accepted: set[str] = set()
    for index, item in enumerate(evidence_submissions):
        valid, detail = _submission_valid(item, as_of)
        if not valid:
            checks.append(ReadinessCheck(f"invalid_evidence_{index}", "BLOCKED", detail))
            structural_ok = False
            continue
        if item.category in seen_categories or item.evidence_id in seen_ids:
            checks.append(ReadinessCheck(
                f"duplicate_evidence_{index}", "BLOCKED", "Duplicate evidence ID or category"
            ))
            structural_ok = False
            continue
        seen_categories.add(item.category)
        seen_ids.add(item.evidence_id)
        accepted.add(item.category)
    for category in REQUIRED_CATEGORIES:
        present = category in accepted
        checks.append(ReadinessCheck(
            category, "SUBMITTED_UNVERIFIED" if present else "MISSING",
            "Submitted pointer only; external authenticity and licence NOT verified"
            if present else "Required external evidence has not been submitted",
        ))
    all_submitted = len(accepted) == len(REQUIRED_CATEGORIES)
    review_candidate = structural_ok and all_submitted
    decision = (
        "BLOCKED_STRUCTURAL_VALIDATION" if not structural_ok else
        "BLOCKED_EXTERNAL_EVIDENCE" if not all_submitted else
        "INDEPENDENT_REVIEW_REQUIRED"
    )
    return UnifiedShadowReadinessReport(
        account_id=current.account_id,
        structural_session_count=quality.session_count,
        claimed_closed_trade_count=claimed_closed_trades,
        evidence_submission_count=len(accepted), checks=tuple(checks),
        review_candidate=review_candidate, release_decision=decision,
    )
