import math
from decimal import Decimal
import pytest
from nexus_titan.operations.stage129_contract_guard import review_contract
from nexus_titan.operations.stage130_greeks_iv import estimate_option,implied_volatility
from nexus_titan.operations.stage131_cost_margin import estimate_cost_margin
from nexus_titan.operations.stage132_fo_research_gate import review_fo_research

@pytest.mark.parametrize('u,e,k,s,asof,valid',[
 ('NIFTY','2026-11-26',25000,'CE','2026-11-11',True),
 ('BANKNIFTY','2026-11-26',50000,'PE','2026-11-11',True),
 ('NIFTY','2026-11-01',25000,'CE','2026-11-11',False),
 ('SENSEX','2026-11-26',25000,'CE','2026-11-11',False),
 ('NIFTY','2026-11-26',0,'CE','2026-11-11',False),
 ('NIFTY','2026-11-26',25000,'XX','2026-11-11',False),
 ('NIFTY','bad',25000,'CE','2026-11-11',False),
 ('NIFTY','2026-11-26',float('nan'),'CE','2026-11-11',False),
])
def test_contract(u,e,k,s,asof,valid):
    x=review_contract(u,e,k,s,as_of=asof); assert x.valid is valid; assert not x.trading_approved

def test_put_call_parity():
    kw=dict(spot=100.,strike=105.,years=.5,volatility=.25,rate=.05)
    c=estimate_option(**kw,side='CE'); p=estimate_option(**kw,side='PE')
    assert c.price-p.price==pytest.approx(100-105*math.exp(-.05*.5),abs=1e-9)
    assert c.delta-p.delta==pytest.approx(1,abs=1e-9)
    assert c.gamma==pytest.approx(p.gamma)
    assert not c.trading_approved

@pytest.mark.parametrize('side', ['CE','PE'])
def test_iv_roundtrip(side):
    kw=dict(spot=100.,strike=105.,years=.5,rate=.05,side=side)
    target=estimate_option(**kw,volatility=.27).price
    assert implied_volatility(**kw,market_price=target)==pytest.approx(.27,abs=1e-5)

@pytest.mark.parametrize('bad', [0,-1,float('nan'),float('inf')])
def test_bad_spot(bad):
    with pytest.raises(ValueError): estimate_option(spot=bad,strike=100,years=.5,volatility=.2,rate=.05,side='CE')

def test_iv_impossible():
    with pytest.raises(ValueError): implied_volatility(market_price=200,spot=100,strike=100,years=1,rate=.05,side='CE')

def test_cost_exact_and_insufficient():
    x=estimate_cost_margin(premium='120',quantity=50,capital='100',brokerage='20',other_fees='3.10',slippage_per_unit='0.5',margin_requirement='1000')
    assert x.estimated_total_cost==Decimal('48.10')
    assert x.margin_required==Decimal('1048.10')
    assert not x.sufficient_capital and not x.live_trading_enabled

@pytest.mark.parametrize('quantity',[0,-1,1.5,True])
def test_bad_quantity(quantity):
    with pytest.raises(ValueError): estimate_cost_margin(premium=1,quantity=quantity,capital=100,brokerage=1,other_fees=1,slippage_per_unit=1,margin_requirement=10)

def test_integration_fail_closed():
    kw=dict(underlying='NIFTY',expiry='2026-11-26',strike=25000,side='CE',as_of='2026-11-11',spot=25100,years=.04,volatility=.2,rate=.06,premium=200,quantity=50,capital=50000,brokerage=20,other_fees=10,slippage_per_unit=1,margin_requirement=20000)
    ok=review_fo_research(**kw)
    assert ok.contract.valid and ok.estimate and ok.costs
    assert ok.verdict=='RESEARCH_ONLY_NO_GO'
    assert not ok.live_trading_enabled and not ok.paper_trading_approved and not ok.historical_backtest_approved
    bad=review_fo_research(**{**kw,'expiry':'2026-01-01'})
    assert bad.estimate is None and 'EXPIRED_CONTRACT' in bad.reasons
