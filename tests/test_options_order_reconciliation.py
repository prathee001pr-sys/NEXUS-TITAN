"""Synthetic offline tests for options fragment reconciliation; no real trades."""
from dataclasses import replace
from datetime import date, datetime, timedelta
import hashlib

import pytest

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import assemble_research_option_chain_history
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)
from nexus_titan.simulation.options_order_reconciliation import (
    OptionsReconciliationError, ResearchFillEvent, reconcile_options_research_order,
)
from nexus_titan.cost.charges import IndianCostConfig


OBS = datetime.fromisoformat("2026-11-02T09:16:00+05:30")


def _contract(**changes):
    opts = dict(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1), effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5), strike_step=50,
        source_reference="evidence/test-contract", source_verified=True,
    )
    opts.update(changes)
    return PointInTimeContractSpec(**opts)


def _history():
    quote_time=(OBS-timedelta(seconds=1)).isoformat()
    quotes=tuple(OptionChainQuote(
        timestamp=quote_time, symbol="NIFTYOPT", underlying="NIFTY",
        expiry_date="2026-11-05", strike=100, option_type=type_,
        bid=5.0, ask=5.5, ltp=5.25, volume=2000, open_interest=1200,
        underlying_spot=100.0, lot_size=25,
    ) for type_ in ("CE","PE"))
    item=ResearchOptionChainSnapshot(
        quotes=quotes, sha256=hashlib.sha256(b"fixture").hexdigest(),
        observed_at=OBS, provider_reference="evidence/provider",
        licence_evidence_reference="evidence/licence",
        calendar_evidence_reference="evidence/calendar",
        contract_evidence_reference="evidence/test-contract",
    )
    return assemble_research_option_chain_history(
        [item], contract=_contract(), calendar=nse_equity_derivatives_baseline()
    )


def _fragment(*, lots=4, ask_depth=200, bid_depth=400, side="BUY", cost=None):
    depth=OptionDisplayedDepth(
        as_of=OBS, ask_quantity=ask_depth, bid_quantity=bid_depth,
        source_reference="evidence/topbook", source_declared_verified=True,
    )
    return simulate_historical_option_fill(
        _history(), contract=_contract(), calendar=nse_equity_derivatives_baseline(),
        observed_at=OBS, strike=100, option_type="CE", side=side,
        lots=lots, depth=depth, costs=cost,
    )


def _evt(seq, fragment, *, at=None):
    return ResearchFillEvent(str(seq), at or OBS+timedelta(seconds=seq-1), fragment)


def _reconcile(*events, **change):
    params=dict(
        events=list(events), order_id="RESEARCH-ORDER-1", contract=_contract(),
        strike=100.0, option_type="CE", side="BUY",
        requested_lots=4, starting_cash=50000,
    )
    params.update(change)
    return reconcile_options_research_order(**params)


def test_two_partial_fragments_finish_one_order_without_overfill():
    one=_fragment(lots=4,ask_depth=200)
    two=_fragment(lots=2,ask_depth=400)
    assert one.status=="PARTIAL" and two.status=="FILLED"
    result=_reconcile(_evt(1,one),_evt(2,two))
    assert (result.requested_quantity,result.filled_quantity,result.remaining_quantity)==(100,100,0)
    assert result.status=="FILLED" and result.fill_count==2
    assert result.projected_inventory_quantity==100
    assert result.projected_cash < result.starting_cash
    assert result.live_orders_transmitted==0
    assert not result.approved_for_strategy_promotion
    assert result.conservative_fee_reserve==max(result.fragment_fee_sum,result.recomputed_order_fee)
    assert result.total_estimated_friction==round(result.total_execution_shortfall+result.conservative_fee_reserve,2)


def test_partial_one_fragment_keeps_residual_and_lot_alignment():
    first=_fragment()
    result=_reconcile(_evt(1,first))
    assert result.status=="PARTIAL"
    assert (result.filled_quantity,result.remaining_quantity)==(50,50)


def test_first_attempt_no_liquidity_then_success_does_not_create_phantom_fees():
    missed=_fragment(lots=4,ask_depth=0)
    first=_fragment(lots=4,ask_depth=400)
    result=_reconcile(_evt(1,missed),_evt(2,first))
    assert result.unfilled_attempt_count==1
    assert result.fill_count==1 and result.filled_quantity==100
    assert result.status=="FILLED"


def test_no_fill_means_cash_and_inventory_unchanged():
    result=_reconcile(_evt(1,_fragment(ask_depth=0)))
    assert result.status=="UNFILLED"
    assert result.conservative_fee_reserve==0
    assert result.projected_cash==50000
    assert result.projected_inventory_quantity==0
    assert result.average_fill_price is None


def test_replay_event_id_is_rejected():
    first=_fragment()
    with pytest.raises(OptionsReconciliationError,match="duplicate/replayed"):
        _reconcile(_evt(1,first),_evt(1,first))


def test_duplicate_fill_across_new_ids_cannot_exceed_remaining_order():
    first=_fragment()
    with pytest.raises(OptionsReconciliationError,match="requested quantity"):
        _reconcile(_evt(1,first),_evt(2,first))


def test_event_timestamp_must_be_monotonic():
    one=_fragment()
    two=_fragment(lots=2,ask_depth=400)
    with pytest.raises(OptionsReconciliationError,match="strictly increasing"):
        _reconcile(_evt(1,one,at=OBS),_evt(2,two,at=OBS))


def test_event_timestamp_requires_timezone():
    with pytest.raises(OptionsReconciliationError,match="timezone-aware"):
        _reconcile(_evt(1,_fragment(),at=datetime(2026,11,2,9,16)))


