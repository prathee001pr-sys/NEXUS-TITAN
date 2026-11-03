"""Stage64: adversarial prospective synthetic shadow validation governance.

All trial records are untrusted, fabricated or operator-claimed. Verify
cash/event conservation and local acceptance metrics, never allow
automatic promotion, real fills, signed registration or live trades.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.operations.integration_candidate_audit import inspect_stage62_candidate
from nexus_titan.research.stage61_evidence_scorecard import inspect_stage61_fo_evidence
from nexus_titan.shadow.stage64_trial_governance import (
    Stage64DailyClaim, Stage64TrialBlocked, Stage64TrialPlan,
    inspect_stage64_shadow_trial,
)
from scripts.run_stage61_fo_evidence_smoke import _inputs
from scripts.run_stage64_shadow_trial_smoke import _trial, CAL

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.fromisoformat("2026-09-29T12:00:00+05:30")


@pytest.fixture(scope="module")
def integration():
    snapshot = json.loads(
        (ROOT / "docs/STAGE62_PR_DEPENDENCY_SNAPSHOT_2026-11-03.json").read_text()
    )
    return inspect_stage62_candidate(ROOT, pr_snapshot=snapshot)


def _inputs_for(tmp_path, integration, *, underlying="NIFTY", plan=None, days=None, **options):
    h, o, e = _inputs(tmp_path / "data", underlying)
    fo = inspect_stage61_fo_evidence(h, o, execution=e)
    base, originals = _trial(underlying)
    return inspect_stage64_shadow_trial(
        plan or base, days if days is not None else originals,
        calendar=options.pop("calendar", CAL),
        as_of=options.pop("as_of", NOW),
        fo_evidence=options.pop("fo_evidence", fo),
        integration=options.pop("integration", integration),
        **options,
    )


def _assert_no_release(r):
    assert r.schema_version == 1
    assert r.release_decision == "BLOCKED_INDEPENDENT_EXTERNAL_EVIDENCE_REQUIRED"
    assert not r.data_source_independently_authenticated
    assert not r.real_fill_or_fee_calibration_verified
    assert not r.genuine_net_pnl_verified
    assert not r.prospectively_signed_trial_plan_verified
    assert not r.audited_full_portfolio_pnl_verified
    assert not r.independently_verified_human_approval
    assert not r.one_authoritative_capital_authority_verified
    assert not r.global_risk_veto_enforced
    assert not r.merge_authorized
    assert not r.strategy_promotion_authorized
    assert not r.live_trading_enabled
    assert not r.production_ready
    assert r.broker_orders_transmitted == 0
    assert len(r.mandatory_external_blockers) == 8


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_complete_20_session_claims_pass_local_criteria_but_external_is_blocked(
    tmp_path, integration, underlying,
):
    r = _inputs_for(tmp_path, integration, underlying=underlying)
    assert r.underlying == underlying
    assert r.supplied_sessions == r.expected_trading_sessions == 20
    assert r.missing_session_dates == ()
    assert r.declared_closed_trades == 40
    assert r.declared_execution_observations == 80
    assert r.gross_winning_cents == 60000
    assert r.gross_losing_cents == 20000
    assert r.fees_cents == 4000
    assert r.slippage_cents == 2000
    assert r.claimed_net_pnl_cents == 34000
    assert r.claimed_gross_profit_factor == Decimal("3")
    assert r.claimed_net_expectancy_cents == Decimal("850")
    assert r.observed_closing_day_drawdown_bps == 0
    assert r.claimed_max_intraday_drawdown_bps == 100
    assert r.local_trial_criteria_met
    assert len(r.local_trial_sha256) == 64
    assert r.stage61_local_structural_check_observed
    assert r.stage62_local_static_check_observed
    assert len(r.checks) >= 14
    assert all(x.locally_met for x in r.checks)
    _assert_no_release(r)


def test_variable_capital_not_fixed_to_50000(tmp_path, integration):
    initial = 1_250_000  # ₹12,500
    plan, days = _trial(starting_capital=initial)
    r = _inputs_for(tmp_path, integration, plan=plan, days=days)
    assert plan.starting_capital_cents == initial
    assert r.claimed_net_pnl_cents == 34000
    assert r.local_trial_criteria_met
    _assert_no_release(r)


def test_deterministic_read_only_same_inputs_same_digest(tmp_path, integration):
    plan, days = _trial()
    path = tmp_path / "data" / "futures.csv"
    a = _inputs_for(tmp_path, integration, plan=plan, days=days)
    original = path.read_bytes()
    b = _inputs_for(tmp_path, integration, plan=plan, days=days)
    assert a == b
    assert a.local_trial_sha256 == b.local_trial_sha256
    assert path.read_bytes() == original
    assert not list(tmp_path.rglob("*.sqlite*"))
    _assert_no_release(a)


def test_missing_middle_market_day_detected_even_with_good_accounting_elsewhere(tmp_path, integration):
    plan, days = _trial()
    removed = days[:10] + days[11:]
    r = _inputs_for(tmp_path, integration, plan=plan, days=removed)
    assert r.missing_session_dates == (days[10].session_date,)
    assert not r.local_trial_criteria_met
    assert not _check(r, "no_selectively_omitted_trading_days")
    assert not _check(r, "cash_continuity_and_cost_conservation")
    _assert_no_release(r)


def test_cash_drift_is_reported_not_promoted(tmp_path, integration):
    plan, days = _trial()
    altered = replace(days[5], closing_cash_cents=days[5].closing_cash_cents + 1)
    r = _inputs_for(tmp_path, integration, plan=plan,
                    days=days[:5] + (altered,) + days[6:])
    assert not _check(r, "cash_continuity_and_cost_conservation")
    assert not r.local_trial_criteria_met
    _assert_no_release(r)


def test_fee_omission_detected_by_balance_reconciliation(tmp_path, integration):
    plan, days = _trial()
    altered = replace(days[5], fees_cents=days[5].fees_cents + 1)
    r = _inputs_for(tmp_path, integration, plan=plan,
                    days=days[:5] + (altered,) + days[6:])
    assert not _check(r, "cash_continuity_and_cost_conservation")
    assert r.fees_cents == 4001
    _assert_no_release(r)


def test_risk_breach_suppresses_local_governance_pass(tmp_path, integration):
    plan, days = _trial()
    updated = replace(days[4], risk_limit_breaches=1)
    r = _inputs_for(tmp_path, integration, plan=plan,
                    days=days[:4] + (updated,) + days[5:])
    assert not _check(r, "no_risk_policy_breach")
    _assert_no_release(r)


def test_intraday_drawdown_exceeds_plan_gate(tmp_path, integration):
    plan, days = _trial()
    updated = replace(days[4], claimed_max_intraday_drawdown_bps=1200)
    r = _inputs_for(tmp_path, integration, plan=plan,
                    days=days[:4] + (updated,) + days[5:])
    assert not _check(r, "no_risk_policy_breach")
    assert not _check(r, "peak_to_close_drawdown_threshold")
    _assert_no_release(r)


@pytest.mark.parametrize("field,value,expected", [
    ("missing_market_observations", 1, "calendar_session_data_quality"),
    ("data_quality_checked", False, "calendar_session_data_quality"),
    ("paper_orders_reconciled", False, "all_orders_reconciled_flat"),
    ("unresolved_orders", 1, "all_orders_reconciled_flat"),
    ("unvalued_open_positions", 1, "all_orders_reconciled_flat"),
    ("execution_observations", 1, "execution_observation_coverage"),
])
def test_broken_data_fill_or_position_claim_blocks_local_pass(
    tmp_path, integration, field, value, expected,
):
    plan, days = _trial()
    modified = tuple(replace(x, **{field: value}) for x in days)
    r = _inputs_for(tmp_path, integration, plan=plan, days=modified)
    assert not _check(r, expected)
    assert not r.local_trial_criteria_met
    _assert_no_release(r)


def _check(r, name):
    return next(x.locally_met for x in r.checks if x.name == name)


def _rebuild_cash(rows):
    revised = []
    value = rows[0].opening_cash_cents
    for row in rows:
        result = value + row.gross_winning_cents - row.gross_losing_cents - row.fees_cents - row.slippage_cents
        revised.append(replace(row, opening_cash_cents=value, closing_cash_cents=result))
        value = result
    return tuple(revised)


def test_gross_profit_factor_alone_cannot_hide_net_negative_costs(tmp_path, integration):
    plan, days = _trial()
    altered = _rebuild_cash(tuple(replace(x, fees_cents=4000) for x in days))
    r = _inputs_for(tmp_path, integration, plan=plan, days=altered)
    assert r.claimed_gross_profit_factor == Decimal("3")
    assert r.claimed_net_pnl_cents < 0
    assert not _check(r, "net_expectancy_and_total_net_threshold")
    assert not r.local_trial_criteria_met
    _assert_no_release(r)


def test_no_gross_losses_is_unknown_pf_not_infinite_winrate(tmp_path, integration):
    plan, days = _trial()
    altered = _rebuild_cash(tuple(replace(
        x, gross_losing_cents=0, losing_trades=0, closed_trades=1,
    ) for x in days))
    r = _inputs_for(tmp_path, integration, plan=plan, days=altered)
    assert r.claimed_gross_profit_factor is None
    assert not _check(r, "gross_profit_factor_threshold")
    assert not _check(r, "minimum_closed_trade_sample")
    assert not r.local_trial_criteria_met
    _assert_no_release(r)


@pytest.mark.parametrize("field,value", [
    ("winning_trades", 0),
    ("closed_trades", 1),
    ("losing_trades", True),
    ("gross_winning_cents", 0),
    ("gross_losing_cents", -1),
    ("fees_cents", 1.5),
    ("slippage_cents", -1),
    ("execution_observations", -1),
    ("opening_cash_cents", False),
    ("closing_cash_cents", 10**15),
])
def test_tampered_trade_count_or_nonnumeric_money_rejected(
    tmp_path, integration, field, value,
):
    plan, days = _trial()
    altered = replace(days[1], **{field: value})
    with pytest.raises(Stage64TrialBlocked):
        _inputs_for(tmp_path, integration, plan=plan,
                    days=days[:1] + (altered,) + days[2:])


@pytest.mark.parametrize("field,value", [
    ("independently_authenticated_data", True),
    ("independently_authenticated_fills", True),
    ("real_money_order_sent", True),
    ("source_class", "REAL_BROKER_APPROVED"),
    ("account_id", "ANOTHER"),
    ("underlying", "BANKNIFTY"),
    ("evidence_reference", ""),
])
def test_untrusted_day_cannot_claim_issuer_identity_market_fills_or_money(
    tmp_path, integration, field, value,
):
    plan, days = _trial()
    changed = replace(days[0], **{field: value})
    with pytest.raises(Stage64TrialBlocked):
        _inputs_for(tmp_path, integration, plan=plan,
                    days=(changed,) + days[1:])


def test_unverified_operator_paper_source_still_cannot_promote(tmp_path, integration):
    plan, days = _trial()
    altered = tuple(replace(x, source_class="OPERATOR_DECLARED_PAPER") for x in days)
    r = _inputs_for(tmp_path, integration, plan=plan, days=altered)
    assert r.local_trial_criteria_met
    assert not r.genuine_net_pnl_verified
    _assert_no_release(r)


def test_out_of_order_and_duplicate_sessions_rejected(tmp_path, integration):
    plan, days = _trial()
    for altered in (
        days[:4] + (days[3],) + days[4:],
        days[:3] + (days[4], days[3]) + days[5:],
    ):
        with pytest.raises(Stage64TrialBlocked, match="distinct|ordered"):
            _inputs_for(tmp_path, integration, plan=plan, days=altered)


def test_market_holiday_conflicting_day_rejected(tmp_path, integration):
    plan, days = _trial()
    calendar = nse_equity_derivatives_baseline(
        holidays=frozenset({days[2].session_date}),
    )
    with pytest.raises(Stage64TrialBlocked, match="market days"):
        _inputs_for(tmp_path, integration, plan=plan, days=days, calendar=calendar)


def test_before_market_close_and_wrong_india_date_rejected(tmp_path, integration):
    plan, days = _trial()
    for observed in (
        datetime.fromisoformat("2026-09-01T14:00:00+05:30"),
        datetime.fromisoformat("2026-09-02T16:00:00+05:30"),
    ):
        altered = (replace(days[0], observed_at=observed),) + days[1:]
        with pytest.raises(Stage64TrialBlocked):
            _inputs_for(tmp_path, integration, plan=plan, days=altered)


def test_plan_registration_after_first_open_is_rejected(tmp_path, integration):
    plan, days = _trial()
    updated = replace(plan, registered_at=datetime.fromisoformat("2026-09-01T09:15:00+05:30"))
    with pytest.raises(Stage64TrialBlocked, match="before first"):
        _inputs_for(tmp_path, integration, plan=updated, days=days)


def test_plan_time_is_operator_claim_not_authentic_signed_evidence(tmp_path, integration):
    plan, days = _trial()
    r = _inputs_for(tmp_path, integration, plan=plan, days=days)
    assert _check(r, "registered_before_first_session")
    assert not r.prospectively_signed_trial_plan_verified
    _assert_no_release(r)


@pytest.mark.parametrize("field,value", [
    ("independently_timestamped_registration", True),
    ("authenticated_owner_approval", True),
    ("live_trading_enabled", True),
    ("minimum_sessions", True),
    ("minimum_sessions", 1),
    ("minimum_closed_trades", 0),
    ("minimum_execution_observations_per_trade", 0),
    ("maximum_drawdown_bps", 20000),
    ("minimum_gross_profit_factor", Decimal("NaN")),
    ("minimum_net_expectancy_cents", Decimal("-1")),
    ("starting_capital_cents", 0),
    ("trial_id", "../bad/name"),
])
def test_no_forged_plan_approval_invalid_threshold_or_account(field, value):
    plan, _ = _trial()
    with pytest.raises(Stage64TrialBlocked):
        replace(plan, **{field: value})


def test_as_of_before_trial_finished_is_rejected(tmp_path, integration):
    plan, days = _trial()
    with pytest.raises(Stage64TrialBlocked, match="future"):
        _inputs_for(tmp_path, integration, plan=plan, days=days,
                    as_of=datetime.fromisoformat("2026-09-10T18:00:00+05:30"))


def test_future_claimed_event_timestamp_rejected(tmp_path, integration):
    plan, days = _trial()
    changed = replace(days[-1], observed_at=datetime.fromisoformat("2026-09-29T18:00:00+05:30"))
    with pytest.raises(Stage64TrialBlocked):
        _inputs_for(tmp_path, integration, plan=plan,
                    days=days[:-1] + (changed,))


def test_mismatched_stage61_underlying_or_spoofed_integration_authority(
    tmp_path, integration,
):
    h, o, e = _inputs(tmp_path / "data", "NIFTY")
    evidence = inspect_stage61_fo_evidence(h, o, execution=e)
    plan, days = _trial()
    with pytest.raises(Stage64TrialBlocked, match="Cross-stage"):
        inspect_stage64_shadow_trial(
            plan, days, calendar=CAL, as_of=NOW, integration=integration,
            fo_evidence=replace(evidence, underlying="BANKNIFTY"),
        )
    with pytest.raises(Stage64TrialBlocked, match="Cross-stage"):
        inspect_stage64_shadow_trial(
            plan, days, calendar=CAL, as_of=NOW, fo_evidence=evidence,
            integration=replace(integration, merge_authorized=True),
        )


def test_missing_stage61_or_stage62_report_fails_closed(tmp_path, integration):
    h, o, e = _inputs(tmp_path / "data")
    evidence = inspect_stage61_fo_evidence(h, o, execution=e)
    plan, days = _trial()
    for research, check in ((object(), integration), (evidence, object())):
        with pytest.raises(Stage64TrialBlocked):
            inspect_stage64_shadow_trial(
                plan, days, calendar=CAL, as_of=NOW,
                fo_evidence=research, integration=check,
            )


def test_stage61_local_conflict_never_passes_local_check(tmp_path, integration):
    h, o, e = _inputs(tmp_path / "data")
    fo = inspect_stage61_fo_evidence(h, o, execution=e)
    plan, days = _trial()
    report = inspect_stage64_shadow_trial(
        plan, days, calendar=CAL, as_of=NOW,
        fo_evidence=replace(fo, local_inputs_structurally_consistent=False),
        integration=integration,
    )
    assert not _check(report, "stage61_local_futures_evidence_review")
    assert not report.local_trial_criteria_met
    _assert_no_release(report)


def test_stage62_static_conflict_never_passes_local_check(tmp_path, integration):
    h, o, e = _inputs(tmp_path / "data")
    fo = inspect_stage61_fo_evidence(h, o, execution=e)
    plan, days = _trial()
    report = inspect_stage64_shadow_trial(
        plan, days, calendar=CAL, as_of=NOW,
        fo_evidence=fo,
        integration=replace(integration, local_static_review_passed=False),
    )
    assert not _check(report, "stage62_local_integration_review")
    assert not report.local_trial_criteria_met
    _assert_no_release(report)


def test_stage64_smoke_composes_real_stage61_and_stage62_objects_only_synthetic():
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage64_shadow_trial_smoke.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=60,
    )
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["mode"] == "STAGE64_FABRICATED_TRIAL_GOVERNANCE_NO_GO_ONLY"
    assert result["data_source_is_real_market"] is False
    assert result["real_broker_fills"] is False
    assert result["signed_trials_registered"] is False
    assert result["live_orders_transmitted"] == 0
    assert result["production_ready"] is False
    for market in ("nifty", "banknifty"):
        item = result[market]
        assert item["starting_capital_cents"] == 3500000
        assert item["supplied_sessions"] == 20
        assert item["expected_trading_sessions"] == 20
        assert item["missing_trading_sessions"] == 0
        assert item["declared_closed_trades"] == 40
        assert item["local_trial_criteria_met"] is True
        assert item["claimed_net_pnl_cents"] == 34000
        assert item["authentic_real_shadow_performance"] is False
        assert item["strategy_promotion_authorized"] is False
        assert item["production_ready"] is False
        assert item["broker_orders_transmitted"] == 0
