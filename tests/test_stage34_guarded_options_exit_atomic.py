"""Stage34: guard long-options SELL-to-close under the same SQLite transaction."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import runpy

import pytest

from nexus_titan.shadow.guarded_options_research import guarded_options_research_buy
from nexus_titan.shadow.long_option_exit_research import (
    _assert_guarded_exit_admission, report_research_long_portfolio,
    simulate_and_settle_long_exit,
)
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)

ROOT=Path(__file__).resolve().parents[1]
STAGE24=runpy.run_path(str(ROOT/"tests"/"test_stage24_long_option_exit_research.py"))


def _guarded_buy(tmp_path):
    ledger,params=STAGE24["BUY_SETUP"](tmp_path)
    ledger.enable_guarded_paper_mode()
    buy=guarded_options_research_buy(**params)
    assert buy.live_orders_transmitted==0
    return ledger,params


def _sell_params(params,**kw):
    data=STAGE24["_exit_args"](params)
    data.update(kw)
    return data


def test_guarded_long_sell_settlement_is_atomic_and_recoverable(tmp_path):
    ledger,params=_guarded_buy(tmp_path)
    before=ledger.status()
    result=simulate_and_settle_long_exit(**_sell_params(params))
    assert result.status=="FILLED"
    assert result.filled_quantity==50
    assert result.remaining_inventory==0
    assert result.live_orders_transmitted==0
    assert ledger.status().cash_balance>before.cash_balance
    assert ledger.verify_integrity()
    reopened=DurableResearchShadowLedger(ledger.db_path,account_id=ledger.account_id,
                                         starting_capital=50000)
    assert reopened.guarded_paper_mode and reopened.status()==ledger.status()
    assert report_research_long_portfolio(reopened)==report_research_long_portfolio(ledger)


def test_guarded_sell_permission_false_denies_without_mutation(tmp_path):
    ledger,params=_guarded_buy(tmp_path)
    before=ledger.status()
    for permission in (False,"true",1,None):
        with pytest.raises(ResearchLedgerError,match="permission denied"):
            simulate_and_settle_long_exit(**_sell_params(params,paper_trading_enabled=permission))
        assert ledger.status()==before


def test_guarded_sell_repeated_order_and_event_id_cannot_double_credit(tmp_path):
    ledger,params=_guarded_buy(tmp_path)
    data=_sell_params(params,lots=1)
    simulate_and_settle_long_exit(**data)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed exit order_id"):
        simulate_and_settle_long_exit(**data)
    second={**data,"order_id":"SECOND"}
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed exit event_id"):
        simulate_and_settle_long_exit(**second)
    assert ledger.status()==before and ledger.verify_integrity()


def test_guarded_sell_partial_preserves_fifo_quantity(tmp_path):
    ledger,params=_guarded_buy(tmp_path)
    data=_sell_params(params,bid_depth=100)
    exit=simulate_and_settle_long_exit(**data)
    assert exit.status=="PARTIAL"
    assert exit.filled_quantity==25 and exit.remaining_inventory==25
    assert ledger.verify_integrity()


def test_guarded_unfilled_exit_does_not_debit_or_replay(tmp_path):
    ledger,params=_guarded_buy(tmp_path)
    before=ledger.status()
    result=simulate_and_settle_long_exit(**_sell_params(params,bid_depth=0))
    assert result.status=="UNFILLED"
    assert ledger.status()==before


def test_guarded_atomic_exit_rejects_pending_reservation_and_no_side_effect(tmp_path):
    ledger,params=STAGE24["BUY_SETUP"](tmp_path)
    ledger.enable_guarded_paper_mode()
    admission=__import__(
        "nexus_titan.shadow.research_reservation_ledger",fromlist=["GuardedBuyAdmission"]
    ).GuardedBuyAdmission
    # Test the transaction boundary with an authentic pending guarded BUY.
    from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig
    ledger.reserve_buy_guarded(
        order_id="PENDING",contract=params["contract"],
        strike=100.0,option_type="CE",lots=2,as_of=params["observed_at"],
        max_unit_premium=6.0,fee_buffer=25.0,
        admission=admission(
            paper_trading_enabled=True,risk_config=PortfolioRiskConfig(),
            stop_price=5.0,bid=5.0,ask=5.5,ask_quantity=400,
            expected_edge_bps=2000.0,slippage_bps=1.0,
            realized_daily_loss_pct=0.0,consecutive_losses=0,
            current_drawdown_pct=0.0,
        ),
    )
    before=ledger.status()
    with ledger._transaction() as con:
        with pytest.raises(ResearchLedgerError,match="pending BUY"):
            _assert_guarded_exit_admission(ledger,con,paper_trading_enabled=True)
    assert ledger.status()==before


def test_legacy_research_sell_still_supported(tmp_path):
    ledger,params=STAGE24["_buy"](tmp_path)
    assert not ledger.guarded_paper_mode
    result=simulate_and_settle_long_exit(**_sell_params(params))
    assert result.filled_quantity==50 and result.live_orders_transmitted==0


def test_guarded_exit_never_provides_short_or_live_trading(tmp_path):
    ledger,params=_guarded_buy(tmp_path)
    result=simulate_and_settle_long_exit(**_sell_params(params))
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="Insufficient long-option inventory"):
        simulate_and_settle_long_exit(**_sell_params(params,order_id="UNOWNED",event_id="NEW"))
    assert ledger.status()==before
    assert result.live_orders_transmitted==0
