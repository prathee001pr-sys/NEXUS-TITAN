"""Stage43 paper-only startup: durable strict/gateway profile integration tests.

All test accounts and orders use temporary synthetic state, no external data,
broker API, or asserted real identity verification.
"""
from __future__ import annotations

from pathlib import Path
from datetime import date, datetime
import sqlite3
import json
import subprocess
import sys
import pytest

from nexus_titan.operations.paper_deployment import (
    PaperDeploymentBlocked, PaperDeploymentConfig, open_paper_only_deployment,
)
from nexus_titan.shadow.paper_intent_gateway import PaperIntentDenied
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, GuardedBuyAdmission, ResearchLedgerError,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
from nexus_titan.virtual.order_manager import VirtualAccount, TradingMode, OrderState


def _cfg(tmp_path, *, enabled=False, account_id="S43", capital=50000, **kw):
    values=dict(
        account_id=account_id, starting_capital=capital,
        virtual_state_dir=tmp_path/"virtual",
        research_db_path=tmp_path/"research.sqlite3",
        paper_orders_enabled=enabled, deployment_profile="RESEARCH_PAPER_ONLY",
    )
    values.update(kw)
    return PaperDeploymentConfig(**values)


def _open(cfg, callback=True):
    return open_paper_only_deployment(
        cfg,
        approval_authorizer=(lambda actor, order_id: actor=="OWNER") if callback else None,
    )


def test_bootstrap_is_read_only_by_default_but_durably_strict(tmp_path):
    cfg=_cfg(tmp_path)
    d=_open(cfg)
    status=d.status()
    assert status.read_only and not status.paper_intents_enabled
    assert status.strict_paper_mode and status.gateway_only_mode
    assert status.virtual_reconciled and status.research_ledger_verified
    assert d.virtual_account.durable_store.strict_mode("S43")
    assert d.virtual_account.durable_store.gateway_only("S43")
    assert d.research_ledger.guarded_paper_mode
    assert not d.virtual_account.orders
    with pytest.raises(PaperDeploymentBlocked,match="disabled by session config"):
        d.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)


def test_explicit_paper_permission_manual_buy_owned_sell_no_broker(tmp_path):
    d=_open(_cfg(tmp_path,enabled=True))
    assert d.status().paper_intents_enabled
    starting=d.virtual_account.cash_balance
    buy=d.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)
    assert buy.status=="PENDING_APPROVAL"
    assert d.virtual_account.cash_balance==starting
    with pytest.raises(PermissionError,match="denies direct submit_order"):
        d.virtual_account.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    d.virtual_account.approve_order(buy.order_id,"OWNER")
    d.virtual_account.execute_fill(buy.order_id,100)
    assert d.virtual_account.positions["ABC"].quantity==1
    close=d.request_sell_to_close(symbol="ABC",quantity=1)
    assert close.status=="PENDING_APPROVAL"
    d.virtual_account.approve_order(close.order_id,"OWNER")
    d.virtual_account.execute_fill(close.order_id,103)
    assert not d.virtual_account.positions
    assert d.virtual_account.reconcile().is_reconciled
    status=d.status()
    assert status.paper_intents_enabled and not status.production_ready
    assert status.live_orders_transmitted==0
    assert not status.externally_authenticated_identity
    assert not status.cross_ledger_atomicity_verified
    assert not status.global_legacy_apis_disabled


def test_reopen_requires_explicit_opt_in_per_session(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    first=_open(cfg)
    buy=first.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)
    reopened=_open(_cfg(tmp_path,enabled=False))
    assert reopened.virtual_account.orders[buy.order_id].state is OrderState.PENDING_APPROVAL
    assert reopened.status().read_only
    with pytest.raises(PaperDeploymentBlocked,match="disabled by session config"):
        reopened.request_sell_to_close(symbol="ABC",quantity=1)
    assert not reopened.status().production_ready


def test_restart_with_pending_manual_order_does_not_auto_fill(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    first=_open(cfg)
    order=first.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)
    next_session=_open(cfg)
    assert next_session.virtual_account.orders[order.order_id].filled_qty==0
    assert next_session.status().paper_intents_enabled
    with pytest.raises(PermissionError,match="intact authenticated"):
        next_session.virtual_account.execute_fill(order.order_id,100)
    assert next_session.virtual_account.cash_balance==50000


