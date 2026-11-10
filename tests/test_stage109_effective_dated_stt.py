"""Official 2026 NSE rate transitions; estimated tax only, not full broker bill."""
from dataclasses import replace, FrozenInstanceError
import pytest
from nexus_titan.operations.stage109_effective_dated_stt import (
    Stage109Blocked,Stage109SyntheticTrade,Stage109OtherCharges,review_stage109_cost,SOURCE)


def base(**kw):
    return replace(Stage109SyntheticTrade('2026-11-10','OPTION_PREMIUM','SELL',25,1_000_000),**kw)


def test_post_2026_sell_15bps_and_zero_on_buy():
    r=review_stage109_cost(base())
    assert (r.stt_rate_ppm,r.modeled_stt_paise,r.taxable_value_paise)==(1500,1500,1_000_000)
    assert r.modeled_total_charges_paise==1500
    assert r.rate_source==SOURCE
    assert not r.actual_broker_charges_verified and not r.exchange_rounding_verified
    assert not r.live_trading_enabled and not r.trade_authorized and 'NO_GO' in r.verdict
    b=review_stage109_cost(base(side='BUY'))
    assert b.stt_rate_ppm==b.modeled_stt_paise==b.taxable_value_paise==0
    with pytest.raises(FrozenInstanceError):r.live_trading_enabled=True


@pytest.mark.parametrize('trade,rate,expected',[
  (Stage109SyntheticTrade('2026-03-31','OPTION_PREMIUM','SELL',25,1_000_000),1000,1000),
  (Stage109SyntheticTrade('2026-04-01','OPTION_PREMIUM','SELL',25,1_000_000),1500,1500),
  (Stage109SyntheticTrade('2026-03-31','OPTION_EXERCISE','EXERCISE',25,0,1_000_000),1250,1250),
  (Stage109SyntheticTrade('2026-04-01','OPTION_EXERCISE','EXERCISE',25,0,1_000_000),1500,1500),
  (Stage109SyntheticTrade('2026-03-31','FUTURE','SELL',25,1_000_000),200,200),
  (Stage109SyntheticTrade('2026-04-01','FUTURE','SELL',25,1_000_000),500,500),
  (Stage109SyntheticTrade('2026-04-01','FUTURE','BUY',25,1_000_000),0,0),
  (Stage109SyntheticTrade('2024-10-01','OPTION_PREMIUM','SELL',1,1_000_000),1000,1000),
])
def test_official_boundary(trade,rate,expected):
    r=review_stage109_cost(trade)
    assert r.stt_rate_ppm==rate and r.modeled_stt_paise==expected


def test_trade_paise_round_up_is_conservative_not_broker_assertion():
    r=review_stage109_cost(base(turnover_paise=1))
    assert r.modeled_stt_paise==1


def test_explicit_optional_charges_do_not_look_verified():
    other=Stage109OtherCharges(20,5,1,3,5)
    a=review_stage109_cost(base(),other)
    assert a.other_modeled_charges_paise==34
    assert a.modeled_total_charges_paise==a.modeled_stt_paise+34
    assert a==review_stage109_cost(base(),other)
    assert a.source_sha256!=review_stage109_cost(base()).source_sha256


@pytest.mark.parametrize('change',[
    {'trading_date':'2024-09-30'},{'trading_date':'2026-02-30'},
    {'trading_date':'2026-4-1'},{'trading_date':'2026-11-10T00:00:00'},
    {'trading_date':None},{'instrument':'STOCK'},{'side':'EXERCISE'},
    {'side':'SHORT'},{'quantity':-1},{'quantity':True},{'quantity':100001},
    {'turnover_paise':-1},{'turnover_paise':True},
    {'turnover_paise':10**13},{'intrinsic_value_paise':1},
    {'source':'REAL_NSE'},{'quantity':0},{'turnover_paise':0},
])
def test_invalid_trade_rejected(change):
    with pytest.raises(Stage109Blocked):review_stage109_cost(base(**change))


@pytest.mark.parametrize('change',[
 {'side':'BUY'},{'side':'SELL'},{'turnover_paise':1},
 {'intrinsic_value_paise':0},{'intrinsic_value_paise':-1},
 {'quantity':0},{'instrument':'OPTION_PREMIUM'},
])
def test_invalid_exercise_rejected(change):
    trade=Stage109SyntheticTrade('2026-11-10','OPTION_EXERCISE','EXERCISE',25,0,1_000_000)
    with pytest.raises(Stage109Blocked):review_stage109_cost(replace(trade,**change))


@pytest.mark.parametrize('change',[
  {'brokerage_paise':-1},{'exchange_paise':True},{'sebi_paise':float('nan')},
  {'stamp_paise':100_000_001},{'gst_paise':-1},
  {'source':'OFFICIAL_NSE'},{'gst_paise':10**14},
])
def test_unverified_extra_cost_rejected(change):
    with pytest.raises(Stage109Blocked):review_stage109_cost(base(),replace(Stage109OtherCharges(),**change))


def test_zero_fill_no_fee_even_if_brokerage_configured():
    z=base(side='BUY',quantity=0,turnover_paise=0)
    assert review_stage109_cost(z).modeled_total_charges_paise==0
    with pytest.raises(Stage109Blocked):review_stage109_cost(z,Stage109OtherCharges(brokerage_paise=100))
