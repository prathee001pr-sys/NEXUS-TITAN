"""Stage31 synthetic-only manual-to-auto permission escalation tests."""
from __future__ import annotations

import pytest
from nexus_titan.virtual.order_manager import VirtualAccount, TradingMode, OrderState

RESOURCE="MODE:MANUAL_APPROVAL->AUTO_PAPER"


def _account(**kw):
    return VirtualAccount(
        "STAGE31",starting_capital=50000,
        trading_mode=TradingMode.MANUAL_APPROVAL,
        require_pretrade_risk_check=False,**kw,
    )


def test_default_manual_mode_rejects_auto_without_identity_callback():
    a=_account()
    with pytest.raises(PermissionError,match="Authenticated approval"):
        a.set_trading_mode(TradingMode.AUTO_PAPER)
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL
    assert a.submit_order("ABC","BUY",1).state is OrderState.PENDING_APPROVAL


@pytest.mark.parametrize("response",[False,None,0,1,"yes"])
def test_untrusted_callback_response_denied(response):
    a=_account(approval_authorizer=lambda actor,resource: response)
    with pytest.raises(PermissionError,match="Authenticated approval"):
        a.set_trading_mode("AUTO_PAPER",actor="OWNER")
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL


def test_approval_callback_sees_exact_mode_resource_and_actor():
    calls=[]
    def approve(actor,resource):
        calls.append((actor,resource))
        return actor=="OWNER" and resource==RESOURCE
    a=_account(approval_authorizer=approve)
    with pytest.raises(PermissionError,match="Authenticated approval"):
        a.set_trading_mode("AUTO_PAPER",actor="ATTACKER")
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL
    a.set_trading_mode("AUTO_PAPER",actor=" OWNER ")
    assert calls==[("ATTACKER",RESOURCE),("OWNER",RESOURCE)]
    assert a.trading_mode is TradingMode.AUTO_PAPER
    assert a.submit_order("ABC","BUY",1).state is OrderState.ACCEPTED


def test_no_auth_required_for_conservative_manual_mode():
    a=VirtualAccount(starting_capital=50000,require_pretrade_risk_check=False)
    assert a.trading_mode is TradingMode.AUTO_PAPER
    a.set_trading_mode("MANUAL_APPROVAL")
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL


def test_redundant_manual_mode_setting_is_safe_noop():
    a=_account()
    a.set_trading_mode(TradingMode.MANUAL_APPROVAL)
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL


def test_kill_switch_blocks_even_authenticated_manual_to_auto():
    a=_account(approval_authorizer=lambda actor,resource: True)
    a.activate_emergency_kill_switch()
    with pytest.raises(PermissionError,match="kill switch prohibits"):
        a.set_trading_mode("AUTO_PAPER",actor="OWNER")
    assert a.trading_mode is TradingMode.MANUAL_APPROVAL


def test_authorized_auto_mode_is_persisted_after_restart(tmp_path):
    a=_account(state_dir=tmp_path,
               approval_authorizer=lambda actor,resource: actor=="OWNER" and resource==RESOURCE)
    a.set_trading_mode("AUTO_PAPER",actor="OWNER")
    reopened=_account(state_dir=tmp_path)
    assert reopened.trading_mode is TradingMode.AUTO_PAPER
    reopened.set_trading_mode("MANUAL_APPROVAL")
    strict=_account(state_dir=tmp_path)
    assert strict.trading_mode is TradingMode.MANUAL_APPROVAL
    with pytest.raises(PermissionError,match="Authenticated approval"):
        strict.set_trading_mode("AUTO_PAPER")
    assert strict.trading_mode is TradingMode.MANUAL_APPROVAL


def test_live_mode_never_enabled_even_if_auth_callback_is_true():
    a=_account(approval_authorizer=lambda actor,resource: True)
    with pytest.raises(ValueError,match="Live trading"):
        a.set_trading_mode(TradingMode.LIVE_DISABLED,actor="OWNER")