def test_order_cannot_straddle_india_trading_dates():
    with pytest.raises(OptionsReconciliationError,match="multiple India trading dates"):
        _reconcile(_evt(1,_fragment()),_evt(2,_fragment(lots=2,ask_depth=400),
                  at=OBS+timedelta(days=1)))


def test_fee_forgery_and_notional_mismatch_rejected():
    valid=_fragment()
    for forged in (
        replace(valid,estimated_fees=0),
        replace(valid,notional=10),
        replace(valid,total_estimated_friction=valid.total_estimated_friction+10),
    ):
        with pytest.raises(OptionsReconciliationError):
            _reconcile(_evt(1,forged))


def test_forged_promotion_or_live_count_fails_closed():
    valid=_fragment()
    for fake in (replace(valid,approved_for_strategy_promotion=True),
                 replace(valid,live_orders_transmitted=1)):
        with pytest.raises(OptionsReconciliationError,match="promotion/live"):
            _reconcile(_evt(1,fake))


def test_forged_residual_and_lot_mismatch_rejected():
    valid=_fragment()
    for fake in (replace(valid,remaining_quantity=49),
                 replace(valid,filled_quantity=51),
                 replace(valid,requested_quantity=99)):
        with pytest.raises(OptionsReconciliationError):
            _reconcile(_evt(1,fake))


def test_false_fill_status_rejected():
    valid=_fragment()
    with pytest.raises(OptionsReconciliationError,match="status"):
        _reconcile(_evt(1,replace(valid,status="FILLED")))


def test_phantom_unfilled_fees_rejected():
    valid=_fragment(ask_depth=0)
    with pytest.raises(OptionsReconciliationError,match="phantom"):
        _reconcile(_evt(1,replace(valid,estimated_fees=2.0)))


def test_virtual_cash_insufficiency_fails_closed():
    with pytest.raises(OptionsReconciliationError,match="Insufficient virtual cash"):
        _reconcile(_evt(1,_fragment(lots=4,ask_depth=400)),starting_cash=1.0)


def test_starting_cash_is_configurable_not_fixed_at_50000():
    result=_reconcile(_evt(1,_fragment()),starting_cash=2500.0)
    assert result.starting_cash==2500.0
    assert 0 < result.projected_cash < 2500.0


def test_naked_short_sell_rejected_without_inventory():
    with pytest.raises(OptionsReconciliationError,match="pre-existing"):
        _reconcile(_evt(1,_fragment(side="SELL")),side="SELL")


def test_sell_with_long_inventory_reduces_inventory_and_credits_cash():
    # Use a full four-lot long inventory; the scenario makes no P&L assertion.
    fill=_fragment(side="SELL",lots=4,bid_depth=400)
    out=_reconcile(_evt(1,fill),side="SELL",starting_inventory_quantity=100)
    assert out.status=="FILLED"
    assert out.projected_inventory_quantity==0
    assert out.projected_cash>50000.0
    assert out.total_estimated_friction>=0


def test_sell_with_insufficient_long_inventory_is_rejected():
    with pytest.raises(OptionsReconciliationError,match="pre-existing"):
        _reconcile(_evt(1,_fragment(side="SELL")),side="SELL",starting_inventory_quantity=50)


def test_sell_inventory_must_be_whole_lots():
    with pytest.raises(OptionsReconciliationError,match="lot-aligned"):
        _reconcile(_evt(1,_fragment(side="SELL")),side="SELL",starting_inventory_quantity=101)


def test_fragment_fee_schedule_must_match_explicit_reconciliation_schedule():
    custom=IndianCostConfig(brokerage_pct=0.0)
    frag=_fragment(cost=custom)
    with pytest.raises(OptionsReconciliationError,match="fragment fees"):
        _reconcile(_evt(1,frag))
    matched=_reconcile(_evt(1,frag),cost_config=custom)
    assert matched.cost_schedule_version==custom.version


def test_aggregate_fee_model_and_fragments_not_blindly_added_together():
    first=_fragment(lots=4,ask_depth=200)
    second=_fragment(lots=2,ask_depth=400)
    report=_reconcile(_evt(1,first),_evt(2,second))
    assert report.conservative_fee_reserve==max(
        report.recomputed_order_fee,report.fragment_fee_sum)
    assert report.fee_model_difference==round(
        report.fragment_fee_sum-report.recomputed_order_fee,2)


@pytest.mark.parametrize("value",[-1,0,True,0.5,float("nan"),float("inf")])
def test_bad_virtual_cash_fails(value):
    with pytest.raises(OptionsReconciliationError):
        _reconcile(_evt(1,_fragment()),starting_cash=value)


@pytest.mark.parametrize("change",[
    {"requested_lots":0}, {"requested_lots":True},
    {"requested_lots":100}, {"starting_inventory_quantity":-1},
    {"order_id":""}, {"strike":float("nan")}, {"strike":0},
    {"side":"HOLD"}, {"option_type":"X"}, {"max_events":0},
    {"max_events":True}, {"cost_config":"invalid"},
])
def test_invalid_configuration_fails(change):
    with pytest.raises(OptionsReconciliationError):
        _reconcile(_evt(1,_fragment()),**change)


def test_empty_and_unbounded_events_rejected():
    with pytest.raises(OptionsReconciliationError,match="At least one"):
        _reconcile()
    with pytest.raises(OptionsReconciliationError,match="max_events"):
        _reconcile(_evt(1,_fragment()),_evt(2,_fragment(lots=2,ask_depth=400)),max_events=1)


def test_reconciliation_is_pure_deterministic_no_external_order_side_effects():
    events=[_evt(1,_fragment())]
    result1=_reconcile(*events)
    result2=_reconcile(*events)
    assert result1==result2
    assert result1.live_orders_transmitted==0
