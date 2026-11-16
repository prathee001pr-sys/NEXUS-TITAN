"""Bounded contract tests. Not a substitute for testing the full GitHub repo."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nexus_titan.operations.crypto_research_preflight import (
    CryptoResearchPreflightBlocked, preflight_crypto_research
)


class Bag:
    def __init__(self, **kw): self.__dict__.update(kw)

class Pipeline:
    def __init__(self, result): self.result = result; self.calls = 0
    def evaluate(self, state, proposals, risk_request):
        self.calls += 1
        return self.result

class Book:
    def __init__(self):
        self.account_id = 'crypto-local'
        self.calls = 0
        self.limits = Bag(paper_enabled=True, mode='SAFE', max_order_cents=100000, max_quote_age_seconds=30)
        self.state = Bag(market='CRYPTO_PAPER',currency='USDT',account_id=self.account_id,
            live_trading_enabled=False, exchange_orders_transmitted=0,real_market_evidence_verified=False,
            kill_active=False,journal_revision=0,journal_tip='0'*64,cash_cents=200000,
            remaining_cost_basis_cents=0,initial_cents=200000,realized_net_pnl_cents=0,position_microcoin=0)
    def snapshot(self): self.calls += 1; return self.state
    def apply(self, *args, **kwargs): raise AssertionError('Never execute')


def fixture():
    state=Bag(quality=Bag(valid=True,stale=False),symbol='BTC-USDT',exchange='CRYPTO_SYNTHETIC',provenance={'source_id':'LOCAL_SYNTHETIC_TEST_ONLY'},event_time=datetime.fromtimestamp(100,timezone.utc),ingest_time=datetime.fromtimestamp(101,timezone.utc))
    intent=Bag(source='LOCAL_SYNTHETIC_TEST_ONLY',symbol='BTC-USDT',side='BUY',observed_epoch=100,
        quantity_microcoin=10000, price_cents_per_coin=5000000)
    risk=Bag(symbol='BTC-USDT',side='BUY')
    result=Bag(status='SHADOW CANDIDATE',risk_approved=True,order_submitted=False,risk_quantity=1,
        consensus=Bag(action='BUY'))
    return dict(pipeline=Pipeline(result),state=state,proposals=[Bag(action='BUY')],risk_request=risk,intent=intent,book=Book(),now_epoch=101)


def test_readonly_happy_path():
    f=fixture();r=preflight_crypto_research(**f)
    assert r.status=='RESEARCH_ONLY_PRECHECK_NO_EXECUTION'
    assert r.action=='BUY' and r.journal_tip=='0'*64
    assert (r.paper_order_submitted,r.exchange_order_submitted,r.risk_permit_issued,r.authorized_for_paper_execution,r.live_trading_enabled,r.production_ready)==(False,)*6
    assert f['pipeline'].calls==1 and f['book'].calls==1

@pytest.mark.parametrize('where,attr,value',[
    ('state','symbol','NIFTY'),('state','exchange','BINANCE'),('state','provenance',{'source_id':'UNVERIFIED'}),
    ('intent','side','SHORT'),('intent','source','LIVE'),('intent','observed_epoch',500),
    ('intent','quantity_microcoin',0),('intent','quantity_microcoin',True),('intent','price_cents_per_coin',0),
    ('intent','quantity_microcoin',1000000),('risk_request','symbol','ETH-USDT'),('risk_request','side','SELL'),
    ('state','quality',Bag(valid=True,stale=True)),('state','quality',Bag(valid=False,stale=False)),
    ('result','status','RISK REJECTED'),('result','risk_approved',False),('result','risk_approved',1),
    ('result','order_submitted',True),('result','risk_quantity',0),('consensus','action','SELL'),
    ('limits','paper_enabled',False),('limits','max_quote_age_seconds',0),('limits','mode','AUTO'),
    ('account','live_trading_enabled',True),('account','exchange_orders_transmitted',1),
    ('account','real_market_evidence_verified',True),('account','currency','INR'),
    ('account','journal_tip','x'*64),('account','kill_active',True),('account','cash_cents',180000), ('account','cash_cents',True), ('account','cash_cents',None),
    ('account','realized_net_pnl_cents','-1'), ('account','position_microcoin',None),
    ('state','event_time',None), ('state','ingest_time',None),
    ('state','event_time',datetime.fromtimestamp(105,timezone.utc)),
    ('state','event_time',datetime.fromtimestamp(100)),
    ('state','ingest_time',datetime.fromtimestamp(99,timezone.utc)),
    ('state','ingest_time',datetime.fromtimestamp(104,timezone.utc)),
])
def test_fail_closed(where,attr,value):
    f=fixture()
    obj={'state':f['state'],'intent':f['intent'],'risk_request':f['risk_request'],
         'result':f['pipeline'].result,'consensus':f['pipeline'].result.consensus,
         'limits':f['book'].limits,'account':f['book'].state}[where]
    setattr(obj,attr,value)
    with pytest.raises(CryptoResearchPreflightBlocked):preflight_crypto_research(**f)

@pytest.mark.parametrize('now',[-1,True,131])
def test_bounded_stale_and_now(now):
    f=fixture();f['now_epoch']=now
    with pytest.raises(CryptoResearchPreflightBlocked):preflight_crypto_research(**f)


def test_insufficient_proposals_fail_closed():
    for proposals in ([], [None]*33):
        f=fixture();f['proposals']=proposals
        with pytest.raises(CryptoResearchPreflightBlocked):preflight_crypto_research(**f)


def test_sell_only_with_position_and_independent_side():
    f=fixture();f['intent'].side='SELL';f['risk_request'].side='SELL';f['pipeline'].result.consensus.action='SELL'
    f['book'].state.position_microcoin=10000
    r=preflight_crypto_research(**f)
    assert r.action=='SELL' and not r.authorized_for_paper_execution
    f['book'].state.position_microcoin=9999
    with pytest.raises(CryptoResearchPreflightBlocked):preflight_crypto_research(**f)
