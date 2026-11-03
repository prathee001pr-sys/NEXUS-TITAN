"""Stage56 brokerless synthetic risk/veto and legacy-bypass evidence tests."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus_titan.operations.brokerless_risk_veto import (
    Stage56RiskBlocked,
    Stage56RiskPolicy,
    Stage56SyntheticIntent,
    Stage56SyntheticQuote,
    Stage56SyntheticRiskState,
    inspect_stage56_synthetic_risk,
)
from nexus_titan.operations.risk_boundary_inventory import (
    inspect_stage56_bypass_paths,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_stage56_brokerless_risk_gate.py"
CURRENT = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def _intent(**overrides):
    return replace(Stage56SyntheticIntent(
        request_id="QA56-ABC-1", symbol="QAABC", quantity=3,
        limit_price_cents=10000, stop_price_cents=9500,
        fee_buffer_cents=100, instrument_type="EQUITY_DELIVERY",
        side="BUY",
    ), **overrides)


def _quote(**overrides):
    return replace(Stage56SyntheticQuote(
        observed_at=CURRENT - timedelta(seconds=1),
        bid_cents=9995, ask_cents=10000, ask_depth_units=15,
        expected_slippage_bps=5, expected_edge_bps=40,
        source_reference="SYNTHETIC/LOCAL_QA",
    ), **overrides)


def _account(**overrides):
    return replace(Stage56SyntheticRiskState(
        account_id="QA56", initial_cents=5_000_000,
        available_cents=5_000_000, already_reserved_cents=0,
        daily_realized_loss_bps=0, current_drawdown_bps=0,
        consecutive_losses=0, kill_switch_active=False,
        risk_module_healthy=True,
    ), **overrides)


def _check(intent=None, quote=None, account=None, policy=None, now=CURRENT):
    return inspect_stage56_synthetic_risk(
        _intent() if intent is None else intent,
        _quote() if quote is None else quote,
        _account() if account is None else account,
        policy=policy or Stage56RiskPolicy(), now=now,
    )


def _release_permanently_blocked(verdict):
    assert verdict.schema_version == 1
    assert verdict.order_submission_authorized is False
    assert verdict.synthetic_fill_authorized is False
    assert verdict.independent_human_identity_verified is False
    assert verdict.local_caller_state_authenticated is False
    assert verdict.external_quote_authenticated is False
    assert verdict.global_legacy_entrypoints_fenced is False
    assert verdict.trusted_risk_service_boundary_enforced is False
    assert verdict.live_trading_enabled is False
    assert verdict.production_ready is False
    assert verdict.broker_orders_transmitted == 0


def test_valid_local_synthetic_qa_screen_is_never_trade_authorization():
    result = _check()
    assert result.local_synthetic_screen_passed
    assert result.blockers == ()
    assert result.account_id == "QA56"
    assert result.request_id == "QA56-ABC-1"
    assert result.synthetic_notional_cents == 30100
    assert result.synthetic_stop_risk_cents == 1600
    assert result.observed_spread_bps is not None
    assert 0 < result.observed_spread_bps < 40
    assert len(result.policy_sha256) == 64
    assert len(result.input_sha256) == 64
    _release_permanently_blocked(result)


@pytest.mark.parametrize("risk", [
    {"kill_switch_active": True},
    {"risk_module_healthy": False},
    {"daily_realized_loss_bps": 300},
    {"current_drawdown_bps": 1000},
    {"consecutive_losses": 3},
])
def test_kill_switch_and_risk_drawdown_loss_veto(risk):
    result = _check(account=_account(**risk))
    assert not result.local_synthetic_screen_passed
    assert result.blockers
    _release_permanently_blocked(result)


@pytest.mark.parametrize("risk", [
    {"initial_cents": 0},
    {"available_cents": True},
    {"already_reserved_cents": -1},
    {"available_cents": 5_000_000, "already_reserved_cents": 1},
    {"account_id": "../broken"},
    {"kill_switch_active": "false"},
    {"risk_module_healthy": 1},
    {"daily_realized_loss_bps": -1},
    {"current_drawdown_bps": 10001},
    {"consecutive_losses": 10_001},
])
def test_corrupt_or_spoofed_local_account_evidence_fails_closed(risk):
    result = _check(account=_account(**risk))
    assert not result.local_synthetic_screen_passed
    assert "UNTRUSTED_OR_INVALID_ACCOUNT_RISK_STATE" in result.blockers
    _release_permanently_blocked(result)


@pytest.mark.parametrize("quote", [
    {"ask_cents": 0},
    {"bid_cents": True},
    {"bid_cents": 10001},
    {"ask_depth_units": 0},
    {"expected_edge_bps": -1},
    {"expected_slippage_bps": "5"},
    {"source_reference": "REAL_NSE"},
    {"observed_at": datetime(2026, 11, 3, 8, 0)},
])
def test_corrupt_quote_evidence_fails_closed(quote):
    result = _check(quote=_quote(**quote))
    assert not result.local_synthetic_screen_passed
    assert "UNTRUSTED_OR_INVALID_SYNTHETIC_QUOTE" in result.blockers
    _release_permanently_blocked(result)


@pytest.mark.parametrize("quote,expected", [
    ({"bid_cents": 9800}, "SPREAD_LIMIT_VETO"),
    ({"expected_slippage_bps": 16}, "SLIPPAGE_LIMIT_VETO"),
    ({"expected_edge_bps": 24}, "EXPECTED_EDGE_TOO_LOW"),
    ({"expected_edge_bps": 1, "expected_slippage_bps": 5}, "EXPECTED_EDGE_BELOW_SLIPPAGE"),
    ({"ask_depth_units": 2}, "INSUFFICIENT_SYNTHETIC_DEPTH"),
    ({"ask_cents": 10001, "bid_cents": 10000}, "ASK_EXCEEDS_LIMIT_PRICE"),
])
def test_quote_spread_depth_edge_slippage_and_price_veto(quote, expected):
    result = _check(quote=_quote(**quote))
    assert not result.local_synthetic_screen_passed
    assert expected in result.blockers
    _release_permanently_blocked(result)


@pytest.mark.parametrize("quote,expected", [
    ({"observed_at": CURRENT - timedelta(seconds=21)}, "QUOTE_STALE_OR_FUTURE_DATED"),
    ({"observed_at": CURRENT + timedelta(microseconds=10)}, "QUOTE_STALE_OR_FUTURE_DATED"),
])
def test_quote_staleness_or_future_quote_blocked(quote, expected):
    result = _check(quote=_quote(**quote))
    assert not result.local_synthetic_screen_passed
    assert expected in result.blockers


@pytest.mark.parametrize("intent", [
    {"request_id": ""},
    {"request_id": "../bad"},
    {"symbol": "BANKNIFTY OPT"},
    {"quantity": 0},
    {"quantity": True},
    {"quantity": 201},
    {"limit_price_cents": 0},
    {"stop_price_cents": 10000},
    {"fee_buffer_cents": -1},
    {"instrument_type": "FUTURES"},
    {"instrument_type": "NIFTY_OPTIONS"},
    {"side": "SELL"},
])
def test_unsupported_intents_and_futures_options_are_vetoed(intent):
    result = _check(intent=_intent(**intent))
    assert not result.local_synthetic_screen_passed
    assert "INVALID_OR_UNSUPPORTED_SYNTHETIC_BUY" in result.blockers
    _release_permanently_blocked(result)


def test_stop_must_be_below_synthetic_bid():
    result = _check(intent=_intent(stop_price_cents=9995))
    assert not result.local_synthetic_screen_passed
    assert "STOP_NOT_BELOW_BID" in result.blockers


@pytest.mark.parametrize("field,value,expected", [
    ("available_cents", 100, "INSUFFICIENT_AVAILABLE_CAPITAL"),
    ("already_reserved_cents", 2_490_000, "AGGREGATE_RESERVE_CAP_VETO"),
])
def test_available_cash_and_aggregate_reserve_veto(field, value, expected):
    overrides = {field: value}
    if field == "already_reserved_cents":
        overrides["available_cents"] = 2_510_000
    result = _check(account=_account(**overrides))
    assert not result.local_synthetic_screen_passed
    assert expected in result.blockers


def test_notional_risk_cap_and_stop_distance_are_independent():
    high_notional = _check(intent=_intent(quantity=200, limit_price_cents=10000))
    assert "SINGLE_NOTIONAL_CAP_VETO" in high_notional.blockers
    assert not high_notional.local_synthetic_screen_passed
    wide_stop = _check(intent=_intent(quantity=100, stop_price_cents=9000))
    assert "STOP_RISK_CAP_VETO" in wide_stop.blockers
    assert not wide_stop.local_synthetic_screen_passed


@pytest.mark.parametrize("bad", [0, -1, True, None, "25", 999999])
def test_policy_invalid_values_fail_closed_before_any_order(bad):
    with pytest.raises(Stage56RiskBlocked):
        Stage56RiskPolicy(max_quote_age_seconds=bad)


def test_policy_fingerprint_is_stable_and_changes_with_limits():
    a = _check()
    b = _check()
    assert a == b
    stricter = _check(policy=Stage56RiskPolicy(max_quote_age_seconds=10))
    assert a.policy_sha256 != stricter.policy_sha256
    assert a.input_sha256 == stricter.input_sha256
    assert not stricter.order_submission_authorized


def test_missing_or_invalid_clock_refuses_to_claim_clean_verdict():
    naive = datetime(2026, 11, 3, 8, 0)
    result = _check(now=naive)
    assert "REFERENCE_CLOCK_UNVERIFIED" in result.blockers
    assert not result.local_synthetic_screen_passed


def test_local_input_digest_not_an_authenticated_signature():
    changed = _check(quote=_quote(expected_edge_bps=41))
    original = _check()
    assert original.input_sha256 != changed.input_sha256
    assert not changed.external_quote_authenticated
    assert not changed.independent_human_identity_verified
    assert not changed.order_submission_authorized


def _cli_request():
    return {
        "schema_version": 1,
        "intent": asdict(_intent()),
        "quote": {**asdict(_quote(observed_at=datetime.now(timezone.utc))),
                  "observed_at": datetime.now(timezone.utc).isoformat()},
        "account": asdict(_account()),
    }


def _run(request=None, *, payload=None):
    if payload is None:
        payload = json.dumps(request).encode("utf-8")
    run = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload, cwd=ROOT, capture_output=True, timeout=15,
    )
    return run, json.loads(run.stdout)


def test_json_subprocess_local_success_never_authorizes_order():
    request = _cli_request()
    run, result = _run(request)
    assert run.returncode == 0, run.stderr.decode()
    assert result["risk_gate_kind"] == "BROKERLESS_LOCAL_SYNTHETIC_QA_ONLY"
    assert result["local_synthetic_screen_passed"]
    assert not result["order_submission_authorized"]
    assert not result["global_legacy_entrypoints_fenced"]
    assert not result["trusted_risk_service_boundary_enforced"]
    assert not result["live_trading_enabled"]
    assert not result["production_ready"]
    assert result["broker_orders_transmitted"] == 0


def test_json_subprocess_denied_kill_switch_without_exception():
    request = _cli_request()
    request["account"]["kill_switch_active"] = True
    run, result = _run(request)
    assert run.returncode == 0
    assert not result["local_synthetic_screen_passed"]
    assert "KILL_SWITCH_ACTIVE" in result["blockers"]
    assert not result["order_submission_authorized"]


@pytest.mark.parametrize("alter", [
    lambda x: x.update(action="MAKE_REAL_ORDER"),
    lambda x: x.update(schema_version=2),
    lambda x: x["intent"].update(extra="bar"),
    lambda x: x.pop("account"),
    lambda x: x["quote"].update(observed_at="not-time"),
    lambda x: x["quote"].update(source_reference="BROKER_PRICE"),
])
def test_json_cli_strict_schema_and_bad_evidence(alter):
    request = _cli_request()
    alter(request)
    run, response = _run(request)
    assert response["order_submission_authorized"] is False
    assert response["broker_orders_transmitted"] == 0
    assert response["production_ready"] is False
    assert response["local_synthetic_screen_passed"] is False
    assert run.returncode in (0, 2)


@pytest.mark.parametrize("raw", [
    b"", b"not-json", b"{}", b"[]" ,
    b'{"schema_version":NaN}', b"x" * 16385,
    b'{"schema_version":1,"schema_version":1}',
    b'{"schema_version":Infinity}',
])
def test_cli_malformed_or_oversized_payload_fails_closed(raw):
    run, data = _run(payload=raw)
    assert run.returncode == 2
    assert not data["local_synthetic_screen_passed"]
    assert not data["order_submission_authorized"]
    assert not data["live_trading_enabled"]


def test_invalid_nan_caller_balance_returns_veto_without_hashing_or_exception():
    result = _check(account=_account(available_cents=float("nan")))
    assert not result.local_synthetic_screen_passed
    assert "UNTRUSTED_OR_INVALID_ACCOUNT_RISK_STATE" in result.blockers
    assert result.input_sha256 is None
    _release_permanently_blocked(result)


def test_exact_quote_age_boundary_and_one_microsecond_overage():
    allowed = _check(quote=_quote(observed_at=CURRENT - timedelta(seconds=20)))
    denied = _check(quote=_quote(
        observed_at=CURRENT - timedelta(seconds=20, microseconds=1),
    ))
    assert allowed.local_synthetic_screen_passed
    assert not denied.local_synthetic_screen_passed
    assert "QUOTE_STALE_OR_FUTURE_DATED" in denied.blockers


def test_audit_reports_existing_public_legacy_bypasses_without_claiming_security():
    report = inspect_stage56_bypass_paths(ROOT)
    assert report.local_static_scan_complete
    assert not report.unverifiable_sources
    assert report.inspected_files == 6
    assert "VirtualAccount.submit_order" in report.known_callable_surfaces
    assert "VirtualAccount.execute_fill" in report.known_callable_surfaces
    assert "PaperOnlyDeployment.request_buy" in report.known_callable_surfaces
    assert "Stage55IsolatedSyntheticExecutionBook.record_simulated_fill" in report.known_callable_surfaces
    assert len(report.reviewed_sources_sha256) == 64
    assert not report.legacy_order_paths_globally_disabled
    assert not report.independent_process_credential_isolation_verified
    assert not report.all_execution_paths_proven_fenced
    assert not report.production_ready
    assert not report.live_trading_enabled


def test_audit_missing_code_is_unknown_not_safely_fenced(tmp_path):
    report = inspect_stage56_bypass_paths(tmp_path)
    assert not report.local_static_scan_complete
    assert report.unverifiable_sources
    assert report.reviewed_sources_sha256 is None
    assert not report.legacy_order_paths_globally_disabled


def test_no_broker_synthetic_cli_demo():
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_stage56_risk_veto_smoke.py")],
        cwd=ROOT, text=True, capture_output=True, timeout=20,
    )
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["mode"] == "STAGE56_BROKERLESS_LOCAL_RISK_QA"
    assert data["accepted_local_qa_screen"]
    assert data["kill_switch_vetoed"]
    assert data["legacy_entrypoints_still_exposed"]
    assert data["live_orders_transmitted"] == 0
    assert not data["global_risk_enforced"]
    assert not data["production_ready"]