def test_readonly_bootstrap_does_not_claim_external_auth_or_production(tmp_path):
    d=_open(_cfg(tmp_path,enabled=False))
    s=d.status()
    assert s.research_profile=="RESEARCH_PAPER_ONLY"
    assert s.live_trading_enabled is False
    assert s.live_orders_transmitted==0
    assert s.approved_for_strategy_promotion is False
    assert s.externally_authenticated_identity is False
    assert s.cross_ledger_atomicity_verified is False
    assert s.global_legacy_apis_disabled is False
    assert s.production_ready is False
    assert not hasattr(d,"submit_live_order")


@pytest.mark.parametrize("changes",[
    {"paper_orders_enabled":"yes"},
    {"paper_orders_enabled":1},
    {"deployment_profile":"LIVE"},
    {"deployment_profile":"AUTO_PAPER"},
    {"starting_capital":0},
    {"starting_capital":float("nan")},
    {"starting_capital":True},
    {"account_id":"../escape"},
    {"account_id":""},
    {"virtual_state_dir":"not-a-Path"},
])
def test_invalid_config_rejected_before_side_effects(tmp_path,changes):
    cfg=_cfg(tmp_path,**changes)
    with pytest.raises(PaperDeploymentBlocked):
        _open(cfg)
    assert not (tmp_path/"virtual").exists()


