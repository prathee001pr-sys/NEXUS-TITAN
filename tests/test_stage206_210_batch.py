"""Stages 206–210: strictly offline synthetic execution research gates."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus_titan.data.stage205_fo_data_readiness_gate import FODataReadinessReceipt
from nexus_titan.data.stage206_depth_snapshot import DepthLevel, DepthSnapshot, audit_depth_snapshot
from nexus_titan.data.stage207_liquidity_fill import audit_liquidity_fill
from nexus_titan.data.stage208_fee_sensitivity import FeeScenario, audit_fee_sensitivity
from nexus_titan.data.stage209_capacity_stress import CapacityCase, audit_capacity_stress
from nexus_titan.data.stage210_execution_no_go_gate import evaluate_execution_no_go_gate

T0 = datetime(2024, 1, 2, 9, 15, tzinfo=timezone.utc)


def fixture_book():
    return DepthSnapshot('snap-1', 'NIFTY2024CE', 'a'*64, T0,
                         T0+timedelta(milliseconds=50),
                         (DepthLevel('99.95', 200), DepthLevel('99.90', 100)),
                         (DepthLevel('100.05', 200), DepthLevel('100.10', 100)))


def fixture_depth(book=None, **kw):
    book = book if book is not None else fixture_book()
    return audit_depth_snapshot(book, decision_at=T0+timedelta(milliseconds=300),
                                tick_size='0.05', **kw)


def fee_scenario():
    return FeeScenario('20', 10, 1, 1, 1800, 3, 5)


def capacities():
    return (CapacityCase('base', 150, 10000, 20, 100, 200),
            CapacityCase('depth-stress', 250, 10000, 40, 100, 200))


def all_valid():
    snap = fixture_book()
    depth = fixture_depth(snap)
    fill = audit_liquidity_fill(snap, depth=depth, side='BUY', quantity=150,
                                participation_bps=10000,max_adverse_slippage_bps=100,
                                latency_ms=20)
    fees = audit_fee_sensitivity(fill, scenario=fee_scenario(), contract_multiplier=1)
    stress = audit_capacity_stress(snap, depth=depth, side='BUY', cases=capacities(),
                                   fees=fee_scenario(), contract_multiplier=1)
    readiness = FODataReadinessReceipt(True, 'b'*64, ())
    return dict(snapshot=snap, depth=depth, fill=fill, fees=fees,
                capacity=stress, data_readiness=readiness, side='BUY', quantity=150,
                participation_bps=10000, max_adverse_slippage_bps=100, latency_ms=20,
                fee_scenario=fee_scenario(), cases=capacities(), contract_multiplier=1)


def test_206_valid_causal_depth_is_not_verified_exchange_data():
    r=fixture_depth()
    assert r.accepted and r.best_bid==Decimal('99.95') and r.best_ask==Decimal('100.05')
    assert r.bid_quantity==300 and r.ask_quantity==300
    assert len(r.snapshot_sha256)==64 and not r.live_trading_authorized
    assert r==fixture_depth()


@pytest.mark.parametrize('mutate',[
    lambda s: replace(s,snapshot_id='../wrong'),
    lambda s: replace(s,contract_id='NIFTY!'),
    lambda s: replace(s,dataset_sha256='bad'),
    lambda s: replace(s,observed_at=s.available_at+timedelta(seconds=1)),
    lambda s: replace(s,available_at=T0+timedelta(seconds=1)),
    lambda s: replace(s,observed_at=T0.replace(tzinfo=None)),
    lambda s: replace(s,bids=()),
    lambda s: replace(s,asks=()),
    lambda s: replace(s,bids=s.bids*6),
    lambda s: replace(s,bids=(DepthLevel('99.95',100), DepthLevel('100.00',100))),
    lambda s: replace(s,asks=(DepthLevel('100.05',100), DepthLevel('100.05',100))),
    lambda s: replace(s,bids=(DepthLevel('100.15',100),)),
    lambda s: replace(s,asks=(DepthLevel('100.03',100),)),
    lambda s: replace(s,asks=(DepthLevel('NaN',100),)),
    lambda s: replace(s,asks=(DepthLevel('100.05',True),)),
    lambda s: replace(s,asks=(DepthLevel('100.05',-1),)),
    lambda s: replace(s,asks=(DepthLevel('100.05',1000001),)),
    lambda s: replace(s,asks=[DepthLevel('100.05',100)]),
    lambda s: replace(s,bids=(None,)),
])
def test_206_invalid_books_fail_closed(mutate):
    r=fixture_depth(mutate(fixture_book()))
    assert not r.accepted and r.blockers and not r.snapshot_sha256


@pytest.mark.parametrize('k',[
    {'max_age_ms':True},{'max_age_ms':-1},{'max_spread_bps':False},
    {'max_spread_bps':0},
])
def test_206_invalid_quote_limits_fail(k):
    assert not fixture_depth(**k).accepted


def test_206_decision_too_old_future_and_invalid_tick():
    b=fixture_book()
    assert not audit_depth_snapshot(b,decision_at=T0+timedelta(seconds=5),tick_size='0.05').accepted
    assert not audit_depth_snapshot(b,decision_at=T0,tick_size='0.05').accepted
    assert not audit_depth_snapshot(b,decision_at=T0+timedelta(milliseconds=100),tick_size='0').accepted


def test_207_full_partial_and_deterministic_depth_walk():
    b=fixture_book(); d=fixture_depth(b)
    r=audit_liquidity_fill(b,depth=d,side='BUY',quantity=250)
    assert r.accepted and r.fully_filled and r.average_price>Decimal('100.05')
    assert r.adverse_slippage_bps>0 and len(r.fill_sha256)==64
    assert r == audit_liquidity_fill(b,depth=d,side='BUY',quantity=250)
    partial=audit_liquidity_fill(b,depth=d,side='BUY',quantity=400)
    assert partial.accepted and not partial.fully_filled
    assert partial.filled_quantity==300 and partial.unfilled_quantity==100
    sell=audit_liquidity_fill(b,depth=d,side='SELL',quantity=250)
    assert sell.accepted and sell.average_price<Decimal('99.95')
    assert sell.adverse_slippage_bps>0


@pytest.mark.parametrize('kwargs',[
    {'side':'HOLD'}, {'quantity':0}, {'quantity':True}, {'quantity':1000001},
    {'participation_bps':0}, {'participation_bps':10001}, {'participation_bps':True},
    {'max_adverse_slippage_bps':-1}, {'max_adverse_slippage_bps':True},
    {'latency_ms':-1}, {'latency_ms':True}, {'latency_ms':86000000},
    {'tick_size':'0.01'}, {'max_age_ms':0}, {'max_spread_bps':0},
])
def test_207_invalid_or_stale_fills_fail(kwargs):
    b=fixture_book(); d=fixture_depth(b)
    r=audit_liquidity_fill(b,depth=d,side='BUY',quantity=250,**kwargs) if 'side' not in kwargs and 'quantity' not in kwargs else audit_liquidity_fill(b,depth=d,**{'side':'BUY','quantity':250,**kwargs})
    assert not r.accepted and r.blockers


def test_207_tampered_book_receipt_blocked():
    b=fixture_book(); d=fixture_depth(b)
    assert not audit_liquidity_fill(b,depth=replace(d,best_ask=Decimal('100.00')),side='BUY',quantity=100).accepted
    assert not audit_liquidity_fill(replace(b,asks=(DepthLevel('100.10',100),)),depth=d,side='BUY',quantity=100).accepted
    assert not audit_liquidity_fill(b,depth=d,side='BUY',quantity=5,participation_bps=1).accepted
    assert not audit_liquidity_fill(b,depth=d,side='BUY',quantity=250,max_adverse_slippage_bps=0).accepted


def test_208_non_verified_rate_schedule_component_reconciliation():
    a=all_valid(); r=a['fees']
    assert r.accepted and not r.schedule_independently_verified and not r.live_trading_authorized
    assert r.stt==0 and r.stamp>0 and r.gst>0 and r.additional_price_friction>0
    assert r.total_assumed_cost == (r.brokerage+r.stt+r.exchange+r.sebi+r.gst+r.stamp
                                    +r.additional_price_friction)
    sell=audit_liquidity_fill(a['snapshot'],depth=a['depth'],side='SELL',quantity=150)
    sf=audit_fee_sensitivity(sell,scenario=fee_scenario())
    assert sf.accepted and sf.stt>0 and sf.stamp==0


@pytest.mark.parametrize('mutate',[
    lambda s: replace(s,brokerage_fixed='-1'),
    lambda s: replace(s,brokerage_fixed='NaN'),
    lambda s: replace(s,brokerage_fixed='1000001'),
    lambda s: replace(s,stt_sell_bps=-1),
    lambda s: replace(s,exchange_bps=10001),
    lambda s: replace(s,sebi_bps=True),
    lambda s: replace(s,gst_bps=10001),
    lambda s: replace(s,stamp_buy_bps=-1),
    lambda s: replace(s,extra_price_friction_bps=False),
    lambda s: replace(s,other_fixed='0.000000001'),
    lambda s: replace(s,other_fixed='1000001'),
])
def test_208_fee_assumption_injection_rejected(mutate):
    a=all_valid()
    assert not audit_fee_sensitivity(a['fill'],scenario=mutate(fee_scenario())).accepted


def test_208_bad_fill_and_multiplier_blocked():
    a=all_valid()
    for bad in (replace(a['fill'],accepted=False), replace(a['fill'],execution_notional=Decimal('NaN'))):
        assert not audit_fee_sensitivity(bad,scenario=fee_scenario()).accepted
    assert not audit_fee_sensitivity(a['fill'],scenario=fee_scenario(),contract_multiplier=True).accepted
    assert not audit_fee_sensitivity(a['fill'],scenario=fee_scenario(),contract_multiplier=0).accepted


def test_209_stress_grid_rechecks_fee_and_liquidity():
    a=all_valid(); r=a['capacity']
    assert r.accepted and r.scenario_count==2 and r.passed_count==2
    assert len(r.capacity_sha256)==64 and not r.real_market_capacity_verified
    assert r==audit_capacity_stress(a['snapshot'],depth=a['depth'],side='BUY',cases=capacities(),fees=fee_scenario())


@pytest.mark.parametrize('cases',[
    (), (capacities()[0],)*2,
    (replace(capacities()[0],name='../escape'),),
    (replace(capacities()[0],name='A'),),
    (replace(capacities()[0],order_quantity=True),),
    (replace(capacities()[0],participation_bps=0),),
    (replace(capacities()[0],simulated_latency_ms=-1),),
    (replace(capacities()[0],max_slippage_bps=True),),
    (replace(capacities()[0],max_fee_cost_bps=-1),),
    (capacities()[0],)*13,
])
def test_209_invalid_capacity_cases_rejected(cases):
    a=all_valid()
    r=audit_capacity_stress(a['snapshot'],depth=a['depth'],side='BUY',cases=cases,fees=fee_scenario())
    assert not r.accepted and r.blockers


def test_209_excessive_orders_cost_and_latency_fail():
    a=all_valid()
    for case in (
        replace(capacities()[0], order_quantity=500),
        replace(capacities()[0], max_fee_cost_bps=0),
        replace(capacities()[0],simulated_latency_ms=2000),
        replace(capacities()[0],participation_bps=1),
    ):
        r=audit_capacity_stress(a['snapshot'],depth=a['depth'],side='BUY',cases=(case,),fees=fee_scenario())
        assert not r.accepted and r.failed_scenarios==(case.name,)


def test_210_accepted_research_gate_always_no_go_for_live():
    a=all_valid();r=evaluate_execution_no_go_gate(**a)
    assert r.eligible_for_internal_synthetic_execution_review
    assert len(r.evidence_sha256)==64
    assert not (r.live_trading_authorized or r.autonomous_execution_authorized
                or r.strategy_promotion_authorized or r.real_market_liquidity_verified
                or r.historical_execution_verified or r.exchange_fee_schedule_verified)
    assert r==evaluate_execution_no_go_gate(**a)


@pytest.mark.parametrize('field,mutate',[
    ('depth',lambda r: replace(r,best_ask=Decimal('99.90'))),
    ('depth',lambda r: replace(r,live_trading_authorized=True)),
    ('fill',lambda r: replace(r,filled_quantity=100)),
    ('fill',lambda r: replace(r,live_trading_authorized=True)),
    ('fees',lambda r: replace(r,total_assumed_cost=Decimal(0))),
    ('fees',lambda r: replace(r,schedule_independently_verified=True)),
    ('capacity',lambda r: replace(r,passed_count=1)),
    ('capacity',lambda r: replace(r,real_market_capacity_verified=True)),
    ('data_readiness',lambda r: replace(r,real_historical_data_verified=True)),
    ('data_readiness',lambda r: replace(r,eligible_for_internal_manual_dataset_review=False)),
    ('data_readiness',lambda r: replace(r,linked_evidence_sha256='bad')),
])
def test_210_rejects_forged_or_promotion_evidence(field,mutate):
    a=all_valid(); a[field]=mutate(a[field]);r=evaluate_execution_no_go_gate(**a)
    assert not r.eligible_for_internal_synthetic_execution_review and r.blockers and not r.evidence_sha256


@pytest.mark.parametrize('mutation',[
    {'side':'SELL'}, {'quantity':151}, {'participation_bps':5000},
    {'latency_ms':21}, {'max_adverse_slippage_bps':99},
    {'fee_scenario':FeeScenario('21',10,1,1,1800,3,5)},
    {'cases':(CapacityCase('base',151,10000,20,100,200),)},
    {'contract_multiplier':2}, {'tick_size':'0.01'},
    {'max_age_ms':1}, {'max_spread_bps':1},
    {'live_requested':True}, {'autonomous_requested':True}, {'promotion_requested':True},
])
def test_210_changes_in_any_linked_assumption_fail(mutation):
    a=all_valid(); a.update(mutation)
    r=evaluate_execution_no_go_gate(**a)
    assert not r.eligible_for_internal_synthetic_execution_review and r.blockers


def test_210_requires_successful_all_capacity_cases():
    a=all_valid()
    cases=(replace(capacities()[0],order_quantity=500),)
    a['cases']=cases
    a['capacity']=audit_capacity_stress(a['snapshot'],depth=a['depth'],side=a['side'],
                                         cases=cases,fees=a['fee_scenario'])
    assert not evaluate_execution_no_go_gate(**a).eligible_for_internal_synthetic_execution_review


def test_210_capacity_must_include_primary_order():
    a=all_valid()
    cases=(CapacityCase('other-order', 250,10000,40,100,200),)
    a['cases']=cases
    a['capacity']=audit_capacity_stress(a['snapshot'],depth=a['depth'],side='BUY',
                                         cases=cases,fees=a['fee_scenario'])
    assert a['capacity'].accepted
    r=evaluate_execution_no_go_gate(**a)
    assert not r.eligible_for_internal_synthetic_execution_review
    assert 'Stage209 includes baseline scenario' in r.blockers
