"""Stage42: exercise Stage40 gateway-only + Stage41 risk drift + Stage38 CAS."""
from __future__ import annotations
import json
import runpy
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"run_stage42_gateway_risk_e2e.py"


def audit():
    return runpy.run_path(str(SCRIPT))["run_stage42_audit"]()


def test_stage42_all_offline_paper_safety_cases_pass():
    result=audit()
    assert result["all_checks_passed"]
    assert result["checks_total"]>=18
    assert result["checks_passed"]==result["checks_total"]
    assert result["scope"]=="TEMPORARY_SYNTHETIC_PAPER_ONLY"


def test_stage42_rejects_gateway_bypass_and_stale_risk():
    checks=audit()["checks"]
    for key in (
        "direct_buy_api_denied","direct_sell_api_denied",
        "risk_limit_drift_rejects_approval",
        "margin_policy_drift_rejects_fill",
        "stale_process_cannot_overwrite_positions",
        "unapproved_fill_has_no_debit",
        "paper_permission_default_deny",
    ):
        assert checks[key] is True


def test_stage42_sell_and_emergency_remain_safe():
    checks=audit()["checks"]
    for key in (
        "naked_short_and_overclose_denied",
        "owned_sell_closes_and_cash_reconciles",
        "emergency_protective_sell_remains_available",
        "restart_preserves_emergency_lock",
        "kill_denies_new_gateway_buy",
        "research_hash_audit_intact",
    ):
        assert checks[key] is True


def test_stage42_never_returns_real_money_or_global_risk_approval():
    result=audit()
    assert result["live_orders_transmitted"]==0
    for field in (
        "real_market_data_approved","cross_ledger_atomicity_verified",
        "externally_authenticated_identity","automatic_strategy_promotion",
        "production_ready",
    ):
        assert result[field] is False


def test_stage42_json_cli_smoke():
    output=subprocess.run(
        [sys.executable,str(SCRIPT)],cwd=ROOT,
        text=True,capture_output=True,timeout=45,check=False,
    )
    assert output.returncode==0,output.stderr
    report=json.loads(output.stdout)
    assert report["all_checks_passed"]
    assert report["checks_passed"]==report["checks_total"]
    assert report["production_ready"] is False
