"""Stage20 recovery drill + multi-day research evidence tests; all synthetic."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3

import pytest

from nexus_titan.data.sessions import nse_equity_derivatives_baseline, TradingSession
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)
from nexus_titan.shadow.research_recovery_validation import (
    DailyResearchShadowRecord, ShadowEvidenceError,
    inspect_multiday_shadow_evidence, run_research_shadow_recovery_drill,
)

SOURCE_DAY = date(2026, 11, 2)


def _ledger(tmp_path, *, capital=50000.0, account="DEMO"):
    return DurableResearchShadowLedger(
        tmp_path / "original.sqlite3", account_id=account, starting_capital=capital
    )


def _drill(ledger, tmp_path, name="stage20-backup.sqlite3"):
    return run_research_shadow_recovery_drill(
        ledger, backup_path=tmp_path / name,
    )


def _close(day):
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).replace(
        hour=10, minute=1
    )  # 15:31 India time; post NSE regular-session close


def _row(day, status, delta=0.0, ref="synthetic/day-close"):
    return DailyResearchShadowRecord(
        session_date=day, observed_at=_close(day),
        status=status, expected_cash_change=delta, evidence_reference=ref,
    )


def _days(*rows, **settings):
    return inspect_multiday_shadow_evidence(
        list(rows), calendar=nse_equity_derivatives_baseline(), **settings,
    )


def test_restore_snapshot_rehearsal_preserves_account_and_audit(tmp_path):
    source = _ledger(tmp_path, capital=73000.0)
    result = _drill(source, tmp_path)
    assert result.passed
    assert result.account_id == "DEMO"
    assert result.original_snapshot == result.recovered_snapshot
    assert result.original_audit_event_count == result.restored_audit_event_count
    assert result.live_orders_transmitted == 0
    assert result.approved_for_strategy_promotion is False
    restored = DurableResearchShadowLedger(
        tmp_path / "stage20-backup.sqlite3", account_id="DEMO",
        starting_capital=73000.0,
    )
    assert restored.status() == source.status()


def test_backup_includes_open_reservations_and_cancel_survives_reopen(tmp_path):
    from nexus_titan.data.instrument_master import PointInTimeContractSpec
    d = SOURCE_DAY
    contract = PointInTimeContractSpec(
        symbol="TESTOPT", underlying="TEST", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=250,
        effective_from=d, effective_to=d + timedelta(days=4),
        expiry_date=d + timedelta(days=4), strike_step=50,
        source_reference="synthetic/contract-review", source_verified=True,
    )
    src = _ledger(tmp_path)
    src.reserve_buy(
        order_id="PENDING", contract=contract,
        strike=100.0, option_type="CE", lots=2,
        as_of=datetime.fromisoformat("2026-11-02T09:16:00+05:30"),
        max_unit_premium=6.0, fee_buffer=25.0,
    )
    snap = src.status()
    assert snap.reserved_cash == 325.0
    report = _drill(src, tmp_path)
    assert report.recovered_snapshot.open_order_count == 1
    restored = DurableResearchShadowLedger(
        tmp_path / "stage20-backup.sqlite3", account_id="DEMO",
        starting_capital=50000.0,
    )
    restored.cancel("PENDING")
    assert restored.status().reserved_cash == 0.0
    assert src.status() == snap  # Source was not modified.


def test_refuses_to_overwrite_original_db(tmp_path):
    ledger = _ledger(tmp_path)
    with pytest.raises(ShadowEvidenceError, match="never overwrite"):
        run_research_shadow_recovery_drill(ledger, backup_path=ledger.db_path)
    assert ledger.verify_integrity()


def test_refuses_existing_backup_without_modifying_bytes(tmp_path):
    ledger = _ledger(tmp_path)
    path = tmp_path / "existing.sqlite3"
    path.write_bytes(b"original content")
    with pytest.raises(ShadowEvidenceError, match="already exists"):
        run_research_shadow_recovery_drill(ledger, backup_path=path)
    assert path.read_bytes() == b"original content"


def test_rejects_missing_backup_parent(tmp_path):
    ledger = _ledger(tmp_path)
    with pytest.raises(ShadowEvidenceError, match="parent directory"):
        run_research_shadow_recovery_drill(
            ledger, backup_path=tmp_path / "missing" / "copy.sqlite3"
        )


def test_corrupted_source_blocked_and_no_backup_created(tmp_path):
    ledger = _ledger(tmp_path)
    with sqlite3.connect(ledger.db_path) as c:
        c.execute("UPDATE accounts SET cash_cents=cash_cents+7 WHERE account_id='DEMO'")
    with pytest.raises(ResearchLedgerError, match="state does not match"):
        _drill(ledger, tmp_path)
    assert not (tmp_path / "stage20-backup.sqlite3").exists()


def test_recovery_can_be_repeated_with_new_nonclobbering_destination(tmp_path):
    ledger = _ledger(tmp_path)
    _drill(ledger, tmp_path, "first.sqlite3")
    _drill(ledger, tmp_path, "second.sqlite3")
    assert (tmp_path / "first.sqlite3").is_file()
    assert (tmp_path / "second.sqlite3").is_file()


def test_separate_ledger_accounts_remain_isolated_during_recovery(tmp_path):
    a = _ledger(tmp_path, capital=50000.0, account="A")
    b = _ledger(tmp_path, capital=23000.0, account="B")
    report = _drill(a, tmp_path)
    assert report.recovered_snapshot.account_id == "A"
    restored = DurableResearchShadowLedger(
        tmp_path / "stage20-backup.sqlite3", account_id="B",
        starting_capital=23000.0
    )
    assert restored.status() == b.status()


def test_three_consecutive_day_closes_reconcile_structurally(tmp_path):
    src = _ledger(tmp_path)
    original = src.status()
    next_day = replace(
        original, cash_balance=49000.0, available_cash=49000.0,
        closed_order_count=1, audit_event_count=3,
    )
    days = [
        _row(SOURCE_DAY, original),
        _row(SOURCE_DAY + timedelta(days=1), next_day, -1000.0),
        _row(SOURCE_DAY + timedelta(days=2), next_day),
    ]
    out = _days(*days)
    assert out.is_structurally_valid, out.discrepancies
    assert out.total_cash_change == -1000
    assert out.session_count == 3
    assert out.live_orders_transmitted == 0
    assert not out.approved_for_strategy_promotion
    assert not out.data_source_authenticity_verified
    assert not out.external_broker_reconciliation_verified


def test_weekend_not_reported_missing(tmp_path):
    initial = _ledger(tmp_path).status()
    fri = date(2026, 10, 30)
    mon = date(2026, 11, 2)
    out = _days(_row(fri, initial), _row(mon, initial))
    assert out.is_structurally_valid and out.missing_session_dates == ()


def test_configured_exchange_holiday_not_counted_missing(tmp_path):
    stat = _ledger(tmp_path).status()
    fri = date(2026, 10, 30)
    tue = date(2026, 11, 3)
    calendar = nse_equity_derivatives_baseline(
        holidays=frozenset({SOURCE_DAY})
    )
    report = inspect_multiday_shadow_evidence(
        [_row(fri, stat), _row(tue, stat)], calendar=calendar,
    )
    assert report.is_structurally_valid


def test_missing_weekday_blocks_even_if_balances_match(tmp_path):
    s = _ledger(tmp_path).status()
    out = _days(
        _row(SOURCE_DAY, s),
        _row(SOURCE_DAY + timedelta(days=2), s),
    )
    assert not out.is_structurally_valid
    assert out.missing_session_dates == (SOURCE_DAY + timedelta(days=1),)


def test_duplicate_or_reverse_order_dates_are_blocked(tmp_path):
    s = _ledger(tmp_path).status()
    assert not _days(_row(SOURCE_DAY, s), _row(SOURCE_DAY, s)).is_structurally_valid
    reverse = _days(
        _row(SOURCE_DAY + timedelta(days=1), s),
        _row(SOURCE_DAY, s),
    )
    assert any("out-of-order" in x for x in reverse.discrepancies)


def test_non_session_day_or_unverified_calendar_rejected(tmp_path):
    s = _ledger(tmp_path).status()
    out = _days(_row(date(2026, 11, 7), s))
    assert any("not an exchange session" in x for x in out.discrepancies)
    with pytest.raises(ShadowEvidenceError, match="MarketCalendar"):
        inspect_multiday_shadow_evidence([_row(SOURCE_DAY, s)], calendar=None)


def test_day_close_must_be_post_session_close(tmp_path):
    s = _ledger(tmp_path).status()
    early = replace(
        _row(SOURCE_DAY, s),
        observed_at=datetime.fromisoformat("2026-11-02T14:00:00+05:30"),
    )
    assert any("before configured session close" in i for i in _days(early).discrepancies)


def test_wrong_local_calendar_day_rejected(tmp_path):
    s = _ledger(tmp_path).status()
    bad = replace(
        _row(SOURCE_DAY, s),
        observed_at=_close(SOURCE_DAY + timedelta(days=1)),
    )
    assert any("mismatches session date" in x for x in _days(bad).discrepancies)


def test_cash_and_reserve_conservation_are_checked(tmp_path):
    s = _ledger(tmp_path).status()
    bad = replace(s, reserved_cash=40.0, available_cash=s.cash_balance)
    out = _days(_row(SOURCE_DAY, bad))
    assert any("reservation mismatch" in x for x in out.discrepancies)
    assert any("overnight" in x for x in out.discrepancies)


def test_open_buy_orders_at_close_require_explicit_policy_override(tmp_path):
    s = _ledger(tmp_path).status()
    bad = replace(s, reserved_cash=100.0, available_cash=49900.0, open_order_count=1)
    result = _days(_row(SOURCE_DAY, bad))
    assert any("overnight" in x for x in result.discrepancies)
    allowed = _days(
        _row(SOURCE_DAY, bad), require_no_overnight_reservations=False
    )
    assert allowed.is_structurally_valid


def test_unexplained_cash_loss_detected(tmp_path):
    s = _ledger(tmp_path).status()
    delta = replace(s, cash_balance=49000.0, available_cash=49000.0, audit_event_count=2)
    out = _days(_row(SOURCE_DAY, delta, delta=0))
    assert any("cash delta reconciliation" in x for x in out.discrepancies)


def test_cash_increase_is_not_disguised_as_buy_research_pnl(tmp_path):
    s = _ledger(tmp_path).status()
    gain = replace(s, cash_balance=50100.0, available_cash=50100.0)
    out = _days(_row(SOURCE_DAY, gain, 100))
    assert any("cash increased" in x for x in out.discrepancies)


def test_account_and_initial_capital_cannot_change_across_days(tmp_path):
    s = _ledger(tmp_path).status()
    changed = replace(
        s, account_id="OTHER", starting_capital=12345,
    )
    result = _days(_row(SOURCE_DAY,s), _row(SOURCE_DAY+timedelta(days=1),changed))
    assert any("account changed" in x for x in result.discrepancies)
    assert any("opening capital changed" in x for x in result.discrepancies)


def test_audit_count_and_terminal_order_count_cannot_regress(tmp_path):
    s = replace(_ledger(tmp_path).status(), audit_event_count=10, closed_order_count=2)
    regress = replace(s, audit_event_count=3, closed_order_count=0)
    out = _days(_row(SOURCE_DAY,s), _row(SOURCE_DAY+timedelta(days=1),regress))
    assert any("audit-event count regressed" in x for x in out.discrepancies)
    assert any("terminal order count regressed" in x for x in out.discrepancies)


def test_buy_only_inventory_cannot_decrease(tmp_path):
    s = _ledger(tmp_path).status()
    first = replace(s, option_inventory=(("NSE|TESTOPT", 50),), audit_event_count=2)
    second = replace(first, option_inventory=(("NSE|TESTOPT", 25),), audit_event_count=3)
    out = _days(_row(SOURCE_DAY,first), _row(SOURCE_DAY+timedelta(days=1),second))
    assert any("inventory unexpectedly decreased" in x for x in out.discrepancies)


def test_fake_live_and_promotion_flags_block(tmp_path):
    s = _ledger(tmp_path).status()
    for fake in (replace(s, live_orders_transmitted=1),
                 replace(s, approved_for_strategy_promotion=True)):
        assert any("live/promotion" in x for x in _days(_row(SOURCE_DAY,fake)).discrepancies)


def test_missing_daily_evidence_reference_is_not_silent(tmp_path):
    s = _ledger(tmp_path).status()
    row = _row(SOURCE_DAY,s,ref="")
    assert any("missing daily evidence reference" in x for x in _days(row).discrepancies)


def test_naive_observation_rejected(tmp_path):
    s = _ledger(tmp_path).status()
    bad = replace(
        _row(SOURCE_DAY,s),
        observed_at=datetime(2026,11,2,15,31),
    )
    assert any("timezone-aware" in x for x in _days(bad).discrepancies)


def test_empty_evidence_never_passes_and_live_stays_disabled():
    result = _days()
    assert not result.is_structurally_valid
    assert not result.approved_for_strategy_promotion


@pytest.mark.parametrize("settings", [
    {"max_days": 0},
    {"max_days": True},
    {"max_missing_examples": 0},
    {"cash_tolerance": -1},
    {"cash_tolerance": float("nan")},
    {"cash_tolerance": float("inf")},
    {"require_no_overnight_reservations": "no"},
])
def test_bad_research_limits_rejected(tmp_path,settings):
    s = _ledger(tmp_path).status()
    with pytest.raises(ShadowEvidenceError):
        _days(_row(SOURCE_DAY,s),**settings)


def test_calendar_span_guard_limits_history(tmp_path):
    s = _ledger(tmp_path).status()
    out = _days(
        _row(SOURCE_DAY,s), _row(SOURCE_DAY + timedelta(days=10), s), max_days=2
    )
    assert not out.is_structurally_valid
    assert any("calendar-span" in x for x in out.discrepancies)


def test_report_deterministic_for_same_records(tmp_path):
    s = _ledger(tmp_path).status()
    rows = (_row(SOURCE_DAY,s),_row(SOURCE_DAY+timedelta(days=1),s))
    assert _days(*rows) == _days(*rows)
