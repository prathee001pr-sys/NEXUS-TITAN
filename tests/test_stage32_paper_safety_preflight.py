"""Stage32 combined safety preflight, synthetic configuration and fail-closed tests."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nexus_titan.shadow.paper_safety_preflight import (
    PaperSafetyPreflight, inspect_paper_safety_preflight,
)
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import TradingMode, VirtualAccount

ROOT=Path(__file__).resolve().parents[1]


def _pair(tmp_path,*,risk=True,mode=TradingMode.MANUAL_APPROVAL,
          guarded=True,callback=True,virtual_id="PAIR",research_id="PAIR"):
    virtual=VirtualAccount(
        virtual_id,starting_capital=50000,
        require_pretrade_risk_check=risk,trading_mode=mode,
        approval_authorizer=(lambda actor,resource: False) if callback else None,
        state_dir=tmp_path/"virtual",
    )
    ledger=DurableResearchShadowLedger(
        tmp_path/"ledger.sqlite3",account_id=research_id,
        starting_capital=50000,guarded_paper_mode=guarded,
    )
    return virtual,ledger


def _check(v,l):
    return inspect_paper_safety_preflight(v,l)


def test_flat_manual_gated_accounts_pass_only_bounded_research_preflight(tmp_path):
    v,l=_pair(tmp_path)
    out=_check(v,l)
    assert isinstance(out,PaperSafetyPreflight)
    assert out.flat_research_gate_passed is True
    assert out.blockers==()
    assert out.virtual_reconciled
    assert out.guarded_ledger_verified
    assert out.account_id_match
    assert not out.external_identity_verified
    assert not out.verified_market_data
    assert not out.global_order_router_verified
    assert not out.production_ready
    assert not out.approved_for_strategy_promotion
    assert out.live_orders_transmitted==0


def test_preflight_is_read_only_and_deterministic(tmp_path):
    v,l=_pair(tmp_path)
    before=l.status()
    a=_check(v,l)
    b=_check(v,l)
    assert a==b
    assert l.status()==before
    assert v.orders=={} and v.positions=={}


@pytest.mark.parametrize("option, expected", [
    ({"risk":False},"pretrade Risk"),
    ({"mode":TradingMode.AUTO_PAPER},"MANUAL_APPROVAL"),
    ({"guarded":False},"legacy"),
    ({"callback":False},"approval callback"),
    ({"research_id":"OTHER"},"account IDs differ"),
])
def test_preflight_rejects_independent_policy_failures(tmp_path,option,expected):
    v,l=_pair(tmp_path,**option)
    out=_check(v,l)
    assert not out.flat_research_gate_passed
    assert any(expected in reason for reason in out.blockers)
    assert not out.production_ready


def test_open_manual_buy_blocks_flat_configuration_preflight(tmp_path):
    v,l=_pair(tmp_path)
    order=v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    assert order.state.value=="PENDING_APPROVAL"
    out=_check(v,l)
    assert any("unfinished orders" in issue for issue in out.blockers)


def test_existing_virtual_inventory_blocks_flat_admission(tmp_path):
    v,l=_pair(tmp_path)
    v.approval_authorizer=lambda actor,oid: True
    buy=v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    v.approve_order(buy.order_id,"OWNER")
    v.execute_fill(buy.order_id,100)
    out=_check(v,l)
    assert not out.flat_research_gate_passed
    assert any("not flat" in issue for issue in out.blockers)


def test_kill_switch_forces_unready_even_if_account_is_flat(tmp_path):
    v,l=_pair(tmp_path)
    v.activate_emergency_kill_switch()
    out=_check(v,l)
    assert not out.flat_research_gate_passed
    assert any("kill switch" in issue for issue in out.blockers)


def test_invalid_ledger_hash_chain_is_flagged_not_accepted(tmp_path):
    v,l=_pair(tmp_path)
    with sqlite3.connect(l.db_path) as conn:
        conn.execute("DELETE FROM account_safety WHERE account_id=?",(l.account_id,))
    out=_check(v,l)
    assert out.flat_research_gate_passed is False
    assert out.guarded_ledger_verified is False
    assert any("integrity" in issue for issue in out.blockers)


def test_legacy_account_with_clean_audit_still_blocks_gated_research(tmp_path):
    v,l=_pair(tmp_path,guarded=False)
    assert l.verify_integrity()
    out=_check(v,l)
    assert out.guarded_ledger_verified is True
    assert not out.flat_research_gate_passed


def test_invalid_types_do_not_create_false_positive(tmp_path):
    v,l=_pair(tmp_path)
    with pytest.raises(TypeError,match="VirtualAccount"):
        _check(None,l)
    with pytest.raises(TypeError,match="DurableResearchShadowLedger"):
        _check(v,None)


def test_report_is_immutable_and_never_promotes(tmp_path):
    v,l=_pair(tmp_path)
    out=_check(v,l)
    with pytest.raises(FrozenInstanceError):
        out.production_ready=True
    assert out.live_orders_transmitted==0


def test_offline_cli_smoke_runs_without_broker_or_market_data():
    process=subprocess.run(
        [sys.executable,str(ROOT/"scripts"/"run_stage32_paper_safety_smoke.py")],
        cwd=ROOT,capture_output=True,text=True,timeout=45,check=False,
    )
    assert process.returncode==0,process.stderr
    report=json.loads(process.stdout)
    assert report["flat_research_gate_passed"] is True
    assert report["global_order_router_verified"] is False
    assert report["external_identity_verified"] is False
    assert report["production_ready"] is False
    assert report["live_orders_transmitted"]==0
