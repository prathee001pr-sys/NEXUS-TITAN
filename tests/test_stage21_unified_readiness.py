"""Stage21 strictly offline readiness checklist tests with synthetic claims only."""
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import hashlib
import sqlite3

import pytest

from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.shadow.research_recovery_validation import (
    DailyResearchShadowRecord, run_research_shadow_recovery_drill,
)
from nexus_titan.shadow.unified_readiness import (
    ExternalEvidenceSubmission, REQUIRED_CATEGORIES, ShadowReadinessError,
    prepare_unified_shadow_readiness,
)

INDIA = ZoneInfo("Asia/Kolkata")
AS_OF = datetime(2026, 11, 2, 20, 0, tzinfo=INDIA)


def _ledger(tmp_path):
    return DurableResearchShadowLedger(
        tmp_path / "source.sqlite3", account_id="TEST-RESEARCH", starting_capital=75000.0
    )


def _records(ledger, count=20):
    cal = nse_equity_derivatives_baseline()
    rows = []
    day = date(2026, 9, 30)
    while len(rows) < count:
        if cal.is_trading_day(day):
            rows.append(DailyResearchShadowRecord(
                session_date=day, observed_at=datetime.combine(
                    day, time(15, 31), tzinfo=INDIA
                ),
                status=ledger.status(), expected_cash_change=0.0,
                evidence_reference=f"synthetic/ledger-day-{day.isoformat()}",
            ))
        day += timedelta(days=1)
    return rows


def _documents(*, submitted_at=None):
    submitted_at = submitted_at or AS_OF
    return [
        ExternalEvidenceSubmission(
            category=category, evidence_id=f"synthetic-evidence-{index}",
            reference=f"research/claims/{category}",
            claimed_sha256=hashlib.sha256(category.encode()).hexdigest(),
            submitted_at=submitted_at,
        ) for index, category in enumerate(REQUIRED_CATEGORIES)
    ]


def _setup(tmp_path, count=20):
    ledger = _ledger(tmp_path)
    recovery = run_research_shadow_recovery_drill(
        ledger, backup_path=tmp_path / "stage21-backup.sqlite3"
    )
    return ledger, recovery, _records(ledger, count)


def _run(ledger, default_recovery, records, **kwargs):
    args = dict(
        ledger=ledger, daily_records=records,
        calendar=nse_equity_derivatives_baseline(), recovery=default_recovery,
        evidence_submissions=[], claimed_closed_trades=0, as_of=AS_OF,
    )
    args.update(kwargs)
    return prepare_unified_shadow_readiness(**args)


