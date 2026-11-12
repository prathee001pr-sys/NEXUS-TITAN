from datetime import date, datetime, timedelta, timezone
import pytest
from nexus_titan.data.stage161_coverage_metrics import assess_coverage
from nexus_titan.data.stage162_fo_chain_consistency import audit_contract_chain
from nexus_titan.data.stage163_cost_assumptions import audit_costs
from nexus_titan.data.stage164_split_embargo import audit_split
from nexus_titan.data.stage165_research_release_gate import evaluate_research_gate

T=datetime(2026,11,12,3,45,tzinfo=timezone.utc)
C={'symbol':'NIFTY','instrument':'OPT','expiry':date(2026,11,19),'strike':25000.0,'option_type':'CE','lot_size':65}

def test_coverage_complete():
    assert assess_coverage((T,T+timedelta(minutes=1)),(T,T+timedelta(minutes=1))).complete

def test_coverage_missing():
    r=assess_coverage((T,T+timedelta(minutes=1)),(T,))
    assert not r.complete and r.missing==1

def test_coverage_duplicate():
    assert assess_coverage((T,),(T,T)).duplicates==1

def test_coverage_reject_bad_expected():
    with pytest.raises(ValueError): assess_coverage((T,T), (T,))

def test_chain_good():
    assert audit_contract_chain((C,),asof=date(2026,11,12)).accepted

def test_chain_duplicate():
    assert not audit_contract_chain((C,C),asof=date(2026,11,12)).accepted

def test_chain_bad():
    assert not audit_contract_chain(({'symbol':'NIFTY'},),asof=date(2026,11,12)).accepted

def test_costs_valid():
    assert audit_costs(brokerage_bps=1,taxes_bps=2,spread_bps=3,slippage_bps=4).total_bps==10

@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-1,True])
def test_costs_invalid(bad):
    assert not audit_costs(brokerage_bps=bad,taxes_bps=1,spread_bps=1,slippage_bps=1).accepted

def test_split_valid():
    assert audit_split(train_end=T,test_start=T+timedelta(minutes=2),embargo_minutes=1).accepted

def test_split_overlap():
    assert not audit_split(train_end=T,test_start=T+timedelta(minutes=1),embargo_minutes=1).accepted

def test_research_gate_fail_closed():
    c=assess_coverage((T,),(T,)); chain=audit_contract_chain((C,),asof=date(2026,11,12))
    cost=audit_costs(brokerage_bps=1,taxes_bps=1,spread_bps=1,slippage_bps=1)
    split=audit_split(train_end=T,test_start=T+timedelta(minutes=2),embargo_minutes=1)
    assert evaluate_research_gate(coverage=c,chain=chain,costs=cost,split=split,source_verified=True).accepted_for_offline_research
    assert not evaluate_research_gate(coverage=c,chain=chain,costs=cost,split=split,source_verified=True,live_requested=True).accepted_for_offline_research