def test_missing_manual_identity_callback_is_blocked_before_file_creation(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    with pytest.raises(PaperDeploymentBlocked,match="approval callback"):
        _open(cfg,callback=False)
    assert not cfg.research_db_path.exists()


def test_existing_legacy_account_never_silently_migrated(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    v=VirtualAccount(
        "S43",starting_capital=50000,state_dir=cfg.virtual_state_dir,
        trading_mode=TradingMode.MANUAL_APPROVAL,require_pretrade_risk_check=True,
        approval_authorizer=lambda actor,oid: True,
    )
    v.submit_order("ABC","BUY",1,entry_price=100,stop_price=95)
    DurableResearchShadowLedger(cfg.research_db_path,account_id="S43",
                                 starting_capital=50000,guarded_paper_mode=True)
    with pytest.raises(PaperDeploymentBlocked,match="do not silently migrate"):
        _open(cfg)
    assert not v.strict_paper_mode and not v.gateway_only_mode


def test_existing_strict_account_without_gateway_only_rejected(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    v=VirtualAccount(
        "S43",starting_capital=50000,state_dir=cfg.virtual_state_dir,
        trading_mode=TradingMode.MANUAL_APPROVAL,require_pretrade_risk_check=True,
        approval_authorizer=lambda actor,oid: True,strict_paper_mode=True,
    )
    DurableResearchShadowLedger(cfg.research_db_path,account_id="S43",
                                 starting_capital=50000,guarded_paper_mode=True)
    with pytest.raises(PaperDeploymentBlocked,match="strict\+gateway-only"):
        _open(cfg)
    assert v.durable_store.strict_mode("S43")
    assert not v.durable_store.gateway_only("S43")


def test_partial_storage_pair_rejected_without_reset(tmp_path):
    cfg=_cfg(tmp_path)
    VirtualAccount(
        "S43",starting_capital=50000,state_dir=cfg.virtual_state_dir,
        trading_mode=TradingMode.MANUAL_APPROVAL,require_pretrade_risk_check=True,
        approval_authorizer=lambda actor,oid: True,strict_paper_mode=True,
    )
    with pytest.raises(PaperDeploymentBlocked,match="Incomplete"):
        _open(cfg)
    assert not cfg.research_db_path.exists()


def test_reopen_capital_mismatch_fails_closed(tmp_path):
    d=_open(_cfg(tmp_path,capital=50000))
    with pytest.raises(PaperDeploymentBlocked,match="initial capital mismatch"):
        _open(_cfg(tmp_path,capital=60000))
    assert d.virtual_account.initial_capital==50000


def test_same_sqlite_paths_rejected(tmp_path):
    cfg=_cfg(tmp_path,research_db_path=tmp_path/"virtual"/"S43_durable.db")
    with pytest.raises(PaperDeploymentBlocked,match="Distinct"):
        _open(cfg)
    assert not (tmp_path/"virtual").exists()


def test_restart_kill_mode_is_readonly_and_no_new_buy(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    d=_open(cfg)
    buy=d.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)
    d.virtual_account.approve_order(buy.order_id,"OWNER")
    d.virtual_account.execute_fill(buy.order_id,100)
    d.virtual_account.emergency_square_off({"ABC":99})
    restarted=_open(cfg)
    assert restarted.virtual_account.kill_switched
    assert restarted.status().read_only
    with pytest.raises(PaperDeploymentBlocked,match="Emergency kill switch"):
        restarted.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)


def test_stale_process_handle_becomes_readonly(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    first=_open(cfg)
    old=_open(cfg)
    first.virtual_account.adjust_capital(100,"TOP_UP")
    status=old.status()
    assert status.read_only and not status.paper_intents_enabled
    with pytest.raises(PaperDeploymentBlocked,match="stale"):
        old.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)
    fresh=_open(cfg)
    assert fresh.virtual_account.current_capital==50100
    assert fresh.status().paper_intents_enabled


def test_research_ledger_integrity_failure_rejects_startup(tmp_path):
    cfg=_cfg(tmp_path,enabled=True)
    d=_open(cfg)
    with sqlite3.connect(cfg.research_db_path) as con:
        con.execute("DELETE FROM account_safety WHERE account_id='S43'")
    with pytest.raises(PaperDeploymentBlocked,match="research ledger startup/integrity"):
        _open(cfg)
    with pytest.raises(ResearchLedgerError,match="state does not match audit"):
        d.research_ledger.verify_integrity()


def test_research_outstanding_reservation_blocks_new_intents(tmp_path):
    # A valid, synthetic guarded options reservation blocks new deployment
    # requests even when VirtualAccount's balance itself looks reconciled.
    d=_open(_cfg(tmp_path,enabled=True))
    contract=PointInTimeContractSpec(
        symbol="NIFTYOPT",underlying="NIFTY",exchange="NSE",segment="OPTIONS",
        lot_size=25,tick_size=0.05,freeze_quantity=1000,max_lots_per_trade=10,
        strike_step=50.0,expiry_date=date(2026,11,5),
        effective_from=date(2026,11,1),effective_to=date(2026,11,5),
        source_reference="synthetic/not-licensed-real-data",source_verified=True,
    )
    d.research_ledger.reserve_buy_guarded(
        order_id="S43-PENDING",contract=contract,strike=100.0,
        option_type="CE",lots=2,
        as_of=datetime.fromisoformat("2026-11-03T09:16:00+05:30"),
        max_unit_premium=6.0,fee_buffer=25.0,
        admission=GuardedBuyAdmission(
            paper_trading_enabled=True,risk_config=PortfolioRiskConfig(),
            stop_price=5.0,bid=5.0,ask=5.5,ask_quantity=400,
            expected_edge_bps=2000.0,slippage_bps=1.0,
            realized_daily_loss_pct=0.0,consecutive_losses=0,
            current_drawdown_pct=0.0,
        ),
    )
    assert d.research_ledger.status().open_order_count==1
    assert d.research_ledger.verify_integrity()
    assert d.status().read_only
    with pytest.raises(PaperDeploymentBlocked,match="outstanding reservations"):
        d.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)


def test_durable_gateway_policy_cannot_be_switched_off_after_startup(tmp_path):
    d=_open(_cfg(tmp_path,enabled=True))
    d.virtual_account.gateway_only_mode=False
    assert d.status().read_only
    with pytest.raises(PaperDeploymentBlocked):
        d.request_buy(symbol="ABC",quantity=1,entry_price=100,stop_price=95)


def test_stage43_cli_smoke_outputs_only_bounded_synthetic_evidence():
    root=Path(__file__).resolve().parents[1]
    proc=subprocess.run(
        [sys.executable,str(root/"scripts"/"run_stage43_paper_deployment_smoke.py")],
        text=True,capture_output=True,check=False,cwd=root,timeout=45,
    )
    assert proc.returncode==0,proc.stderr
    report=json.loads(proc.stdout)
    assert report["all_checks_passed"]
    assert report["checks_passed"]==report["checks_total"]==10
    assert report["live_orders_transmitted"]==0
    assert report["production_ready"] is False
    assert report["cross_ledger_atomicity_verified"] is False
    assert report["externally_authenticated_identity"] is False
