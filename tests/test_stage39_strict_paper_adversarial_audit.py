"""Stage39 offline strict paper safety smoke and invariant review tests."""
from __future__ import annotations
import json
import runpy
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def _run():
    return runpy.run_path(
        str(ROOT/"scripts"/"run_stage39_strict_paper_adversarial_audit.py")
    )["run_strict_synthetic_audit"]()


def test_stage39_all_adversarial_paper_checks_pass_with_no_real_authority():
    r=_run()
    assert r["all_checks_passed"] is True
    assert r["checks_total"]>=18
    assert r["checks_passed"]==r["checks_total"]
    assert r["live_broker_orders_transmitted"]==0
    assert not r["production_ready"]
    assert not r["automatic_strategy_promotion"]


def test_stage39_denies_unapproved_or_stale_capital_mutation():
    c=_run()["checks"]
    assert c["unapproved_fill_blocked_without_debit"]
    assert c["unapproved_sell_fill_blocked"]
    assert c["old_process_snapshot_cannot_overwrite_newer_buy"]
    assert c["stale_emergency_handle_must_recover"]


def test_stage39_reconciles_restart_kill_and_no_naked_short():
    c=_run()["checks"]
    for label in (
        "restart_keeps_strict_policy_and_reconciled_cash",
        "closed_trade_reconciles_without_inventory",
        "naked_or_overquantity_sell_denied",
        "duplicate_pending_sell_denied",
        "kill_lock_survives_restart_and_reconciles",
        "kill_blocks_new_gateway_buys",
        "strict_mode_never_escalates_to_auto",
    ):
        assert c[label]


def test_stage39_never_claims_real_exchange_or_cross_ledger_security():
    r=_run()
    for key in (
        "global_order_router_verified","cross_ledger_atomicity_verified",
        "externally_authenticated_approvals","real_fo_historical_data_verified",
        "automatic_strategy_promotion","production_ready",
    ):
        assert r[key] is False


def test_stage39_cli_returns_machine_readable_bounded_synthetic_evidence():
    p=subprocess.run(
        [sys.executable,str(ROOT/"scripts"/"run_stage39_strict_paper_adversarial_audit.py")],
        cwd=ROOT,capture_output=True,text=True,check=False,timeout=45,
    )
    assert p.returncode==0,p.stderr
    result=json.loads(p.stdout)
    assert result["all_checks_passed"]
    assert result["checks_passed"]==result["checks_total"]
    assert result["live_broker_orders_transmitted"]==0
    assert result["environment"]=="ISOLATED_SYNTHETIC_RESEARCH_ONLY"
