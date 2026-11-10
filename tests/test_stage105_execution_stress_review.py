"""Stage105 bounded synthetic spread/slippage/participation tests."""
from dataclasses import replace, FrozenInstanceError
import pytest
from nexus_titan.operations.stage101_historical_bar_preflight import Stage101SyntheticBar, review_stage101_synthetic_window
from nexus_titan.operations.stage102_option_chain_preflight import Stage102SyntheticQuote, review_stage102_synthetic_chain
from nexus_titan.operations.stage104_historical_catalog_review import review_stage104_catalog
from nexus_titan.operations.stage105_execution_stress_review import Stage105Blocked, Stage105PaperIntent, preview_stage105_execution


def fixtures(volume=100):
    bars=[Stage101SyntheticBar('NIFTY',f'2026-11-10T09:{15+i:02d}:00+05:30',
            2500000,2500200,2499900,2500100,100) for i in range(3)]
    w=review_stage101_synthetic_window(bars)
    q=[Stage102SyntheticQuote(f'NIFTY-2026-11-12-{t}-2500000','NIFTY','2026-11-12',
             '2026-11-10T09:17:00+05:30',t,2500000,1000,1100,200,volume,25)
       for t in ('CE','PE')]
    cat=review_stage104_catalog([w])
    ch=review_stage102_synthetic_chain(w,q)
    intent=Stage105PaperIntent('sim-1',q[0].contract_id,'BUY',75,5000,100,10,10)
    return cat,w,ch,q,intent


def call(changes=None, index=None, **intent_changes):
    cat,w,ch,quotes,intent=fixtures()
    if changes:
        for k,v in changes.items():
            if k=='catalog':cat=v
            elif k=='window':w=v
            elif k=='chain':ch=v
            elif k=='quotes':quotes=v
    return preview_stage105_execution(cat,w,ch,quotes,replace(intent,**intent_changes))


def test_adverse_fill_in_integer_paise_and_partial():
    a=call()
    b=call()
    assert a==b and len(a.scenario_sha256)==64
    assert a.requested_quantity==75 and a.filled_quantity==50 and a.unfilled_quantity==25
    assert a.hypothetical_price_paise==1111
    assert a.hypothetical_gross_turnover_paise==55550
    assert a.hypothetical_fee_paise==76
    assert a.hypothetical_cash_delta_paise==-55626
    assert a.hypothetical_spread_impact_paise==3050
    assert a.statutory_charges_verified is False
    assert a.execution_liquidity_verified is False
    assert a.actual_fill_verified is False and a.trade_authorized is False
    assert a.live_trading_enabled is False


def test_sell_uses_bid_minus_adverse_slippage():
    a=call(side='SELL',requested_quantity=25,adverse_slippage_bps=100)
    assert a.filled_quantity==25 and a.hypothetical_price_paise==990
    assert a.hypothetical_cash_delta_paise>0
    assert a.hypothetical_spread_impact_paise>0


def test_no_volume_leaves_intent_unfilled_and_no_fake_execution():
    cat,w,ch,quotes,intent=fixtures(volume=0)
    a=preview_stage105_execution(cat,w,ch,quotes,intent)
    assert (a.filled_quantity,a.unfilled_quantity)==(0,75)
    assert a.hypothetical_price_paise is None
    assert a.hypothetical_fee_paise==a.hypothetical_cash_delta_paise==0


def test_quota_never_fills_nonlot_fraction():
    a=call(max_volume_participation_bps=2500)
    assert a.filled_quantity==25 and a.unfilled_quantity==50


def test_zero_slippage_still_uses_cross_spread():
    a=call(adverse_slippage_bps=0)
    assert a.hypothetical_price_paise==1100
    assert a.hypothetical_spread_impact_paise==2500


@pytest.mark.parametrize('changes',[
    dict(request_id='bad/path'),dict(request_id=''),dict(request_id=None),
    dict(contract_id='NOPE'),dict(side='SHORT'),dict(side=True),
    dict(requested_quantity=0),dict(requested_quantity=1),dict(requested_quantity=True),
    dict(requested_quantity=25.0),dict(requested_quantity=100001),
    dict(max_volume_participation_bps=0),dict(max_volume_participation_bps=10001),
    dict(max_volume_participation_bps=True),
    dict(adverse_slippage_bps=-1),dict(adverse_slippage_bps=1001),
    dict(estimated_fee_bps=-1),dict(estimated_fee_bps=1001),
    dict(estimated_fixed_fee_paise_per_lot=-1),
    dict(estimated_fixed_fee_paise_per_lot=1000001),
    dict(source='NSE'),dict(live_trading_enabled=True),dict(human_authorization_verified=True),
])
def test_bad_intents_fail_closed(changes):
    with pytest.raises(Stage105Blocked):call(**changes)


@pytest.mark.parametrize('changes', [
    dict(currency='USDT'),dict(symbol='BANKNIFTY'),dict(independent_data_provider_verified=True),
    dict(complete_trading_calendar_verified=True),dict(historical_15y_coverage_verified=True),
    dict(strategy_signal_authorized=True),dict(live_trading_enabled=True),dict(verdict='READY'),
    dict(source_window_hashes=()),dict(first_date='2027-01-01'),
])
def test_catalog_tampering_rejected(changes):
    c,w,ch,q,i=fixtures()
    with pytest.raises(Stage105Blocked):preview_stage105_execution(replace(c,**changes),w,ch,q,i)


@pytest.mark.parametrize('changes', [
    dict(chain_sha256='bad'),dict(quote_count=500),dict(live_trading_enabled=True),
    dict(executable_liquidity_verified=True),dict(official_option_chain_verified=True),
    dict(official_expiry_calendar_verified=True),dict(broker_order_authorized=True),
    dict(currency='USDT'),dict(source_window_sha256='0'*64),dict(verdict='READY'),
])
def test_chain_tampering_rejected(changes):
    c,w,ch,q,i=fixtures()
    with pytest.raises(Stage105Blocked):preview_stage105_execution(c,w,replace(ch,**changes),q,i)


def test_changed_quote_replay_fails():
    c,w,ch,q,i=fixtures()
    bad=list(q)
    bad[0]=replace(bad[0],ask_paise=1101)
    with pytest.raises(Stage105Blocked):preview_stage105_execution(c,w,ch,bad,i)


def test_unordered_quote_replay_digest_is_rejected():
    c,w,ch,q,i=fixtures()
    with pytest.raises(Stage105Blocked):preview_stage105_execution(c,w,ch,list(reversed(q)),i)


def test_broken_window_must_fail():
    c,w,ch,q,i=fixtures()
    with pytest.raises(Stage105Blocked):preview_stage105_execution(c,replace(w,symbol='BANKNIFTY'),ch,q,i)


def test_no_trading_authority_from_immutable_preview():
    with pytest.raises(FrozenInstanceError):call().trade_authorized=True
