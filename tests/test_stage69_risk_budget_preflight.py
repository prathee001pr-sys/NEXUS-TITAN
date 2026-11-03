"""Stage69 research-only double-gate preflight: no orders or budget holds."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus_titan.operations.brokerless_risk_veto import (
    Stage56RiskPolicy, Stage56SyntheticIntent, Stage56SyntheticQuote,
)
from nexus_titan.operations.stage69_risk_budget_preflight import (
    Stage69UntrustedRiskTelemetry, inspect_stage69_synthetic_risk_budget,
)
from nexus_titan.operations.synthetic_capital_authority import (
    Stage53BudgetPolicy, Stage53SyntheticCapitalAuthority,
)

CURRENT = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1]


def setup(tmp_path, *, policy=None, capital=5_000_000):
    auth = Stage53SyntheticCapitalAuthority(
        db_path=tmp_path / "research-budget.db",
        account_id="QA69",
        starting_cents=capital,
        policy=policy or Stage53BudgetPolicy(),
    )
    intent = Stage56SyntheticIntent(
        request_id="QA69-BUY-1", symbol="QAABC", quantity=3,
        limit_price_cents=10000, stop_price_cents=9500,
        fee_buffer_cents=100,
    )
    quote = Stage56SyntheticQuote(
        observed_at=CURRENT - timedelta(seconds=1),
        bid_cents=9995, ask_cents=10000,
        ask_depth_units=10, expected_slippage_bps=5,
        expected_edge_bps=40,
    )
    risk = Stage69UntrustedRiskTelemetry(
        daily_realized_loss_bps=0, current_drawdown_bps=0,
        consecutive_losses=0, kill_switch_active=False,
        risk_module_healthy=True,
    )
    return auth, intent, quote, risk


def inspect(args, *, now=CURRENT, policy=None):
    a, i, q, t = args
    return inspect_stage69_synthetic_risk_budget(
        a, i, q, t, now=now, risk_policy=policy or Stage56RiskPolicy(),
    )


def no_authority(report):
    assert not report.caller_risk_telemetry_authenticated
    assert not report.independently_authenticated_market_quote
    assert not report.global_legacy_entrypoints_fenced
    assert not report.single_atomic_authority_for_all_ledger_books
    assert not report.risk_rechecked_at_real_fill
    assert not report.authenticated_owner_approval
    assert not report.budget_hold_performed
    assert not report.order_submission_authorized
    assert not report.strategy_promotion_authorized
    assert not report.real_money_trading_enabled
    assert not report.production_ready
    assert report.broker_orders_transmitted == 0
    assert "NO_GO" in report.verdict


def test_good_synthetic_readonly_screen_does_not_hold_or_submit(tmp_path):
    args = setup(tmp_path)
    before = args[0].inspect()
    a = inspect(args)
    b = inspect(args)
    after = args[0].inspect()
    assert a == b
    assert a.local_budget_integrity_checked
    assert a.local_synthetic_risk_screen_passed
    assert a.local_budget_caps_checked
    assert a.local_research_preflight_passed
    assert a.requested_notional_cents == 30100
    assert a.blockers == ()
    assert a.observed_budget_revision == 0
    assert before == after
    no_authority(a)


@pytest.mark.parametrize("alter,expected", [
    (lambda t: replace(t, kill_switch_active=True), "KILL_SWITCH_ACTIVE"),
    (lambda t: replace(t, risk_module_healthy=False), "RISK_MODULE_UNAVAILABLE"),
    (lambda t: replace(t, daily_realized_loss_bps=300), "DAILY_LOSS_VETO"),
    (lambda t: replace(t, current_drawdown_bps=1000), "DRAWDOWN_VETO"),
    (lambda t: replace(t, consecutive_losses=3), "CONSECUTIVE_LOSS_VETO"),
    (lambda t: replace(t, daily_realized_loss_bps=True), "CALLER_RISK_TELEMETRY_MALFORMED"),
    (lambda t: replace(t, kill_switch_active="false"), "CALLER_RISK_TELEMETRY_MALFORMED"),
])
def test_spoofed_or_bad_untrusted_risk_telemetry_denied(tmp_path, alter, expected):
    a, i, q, t = setup(tmp_path)
    out = inspect((a, i, q, alter(t)))
    assert not out.local_research_preflight_passed
    assert expected in out.blockers
    no_authority(out)


@pytest.mark.parametrize("modify,expected", [
    (lambda q: replace(q, observed_at=CURRENT - timedelta(seconds=21)), "QUOTE_STALE_OR_FUTURE_DATED"),
    (lambda q: replace(q, source_reference="REAL_NSE"), "UNTRUSTED_OR_INVALID_SYNTHETIC_QUOTE"),
    (lambda q: replace(q, bid_cents=9800), "SPREAD_LIMIT_VETO"),
    (lambda q: replace(q, ask_depth_units=1), "INSUFFICIENT_SYNTHETIC_DEPTH"),
])
def test_bad_or_forged_quote_denied(tmp_path, modify, expected):
    a, i, q, t = setup(tmp_path)
    out = inspect((a, i, modify(q), t))
    assert not out.local_research_preflight_passed
    assert expected in out.blockers
    no_authority(out)


def test_futures_or_options_are_not_silently_admitted(tmp_path):
    a, i, q, t = setup(tmp_path)
    for kind in ("FUTURES", "OPTIONS", "CRYPTO"):
        verdict = inspect((a, replace(i, instrument_type=kind), q, t))
        assert not verdict.local_research_preflight_passed
        assert "INVALID_OR_UNSUPPORTED_SYNTHETIC_BUY" in verdict.blockers
        no_authority(verdict)


def test_local_ledger_reservations_are_read_from_actual_status(tmp_path):
    a, i, q, t = setup(tmp_path)
    a.hold_for_synthetic_research(request_id="EXISTING-1", amount_cents=1_000_000)
    a.hold_for_synthetic_research(request_id="EXISTING-2", amount_cents=1_000_000)
    out = inspect((a, i, q, t))
    assert out.observed_budget_revision == 2
    assert out.local_research_preflight_passed
    assert a.inspect().held_cents == 2_000_000
    no_authority(out)


def test_aggregate_budget_cap_blocks_even_if_risk_screen_passes(tmp_path):
    a, i, q, t = setup(tmp_path)
    a.hold_for_synthetic_research(request_id="EXISTING-1", amount_cents=1_000_000)
    a.hold_for_synthetic_research(request_id="EXISTING-2", amount_cents=1_000_000)
    a.hold_for_synthetic_research(request_id="EXISTING-3", amount_cents=500_000)
    out = inspect((a, i, q, t))
    assert not out.local_research_preflight_passed
    assert "AGGREGATE_RESERVE_CAP_VETO" in out.blockers
    assert "STAGE53_AGGREGATE_HOLD_CAP_VETO" in out.blockers
    assert a.inspect().revision == 3
    no_authority(out)


def test_tighter_budget_per_request_cap_is_a_separate_veto(tmp_path):
    args = setup(tmp_path, policy=Stage53BudgetPolicy(
        max_single_hold_bps=50, max_aggregate_held_bps=5000,
    ))
    out = inspect(args)
    assert out.local_synthetic_risk_screen_passed
    assert not out.local_budget_caps_checked
    assert not out.local_research_preflight_passed
    assert "STAGE53_SINGLE_HOLD_CAP_VETO" in out.blockers
    no_authority(out)


def test_corrupted_budget_head_rejected_before_risk_result(tmp_path):
    a, i, q, t = setup(tmp_path)
    a.hold_for_synthetic_research(request_id="EXISTING", amount_cents=1000)
    with sqlite3.connect(tmp_path / "research-budget.db") as db:
        db.execute("UPDATE budget_scope SET held_cents = held_cents + 1")
    out = inspect((a, i, q, t))
    assert not out.local_budget_integrity_checked
    assert not out.local_synthetic_risk_screen_passed
    assert not out.local_research_preflight_passed
    assert "LOCAL_SYNTHETIC_BUDGET_UNVERIFIABLE" in out.blockers
    assert out.observed_budget_revision is None
    no_authority(out)


def test_missing_auth_instance_and_risk_policy_throw_fail_closed(tmp_path):
    a, i, q, t = setup(tmp_path)
    with pytest.raises(TypeError):
        inspect_stage69_synthetic_risk_budget(object(), i, q, t)
    with pytest.raises(TypeError):
        inspect_stage69_synthetic_risk_budget(a, i, q, t, risk_policy="ALLOW")


def test_disposable_smoke_prints_explicit_no_live_flags(tmp_path):
    runner = ROOT / "scripts/run_stage69_synthetic_risk_budget_smoke.py"
    proc = subprocess.run(
        [sys.executable, str(runner)], cwd=ROOT,
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert report["mode"].endswith("NO_ORDERS")
    assert report["budget_held_cents_before_and_after"] == 0
    assert report["budget_revision_before_and_after"] == 0
    assert report["result"]["local_research_preflight_passed"] is True
    assert report["result"]["production_ready"] is False
    assert report["result"]["order_submission_authorized"] is False