def test_empty_external_evidence_blocks_even_with_valid_local_research(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    report = _run(ledger, rec, days, claimed_closed_trades=30)
    assert report.release_decision == "BLOCKED_EXTERNAL_EVIDENCE"
    assert not report.review_candidate
    assert report.evidence_submission_count == 0
    assert len(report.blocked_checks) == len(REQUIRED_CATEGORIES)
    assert all(x.status == "MISSING" for x in report.checks[-len(REQUIRED_CATEGORIES):])
    assert report.live_trading_enabled is False
    assert report.automatic_strategy_promotion is False


def test_all_submitted_documents_advance_only_to_external_review_not_approval(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    report = _run(
        ledger, rec, days, evidence_submissions=_documents(), claimed_closed_trades=30,
    )
    assert report.review_candidate
    assert report.release_decision == "INDEPENDENT_REVIEW_REQUIRED"
    assert report.evidence_submission_count == len(REQUIRED_CATEGORIES)
    assert all(x.status == "SUBMITTED_UNVERIFIED"
               for x in report.checks[-len(REQUIRED_CATEGORIES):])
    assert report.external_authenticity_verified is False
    assert report.official_market_data_verified is False
    assert report.live_trading_enabled is False
    assert report.automatic_strategy_promotion is False
    assert report.blocked_checks == ()


def test_minimum_sessions_unmet_blocks_even_when_documents_submitted(tmp_path):
    ledger, rec, days = _setup(tmp_path, count=3)
    report = _run(ledger, rec, days, evidence_submissions=_documents(),
                  claimed_closed_trades=30)
    assert report.release_decision == "BLOCKED_STRUCTURAL_VALIDATION"
    assert "minimum_research_sessions" in report.blocked_checks


def test_operator_trade_count_below_minimum_blocks(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    report = _run(ledger, rec, days, evidence_submissions=_documents(),
                  claimed_closed_trades=29)
    assert "claimed_trade_count_for_review" in report.blocked_checks
    assert not report.review_candidate


def test_claimed_closed_trades_never_become_verified_trades(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    report = _run(ledger, rec, days, evidence_submissions=_documents(),
                  claimed_closed_trades=90000)
    assert report.review_candidate
    assert report.release_decision == "INDEPENDENT_REVIEW_REQUIRED"
    assert report.live_trading_enabled is False


def test_missing_backup_blocks_even_if_someone_forges_passed_flag(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    (tmp_path / "stage21-backup.sqlite3").unlink()
    report = _run(ledger, rec, days, recovery=rec,
                  evidence_submissions=_documents(), claimed_closed_trades=30)
    assert "local_sqlite_recovery_drill" in report.blocked_checks


def test_none_recovery_is_rejected_as_structural_missing(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    result = _run(ledger, rec, days, recovery=None,
                  evidence_submissions=_documents(), claimed_closed_trades=30)
    assert not result.review_candidate
    assert "local_sqlite_recovery_drill" in result.blocked_checks


def test_wrong_backup_snapshot_metadata_does_not_count_as_drill(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    forged = replace(rec, restored_audit_event_count=100000)
    result = _run(ledger, rec, days, recovery=forged,
                  evidence_submissions=_documents(), claimed_closed_trades=30)
    assert "local_sqlite_recovery_drill" in result.blocked_checks


def test_tampered_backup_rejected_on_actual_reopen(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    with sqlite3.connect(tmp_path / "stage21-backup.sqlite3") as db:
        db.execute("UPDATE accounts SET cash_cents=cash_cents-100")
    result = _run(ledger, rec, days, recovery=rec,
                  evidence_submissions=_documents(), claimed_closed_trades=30)
    assert "local_sqlite_recovery_drill" in result.blocked_checks


def test_last_daily_snapshot_must_match_current_ledger(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    last = days[-1]
    days[-1] = replace(
        last, status=replace(last.status, cash_balance=last.status.cash_balance-10,
                             available_cash=last.status.available_cash-10),
        expected_cash_change=-10.0,
    )
    result = _run(ledger, rec, days, evidence_submissions=_documents(),
                  claimed_closed_trades=30)
    assert "multi_day_structural_continuity" in result.blocked_checks


def test_missing_middle_calendar_session_blocks_complete_document_packet(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    omitted = days[:9] + days[10:]
    report = _run(ledger, rec, omitted, evidence_submissions=_documents(),
                  claimed_closed_trades=30)
    assert "multi_day_structural_continuity" in report.blocked_checks


def test_duplicate_daily_date_blocks(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    days[5] = days[4]
    report = _run(ledger, rec, days, evidence_submissions=_documents(),
                  claimed_closed_trades=30)
    assert "multi_day_structural_continuity" in report.blocked_checks


def test_future_day_close_reference_is_blocked(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    days[-1] = replace(days[-1], observed_at=AS_OF + timedelta(days=1))
    report = _run(ledger, rec, days, evidence_submissions=_documents(),
                  claimed_closed_trades=30)
    assert "multi_day_structural_continuity" in report.blocked_checks


@pytest.mark.parametrize("change", [
    {"category": "unknown"},
    {"evidence_id": ""},
    {"reference": ""},
    {"claimed_sha256": "abc"},
    {"claimed_sha256": "g" * 64},
    {"submitted_at": datetime(2026, 11, 2, 12, 0)},
    {"submitted_at": AS_OF + timedelta(seconds=1)},
])
def test_invalid_external_claim_cannot_fill_required_category(tmp_path, change):
    ledger, rec, days = _setup(tmp_path)
    docs = _documents()
    docs[0] = replace(docs[0], **change)
    report = _run(ledger, rec, days, evidence_submissions=docs,
                  claimed_closed_trades=30)
    assert report.release_decision == "BLOCKED_STRUCTURAL_VALIDATION"
    assert not report.review_candidate
    assert any(x.name.startswith("invalid_evidence_") for x in report.checks)


def test_duplicate_category_even_with_different_ids_fails(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    docs = _documents()
    docs[1] = replace(docs[1], category=docs[0].category)
    report = _run(ledger, rec, days, evidence_submissions=docs,
                  claimed_closed_trades=30)
    assert any(x.name.startswith("duplicate_evidence_") for x in report.checks)
    assert report.release_decision == "BLOCKED_STRUCTURAL_VALIDATION"


def test_duplicate_ids_with_different_categories_fail(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    docs = _documents()
    docs[1] = replace(docs[1], evidence_id=docs[0].evidence_id)
    report = _run(ledger, rec, days, evidence_submissions=docs,
                  claimed_closed_trades=30)
    assert any(x.name.startswith("duplicate_evidence_") for x in report.checks)


def test_only_seven_categories_cannot_pass_full_external_evidence_gate(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    report = _run(ledger, rec, days, evidence_submissions=_documents()[:-1],
                  claimed_closed_trades=30)
    assert report.release_decision == "BLOCKED_EXTERNAL_EVIDENCE"
    assert "owner_signoff" in report.blocked_checks


def test_empty_daily_records_never_advance_to_review(tmp_path):
    ledger, rec, _ = _setup(tmp_path)
    report = _run(ledger, rec, [], evidence_submissions=_documents(),
                  claimed_closed_trades=30)
    assert report.release_decision == "BLOCKED_STRUCTURAL_VALIDATION"


def test_source_ledger_tampering_does_not_get_a_readiness_report(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    with sqlite3.connect(ledger.db_path) as db:
        db.execute("UPDATE accounts SET cash_cents=cash_cents+1")
    with pytest.raises(ShadowReadinessError, match="source integrity"):
        _run(ledger, rec, days, evidence_submissions=_documents(),
             claimed_closed_trades=30)


@pytest.mark.parametrize("override", [
    {"claimed_closed_trades": -1},
    {"claimed_closed_trades": True},
    {"minimum_sessions": 0},
    {"minimum_sessions": True},
    {"minimum_closed_trades": 0},
    {"as_of": datetime(2026, 11, 2, 20, 0)},
    {"calendar": None},
    {"daily_records": "not-records"},
    {"evidence_submissions": "not-evidence"},
])
def test_invalid_configuration_fails_closed(tmp_path, override):
    ledger, rec, days = _setup(tmp_path)
    with pytest.raises(ShadowReadinessError):
        _run(ledger, rec, days, **override)


def test_too_many_external_documents_is_invalid(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    with pytest.raises(ShadowReadinessError, match="Too many"):
        _run(ledger, rec, days, evidence_submissions=_documents()+_documents()[:1])


def test_report_is_repeatable_and_does_not_enable_trading(tmp_path):
    ledger, rec, days = _setup(tmp_path)
    one = _run(ledger, rec, days, evidence_submissions=_documents(),
               claimed_closed_trades=30)
    two = _run(ledger, rec, days, evidence_submissions=_documents(),
               claimed_closed_trades=30)
    assert one == two
    assert not one.live_trading_enabled
    assert not two.automatic_strategy_promotion
    assert ledger.status().cash_balance == 75000.0
