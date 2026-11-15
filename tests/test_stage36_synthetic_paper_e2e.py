"""Stage36 end-to-end synthetic-only audit and safety boundary assertions."""
from __future__ import annotations
import json
import runpy
import subprocess
import sys
from pathlib import Path
from dataclasses import replace

import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_fully_offline_multistage_paper_buy_sell_recovery_audit():
    mod=runpy.run_path(str(ROOT/"scripts"/"run_stage36_synthetic_paper_e2e.py"))
    report=mod["run_synthetic_audit"]()
    assert report["all_checks_passed"] is True
    assert report["checks_passed"]==report["checks_total"]==16
    assert report["mode"]=="SYNTHETIC_OFFLINE_RESEARCH_ONLY"
    assert report["genuine_fo_market_data_verified"] is False
    assert report["real_broker_trading_enabled"] is False
    assert report["global_order_router_proven"] is False
    assert report["production_ready"] is False


def test_cli_smoke_is_deterministically_bounded_and_never_reports_live():
    result=subprocess.run(
        [sys.executable,str(ROOT/"scripts"/"run_stage36_synthetic_paper_e2e.py")],
        capture_output=True,text=True,check=False,timeout=45,cwd=ROOT,
    )
    assert result.returncode==0,result.stderr
    report=json.loads(result.stdout)
    assert report["checks_passed"]==16
    assert report["real_broker_trading_enabled"] is False
    assert report["strategy_promotion_approved"] is False


def test_individual_safety_regressions_are_present_in_aggregated_audit():
    report=runpy.run_path(
        str(ROOT/"scripts"/"run_stage36_synthetic_paper_e2e.py")
    )["run_synthetic_audit"]()
    for name in (
        "initial_flat_preflight","default_paper_permission_denied",
        "intent_evidence_expires_after_approval","naked_sell_denied",
        "durable_restart_reconciled","research_guard_cannot_downgrade",
        "kill_switch_survives_restart","gateway_buy_denied_after_kill",
        "post_emergency_reconciled",
    ):
        assert report["checks"][name] is True


def test_no_live_or_production_authority_misrepresented():
    report=runpy.run_path(
        str(ROOT/"scripts"/"run_stage36_synthetic_paper_e2e.py")
    )["run_synthetic_audit"]()
    assert not report["genuine_fo_market_data_verified"]
    assert not report["global_order_router_proven"]
    assert not report["production_ready"]
    assert not report["strategy_promotion_approved"]
