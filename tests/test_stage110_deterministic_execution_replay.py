"""Synthetic L1 quote replay: stronger safety assumptions than a bar-only fill."""
from dataclasses import replace, FrozenInstanceError
from datetime import datetime
import pytest
from nexus_titan.operations.stage110_deterministic_execution_replay import (
    Stage110Blocked,Stage110ReplayIntent,Stage110BookUpdate,Stage110OrderEvent,
    review_stage110_execution)
from test_stage108_upgrade_compatibility import valid


def ms(clock):
    return int(datetime.fromisoformat('2026-11-10T'+clock+'+05:30').timestamp()*1000)


def fixtures():
    _,e,_,_=valid()
    assert e.filled_quantity==50
    i=Stage110ReplayIntent(e.request_id,e.contract_id,'BUY',50,25,ms('09:17:00'),1300)
    q=Stage110BookUpdate('book-1',ms('09:17:00'),1000,1100,50,50)
    f=Stage110OrderEvent('fill-1',ms('09:17:01'),'FILL',25,1111)
    return e,i,[q,f]


def check(preview=None,intent=None,events=None):
    e,i,ev=fixtures()
    return review_stage110_execution(e if preview is None else preview,
                                     i if intent is None else intent,
                                     ev if events is None else events)


def test_partial_fill_cash_conservation_hash_and_no_permissions():
    r=check()
    assert r==check() and len(r.replay_sha256)==64
    assert r.requested_quantity==50 and r.filled_quantity==25 and r.unfilled_quantity==25
    assert r.modeled_turnover_paise==25*1111 and r.fill_count==1
    assert r.evidence_tier=='SYNTHETIC_L1'
    assert not any((r.real_order_book_verified,r.real_exchange_fill_verified,
                    r.independent_risk_veto_verified,r.trade_authorized,r.live_trading_enabled))
    with pytest.raises(FrozenInstanceError):r.trade_authorized=True


def test_deterministic_empty_and_cancelled_replay():
    e,i,events=fixtures()
    r=check(events=[events[0]])
    assert (r.filled_quantity,r.unfilled_quantity,r.modeled_turnover_paise,r.fill_count)==(0,50,0,0)
    r2=check(events=[*events,Stage110OrderEvent('cancel',ms('09:17:02'),'CANCEL')])
    assert r2.canceled and r2.filled_quantity==25
    assert r2.replay_sha256 != check().replay_sha256


def test_multiple_fills_cannot_reuse_visible_qty():
    e,i,events=fixtures()
    events.append(Stage110OrderEvent('fill-2',ms('09:17:03'),'FILL',25,1111))
    r=check(events=events)
    assert r.filled_quantity==50 and r.unfilled_quantity==0 and r.fill_count==2
    events.append(Stage110OrderEvent('fill-3',ms('09:17:04'),'FILL',25,1111))
    with pytest.raises(Stage110Blocked):check(events=events)


@pytest.mark.parametrize('part,change',[
 ('intent',{'request_id':'not matched'}),('intent',{'request_id':None}),
 ('intent',{'contract_id':'BAD'}),('intent',{'contract_id':1}),
 ('intent',{'side':'SELL'}),('intent',{'quantity':25}),('intent',{'quantity':0}),
 ('intent',{'lot_size':3}),('intent',{'lot_size':0}),('intent',{'lot_size':True}),
 ('intent',{'submitted_at_ms':ms('09:14:59')}),
 ('intent',{'submitted_at_ms':ms('09:21:00')}),
 ('intent',{'submitted_at_ms':True}),
 ('intent',{'price_protection_paise':100}),('intent',{'price_protection_paise':0}),
 ('intent',{'max_quote_age_ms':0}),('intent',{'max_quote_age_ms':60001}),
 ('intent',{'source':'LIVE_FEED'}),('intent',{'live_trading_enabled':True}),
 ('preview',{'actual_fill_verified':True}),('preview',{'trade_authorized':True}),
 ('preview',{'live_trading_enabled':True}),('preview',{'verdict':'READY'}),
 ('preview',{'scenario_sha256':'bad'}),
 ('preview',{'requested_quantity':75}),('preview',{'filled_quantity':51}),
 ('preview',{'currency':'USDT'}),('preview',{'hypothetical_price_paise':1300}),
])
def test_invalid_lineage_or_intent_rejected(part,change):
    e,i,ev=fixtures()
    with pytest.raises(Stage110Blocked):
        check(preview=replace(e,**change) if part=='preview' else e,
              intent=replace(i,**change) if part=='intent' else i,
              events=ev)


@pytest.mark.parametrize('kind,change',[
 ('book',{'bid_paise':0}),('book',{'ask_paise':900}),
 ('book',{'bid_quantity':-1}),('book',{'ask_quantity':-1}),
 ('book',{'source':'EXCHANGE'}),('book',{'event_id':'bad/id'}),
 ('book',{'event_id':'fill-1'}),('book',{'at_ms':ms('09:16:59')}),
 ('fill',{'price_paise':1099}),('fill',{'price_paise':1301}),
 ('fill',{'quantity':24}),('fill',{'quantity':0}),('fill',{'quantity':75}),
 ('fill',{'source':'BROKER'}),('fill',{'event_id':'book-1'}),
 ('fill',{'at_ms':ms('09:16:59')}),
 ('fill',{'at_ms':ms('09:18:00')}),
 ('fill',{'at_ms':ms('09:21:00')}),
 ('fill',{'action':'EXECUTE_LIVE'}),
])
def test_bad_events_rejected(kind,change):
    e,i,ev=fixtures()
    n=0 if kind=='book' else 1
    ev[n]=replace(ev[n],**change)
    with pytest.raises(Stage110Blocked):check(preview=e,intent=i,events=ev)


def test_book_is_not_allowed_to_appear_after_fill_at_same_timestamp():
    e,i,ev=fixtures()
    ev=[Stage110OrderEvent('fill-premature',ms('09:17:00'),'FILL',25,1111),ev[0]]
    with pytest.raises(Stage110Blocked):check(events=ev)


def test_cancel_blocks_subsequent_fill():
    e,i,ev=fixtures()
    ev=[ev[0],Stage110OrderEvent('cancel-1',ms('09:17:00'),'CANCEL'),ev[1]]
    with pytest.raises(Stage110Blocked):check(events=ev)


def test_l1_not_automatically_exchange_verified_even_after_quote_refresh():
    e,i,ev=fixtures()
    ev.append(Stage110BookUpdate('book-2',ms('09:18:00'),1000,1100,100,100))
    ev.append(Stage110OrderEvent('fill-2',ms('09:18:01'),'FILL',25,1111))
    r=check(events=ev)
    assert r.filled_quantity==50 and r.real_exchange_fill_verified is False


def test_wrong_collection_type_rejected():
    e,i,ev=fixtures()
    for bad in [None,{},'evil',tuple(),range(2)]:
        with pytest.raises(Stage110Blocked):review_stage110_execution(e,i,bad)
