import pytest
from nexus_titan.operations.stage133_fill_simulator import simulate_limit
from nexus_titan.operations.stage134_execution_costs import estimate_paper_costs
from nexus_titan.operations.stage135_fill_reconciliation import reconcile_paper
from nexus_titan.operations.stage136_execution_safety_gate import evaluate_execution_research

def test_fill():
    x=simulate_limit(side='BUY',quantity=10,limit_price=101,bid=99,ask=100,bid_size=10,ask_size=4)
    assert (x.status,x.filled,x.remaining)==('PARTIAL',4,6)

def test_sell():
    x=simulate_limit(side='SELL',quantity=3,limit_price=98,bid=99,ask=100,bid_size=5,ask_size=5)
    assert (x.status,x.filled)==('FILLED',3)

def test_not_crossed():
    assert simulate_limit(side='BUY',quantity=3,limit_price=99,bid=99,ask=100,bid_size=5,ask_size=5).filled==0

def test_zero_liquidity():
    assert simulate_limit(side='BUY',quantity=3,limit_price=101,bid=99,ask=100,bid_size=5,ask_size=0).status=='UNFILLED'

@pytest.mark.parametrize('change', [{'bid':102},{'slippage':-1},{'quantity':0},{'ask':float('nan')},{'bid_size':-1},{'side':'SHORT'},{'limit_price':float('inf')}])
def test_reject_quote(change):
    kw=dict(side='BUY',quantity=3,limit_price=101,bid=99,ask=100,bid_size=5,ask_size=5,slippage=0)
    kw.update(change)
    with pytest.raises(ValueError): simulate_limit(**kw)

def test_costs():
    c=estimate_paper_costs(quantity=10,price=100,brokerage_flat=20,fee_rate=.001)
    assert c.total_cost==21 and not c.assumptions_verified

@pytest.mark.parametrize('change',[{'fee_rate':-1},{'fee_rate':float('nan')},{'quantity':0},{'price':0},{'fee_rate':1.1}])
def test_reject_cost(change):
    kw=dict(quantity=10,price=100,brokerage_flat=20,fee_rate=.001);kw.update(change)
    with pytest.raises(ValueError): estimate_paper_costs(**kw)

def test_reconcile():
    r=reconcile_paper(order_quantity=10,events=(('a',3,100),('b',2,102)))
    assert (r.total_filled,r.remaining,r.weighted_price)==(5,5,100.8)

@pytest.mark.parametrize('events',[(('a',3,100),('a',1,100)),(('a',11,100),),(('a',0,100),),(('a',2,float('inf')),),(('',2,100),)])
def test_reject_events(events):
    with pytest.raises(ValueError): reconcile_paper(order_quantity=10,events=events)

def test_gate_fail_closed():
    g=evaluate_execution_research(side='BUY',quantity=10,limit_price=101,bid=99,ask=100,bid_size=5,ask_size=4,slippage=0,brokerage_flat=10,fee_rate=.001)
    assert g.fill.filled==4 and g.reconciliation.remaining==6
    assert g.verdict=='RESEARCH_ONLY_NO_GO' and not g.live_trading_enabled and not g.broker_order_authorized and not g.paper_execution_authorized

def test_gate_unfilled():
    g=evaluate_execution_research(side='BUY',quantity=10,limit_price=99,bid=99,ask=100,bid_size=5,ask_size=4,slippage=0,brokerage_flat=10,fee_rate=.001)
    assert g.costs is None and g.reconciliation.total_filled==0
