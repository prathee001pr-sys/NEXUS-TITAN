from dataclasses import replace,FrozenInstanceError
from hashlib import sha256
import pytest
from nexus_titan.operations.stage112_fo_contract_master import (Stage112Blocked, Stage112Contract,review_stage112_master)
from phase02_fixtures import contracts, spec, future, DAY


def test_master_determinism_sorted_and_no_go():
    x=review_stage112_master(contracts(),trading_date=DAY)
    assert x==review_stage112_master(list(reversed(contracts())),trading_date=DAY)
    assert x.underlying=='NIFTY' and x.contract_count==2 and x.currency=='INR'
    assert len(x.master_sha256)==64 and not x.live_trading_enabled
    assert not x.official_contract_master_verified and not x.official_lot_history_verified
    assert x.verdict.endswith('NO_GO')
    with pytest.raises(FrozenInstanceError):x.live_trading_enabled=True


def test_future_valid_and_contract_immutability():
    x=review_stage112_master((*contracts(),future()),trading_date=DAY)
    assert x.contract_count==3
    with pytest.raises(FrozenInstanceError):x.contracts[0].lot_size=100

@pytest.mark.parametrize('mut',[
    {'underlying':'BTC'}, {'instrument':'STOCK'},
    {'option_type':'NA'},{'option_type':'XX'}, {'expiry_date':'invalid'},
    {'expiry_date':'2026-11-09'},{'effective_from':'2026-11-11'},
    {'effective_through':'2026-11-09'}, {'effective_through':'2026-10-01'},
    {'strike_paise':0},{'strike_paise':-1},{'strike_paise':True},
    {'lot_size':0},{'lot_size':True},{'lot_size':100001},
    {'tick_size_paise':0},{'tick_size_paise':True},{'tick_size_paise':100001},
    {'contract_id':'bad/path'},{'contract_id':'../escape'},
    {'contract_id':''},{'contract_id':'z'*200},
    {'currency':'USDT'},{'source':'BROKER_VERIFIED'},
    {'live_trading_enabled':True},
])
def test_bad_contract_fails_closed(mut):
    with pytest.raises(Stage112Blocked):review_stage112_master((replace(spec('CE'),**mut),),trading_date=DAY)

@pytest.mark.parametrize('date', ['2026-11-10Z','2026-11-7','2026-02-30','1800-01-01',
                                      '2026/11/10',None,True])
def test_incorrect_or_nontrading_date_rejected(date):
    with pytest.raises(Stage112Blocked):review_stage112_master(contracts(),trading_date=date)

@pytest.mark.parametrize('case', ['duplicate_id','duplicate_side','mixed_symbol','non_type','empty','long'])
def test_catalog_cross_row_invariants(case):
    x=list(contracts())
    if case=='duplicate_id': x.append(replace(x[0]))
    elif case=='duplicate_side': x.append(replace(x[0],contract_id='another-id'))
    elif case=='mixed_symbol': x.append(replace(spec('CE'),contract_id='new',underlying='BANKNIFTY'))
    elif case=='non_type': x[0]=dict(x=1)
    elif case=='empty':x=[]
    elif case=='long':x=x*101
    with pytest.raises(Stage112Blocked):review_stage112_master(x,trading_date=DAY)

@pytest.mark.parametrize('future_mut', [{'option_type':'CE'}, {'strike_paise':10}, {'lot_size':0}])
def test_future_no_options_features(future_mut):
    with pytest.raises(Stage112Blocked):review_stage112_master([replace(future(),**future_mut)],trading_date=DAY)


def test_weekend_special_session_unverified_not_misclassified():
    result=review_stage112_master(contracts(),trading_date='2026-11-14')
    assert not result.exchange_expiry_verified
    assert result.verdict.endswith('NO_GO')
