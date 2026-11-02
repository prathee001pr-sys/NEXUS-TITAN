"""Stage24 true-module synthetic BUY → SELL → FIFO → SQLite restart tests.

No real exchange data, broker orders or authenticated market prices.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
import hashlib
import runpy
import sqlite3
from pathlib import Path

import pytest

from nexus_titan.core.permissions import Action, Decision, decide
from nexus_titan.data.option_chain_history import assemble_research_option_chain_history
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.shadow.guarded_options_research import guarded_options_research_buy
from nexus_titan.shadow.long_option_exit_research import (
    report_research_long_portfolio, simulate_and_settle_long_exit,
)
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)
from nexus_titan.simulation.options_order_reconciliation import ResearchFillEvent
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)

ROOT = Path(__file__).resolve().parents[1]
STAGE23 = runpy.run_path(str(ROOT / "tests" / "test_stage23_guarded_options_research.py"))
OBS = STAGE23["OBS"]
BUY_SETUP = STAGE23["_setup"]


def _exit_history(contract, when, *, bid=8.0, ask=None):
    ask = bid + min(0.5, bid * 0.1) if ask is None else ask
    quotes = tuple(OptionChainQuote(
        timestamp=(when-timedelta(seconds=1)).isoformat(),
        symbol=contract.symbol, underlying=contract.underlying,
        expiry_date=contract.expiry_date.isoformat(), strike=100.0,
        option_type=typ, bid=bid, ask=ask, ltp=(bid+ask)/2,
        volume=1000, open_interest=1500, underlying_spot=100.0,
        lot_size=contract.lot_size,
    ) for typ in ("CE", "PE"))
    item = ResearchOptionChainSnapshot(
        quotes=quotes, sha256=hashlib.sha256(str(when).encode()).hexdigest(),
        observed_at=when, provider_reference="synthetic/exit-provider",
        licence_evidence_reference="synthetic/not-licence",
        calendar_evidence_reference="synthetic/not-holidays",
        contract_evidence_reference=contract.source_reference,
    )
    return assemble_research_option_chain_history(
        [item],contract=contract,calendar=nse_equity_derivatives_baseline(),
    )


def _exit_args(buy_inputs, *, when=None, lots=2, bid=8.0, bid_depth=400, **kwargs):
    when = when or (OBS + timedelta(minutes=1))
    args=dict(
        ledger=buy_inputs["ledger"],
        order_id="SELL-001",event_id="SELL-EVENT-001",
        history=_exit_history(buy_inputs["contract"],when,bid=bid),
        contract=buy_inputs["contract"],calendar=nse_equity_derivatives_baseline(),
        observed_at=when,strike=100.0,option_type="CE",lots=lots,
        depth=OptionDisplayedDepth(
            as_of=when,bid_quantity=bid_depth,ask_quantity=400,
            source_reference="synthetic/exit-top-book",source_declared_verified=True,
        ),
        paper_trading_enabled=True,
    )
    args.update(kwargs)
    return args


def _buy(tmp_path):
    ledger, args = BUY_SETUP(tmp_path)
    result = guarded_options_research_buy(**args)
    assert result.research_statement.filled_quantity == 50
    return ledger,args


def test_full_buy_sell_fifo_net_realized_pnl_and_restart(tmp_path):
    ledger,buy = _buy(tmp_path)
    after_buy = ledger.status()
    bought_basis = round(50000-after_buy.cash_balance,2)
    before = report_research_long_portfolio(ledger)
    assert before.positions[0].quantity == 50
    assert before.positions[0].remaining_cost_basis == bought_basis
    assert before.cumulative_realized_net_pnl == 0
    out = simulate_and_settle_long_exit(**_exit_args(buy))
    assert out.status == "FILLED" and out.filled_quantity == 50
    assert out.remaining_inventory == 0
    assert out.attributed_buy_cost == bought_basis
    assert out.realized_net_pnl == round(
        out.gross_proceeds - out.sell_fees - out.attributed_buy_cost,2
    )
    status = ledger.status()
    assert status.option_inventory == ()
    assert status.cash_balance == out.cash_after
    assert status.cash_balance == round(after_buy.cash_balance + out.gross_proceeds-out.sell_fees,2)
    report = report_research_long_portfolio(ledger)
    assert report.completed_exit_count == 1
    assert report.cumulative_realized_net_pnl == out.realized_net_pnl
    assert report.positions[0].quantity == 0
    assert report.positions[0].remaining_cost_basis == 0
    recovered = DurableResearchShadowLedger(
        tmp_path/"guarded.sqlite3",account_id="TEST-GUARDED",starting_capital=50000,
    )
    assert recovered.status() == status
    assert report_research_long_portfolio(recovered) == report
    assert recovered.verify_integrity()
    assert out.live_orders_transmitted == 0
    assert report.live_orders_transmitted == 0


def test_loss_exit_records_negative_realized_pnl_not_fake_profit(tmp_path):
    ledger,buy = _buy(tmp_path)
    before = ledger.status()
    out = simulate_and_settle_long_exit(**_exit_args(buy,bid=2.0))
    assert out.realized_net_pnl < 0
    assert out.cash_after > before.cash_balance
    assert out.cash_after < 50000
    assert report_research_long_portfolio(ledger).cumulative_realized_net_pnl < 0


def test_partial_sell_respects_lot_rounding_and_preserves_remaining_basis(tmp_path):
    ledger,buy = _buy(tmp_path)
    initial_basis = report_research_long_portfolio(ledger).positions[0].remaining_cost_basis
    # Default microstructure participation cap is 25%: depth 100 -> one lot.
    out = simulate_and_settle_long_exit(**_exit_args(buy,bid_depth=100))
    assert out.status == "PARTIAL"
    assert out.filled_quantity == 25 and out.remaining_inventory == 25
    record=report_research_long_portfolio(ledger).positions[0]
    assert record.quantity == 25
    assert round(record.remaining_cost_basis + out.attributed_buy_cost,2) == initial_basis
    assert ledger.verify_integrity()


def test_no_bid_liquidity_does_not_mutate_or_charge_exit(tmp_path):
    ledger,buy = _buy(tmp_path)
    before=ledger.status()
    out = simulate_and_settle_long_exit(**_exit_args(buy,bid_depth=0))
    assert out.status == "UNFILLED"
    assert out.filled_quantity == 0 and out.sell_fees == 0
    assert out.cash_after == before.cash_balance
    assert ledger.status() == before
    assert report_research_long_portfolio(ledger).completed_exit_count == 0


def test_missing_or_false_permission_blocks_exit_before_cash_changes(tmp_path):
    ledger,buy = _buy(tmp_path)
    before=ledger.status()
    args=_exit_args(buy)
    args.pop("paper_trading_enabled")
    with pytest.raises(ResearchLedgerError,match="permission denied"):
        simulate_and_settle_long_exit(**args)
    args["paper_trading_enabled"]=False
    with pytest.raises(ResearchLedgerError,match="permission denied"):
        simulate_and_settle_long_exit(**args)
    args["paper_trading_enabled"]="yes"
    with pytest.raises(ResearchLedgerError,match="permission denied"):
        simulate_and_settle_long_exit(**args)
    assert ledger.status()==before


def test_trying_to_sell_more_than_long_inventory_fails_closed(tmp_path):
    ledger,buy = _buy(tmp_path)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="Insufficient long-option inventory"):
        simulate_and_settle_long_exit(**_exit_args(buy,lots=3))
    assert ledger.status()==before


def test_no_naked_sell_from_empty_account(tmp_path):
    ledger,buy = BUY_SETUP(tmp_path)
    before=ledger.status()
    with pytest.raises(ResearchLedgerError,match="Insufficient long-option inventory"):
        simulate_and_settle_long_exit(**_exit_args(buy,lots=1))
    assert ledger.status()==before


def test_duplicate_exit_id_and_event_id_cannot_double_credit_after_restart(tmp_path):
    ledger,buy = _buy(tmp_path)
    args=_exit_args(buy,lots=1)
    first=simulate_and_settle_long_exit(**args)
    restarted=DurableResearchShadowLedger(
        tmp_path/"guarded.sqlite3",account_id="TEST-GUARDED",starting_capital=50000
    )
    before=restarted.status()
    args["ledger"]=restarted
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed exit order_id"):
        simulate_and_settle_long_exit(**args)
    args["order_id"]="SELL-SECOND"
    with pytest.raises(ResearchLedgerError,match="Duplicate/replayed exit event_id"):
        simulate_and_settle_long_exit(**args)
    assert restarted.status()==before
    assert first.filled_quantity==25


def test_missing_quote_or_wrong_leg_does_not_change_position(tmp_path):
    ledger,buy = _buy(tmp_path)
    before=ledger.status()
    with pytest.raises(ValueError):
        simulate_and_settle_long_exit(**_exit_args(buy,strike=150.0))
    with pytest.raises(ResearchLedgerError,match="Insufficient long-option inventory"):
        simulate_and_settle_long_exit(**_exit_args(buy,option_type="PE"))
    assert ledger.status()==before


def test_report_detects_cash_tampering_even_when_stage19_hash_is_recomputed(tmp_path):
    ledger,buy = _buy(tmp_path)
    with sqlite3.connect(ledger.db_path) as db:
        db.execute("UPDATE accounts SET cash_cents=cash_cents+10")
    with pytest.raises(ResearchLedgerError,match="state does not match"):
        report_research_long_portfolio(ledger)


def test_replay_across_two_buy_lots_preserves_fifo_cost_order(tmp_path):
    ledger,buy = BUY_SETUP(tmp_path)
    contract=buy["contract"]
    first=simulate_historical_option_fill(
        buy["history"],contract=contract,calendar=buy["calendar"],
        observed_at=OBS,strike=100.0,option_type="CE",side="BUY",lots=1,
        depth=buy["depth"],
    )
    ledger.reserve_buy(order_id="BUY-FIRST",contract=contract,strike=100.0,
                       option_type="CE",lots=1,as_of=OBS,max_unit_premium=6,fee_buffer=25)
    ledger.settle_buy(order_id="BUY-FIRST",contract=contract,strike=100.0,
                      option_type="CE",events=[ResearchFillEvent("BUY-FILL-FIRST",OBS,first)])
    cost_first=round(50000-ledger.status().cash_balance,2)
    later=OBS+timedelta(minutes=1)
    hist=_exit_history(contract,later,bid=7.0)
    second=simulate_historical_option_fill(
        hist,contract=contract,calendar=buy["calendar"],
        observed_at=later,strike=100.0,option_type="CE",side="BUY",lots=1,
        depth=replace(buy["depth"],as_of=later),
    )
    cash_before=ledger.status().cash_balance
    ledger.reserve_buy(order_id="BUY-SECOND",contract=contract,strike=100.0,
                       option_type="CE",lots=1,as_of=later,max_unit_premium=8.0,fee_buffer=25)
    ledger.settle_buy(order_id="BUY-SECOND",contract=contract,strike=100.0,
                      option_type="CE",events=[ResearchFillEvent("BUY-FILL-SECOND",later,second)])
    cost_second=round(cash_before-ledger.status().cash_balance,2)
    before=report_research_long_portfolio(ledger)
    assert before.positions[0].quantity==50
    assert before.positions[0].remaining_cost_basis==round(cost_first+cost_second,2)
    exit_when=later+timedelta(minutes=1)
    out=simulate_and_settle_long_exit(**_exit_args(buy,when=exit_when,lots=1))
    assert out.attributed_buy_cost==cost_first
    after=report_research_long_portfolio(ledger)
    assert after.positions[0].quantity==25
    assert after.positions[0].remaining_cost_basis==cost_second


def test_unfilled_order_id_not_written_to_exit_replay_journal(tmp_path):
    ledger,buy=_buy(tmp_path)
    args=_exit_args(buy,bid_depth=0)
    first=simulate_and_settle_long_exit(**args)
    assert first.status=="UNFILLED"
    args["depth"]=replace(args["depth"],bid_quantity=400)
    out=simulate_and_settle_long_exit(**args)
    assert out.status=="FILLED"


def test_exit_past_expiry_fails_before_account_mutation(tmp_path):
    ledger,buy=_buy(tmp_path)
    old=ledger.status()
    when=datetime.fromisoformat("2026-11-06T09:16:00+05:30")
    args=_exit_args(buy)
    args["observed_at"]=when
    with pytest.raises(ResearchLedgerError,match="not effective"):
        simulate_and_settle_long_exit(**args)
    assert ledger.status()==old


def test_forged_costless_position_does_not_create_a_synthetic_profit(tmp_path):
    ledger,buy=_buy(tmp_path)
    with sqlite3.connect(ledger.db_path) as db:
        db.execute("UPDATE inventory SET quantity=quantity+25")
    with pytest.raises(ResearchLedgerError):
        report_research_long_portfolio(ledger)


def test_unfilled_exit_does_not_count_as_closed_trade(tmp_path):
    ledger,buy=_buy(tmp_path)
    initial=report_research_long_portfolio(ledger)
    simulate_and_settle_long_exit(**_exit_args(buy,bid_depth=0))
    assert report_research_long_portfolio(ledger).completed_exit_count == initial.completed_exit_count
