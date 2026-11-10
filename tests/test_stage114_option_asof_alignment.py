from dataclasses import replace,FrozenInstanceError
import pytest
from nexus_titan.operations.stage114_option_asof_alignment import (Stage114Blocked,Stage114Clock,review_stage114_asof)
from nexus_titan.operations.stage112_fo_contract_master import review_stage112_master
from nexus_titan.operations.stage113_fo_source_provenance import review_stage113_csv
from phase02_fixtures import base,csv_payload,manifest,DAY,contracts,spec


def test_asof_latest_explicit_no_go():
    _,master,m,raw,data,clock,session=base()
    x=review_stage114_asof(master,data,clock)
    assert x.selected_quote_count==2 and x.maximum_quote_age_seconds==0
    assert x.cross_contract_skew_seconds==0
    assert x==review_stage114_asof(master,data,clock)
    assert x.verdict.endswith('NO_GO') and not x.trade_authorized and not x.live_trading_enabled
    assert not x.market_quote_authenticity_verified and not x.independent_time_source_verified
    with pytest.raises(FrozenInstanceError):x.trade_authorized=True


def test_future_data_is_not_used_to_decide_past():
    items,master,m,raw,data,clock,session=base()
    original=review_stage114_asof(master,data,clock)
    later=[]
    for item in items:
        later.append(f'{item.contract_id},{DAY}T09:18:00+05:30,3000,3005,1,1')
    raw2=csv_payload(extras=later)
    ds2=review_stage113_csv(master,manifest(raw2),raw2)
    new=review_stage114_asof(master,ds2,clock)
    assert new.selected_quotes==original.selected_quotes
    assert new.maximum_quote_age_seconds==0
    assert new.dataset_sha256!=original.dataset_sha256

@pytest.mark.parametrize('clockmut',[
 {'decision_at_ist':f'{DAY}T09:20:00+05:30'},
 {'decision_at_ist':f'{DAY}T09:14:00+05:30'},
 {'decision_at_ist':f'{DAY}T09:17:01+05:30'},
 {'decision_at_ist':f'{DAY}T09:17:00+00:00'},
 {'decision_at_ist':'2026-11-11T09:17:00+05:30'},
 {'max_quote_age_seconds':-1},
 {'max_quote_age_seconds':181},
 {'max_quote_age_seconds':True},
 {'max_cross_contract_skew_seconds':-1},
 {'max_cross_contract_skew_seconds':181},
 {'max_cross_contract_skew_seconds':True},
 {'live_trading_enabled':True},
])
def test_time_or_authority_failure(clockmut):
    _,master,m,raw,data,clock,session=base()
    with pytest.raises(Stage114Blocked):review_stage114_asof(master,data,replace(clock,**clockmut))


def test_skew_failure_and_staleness():
    raw=csv_payload(drops=(('PE',2),))
    _,master,m,raw,data,clock,session=base(raw)
    with pytest.raises(Stage114Blocked):review_stage114_asof(master,data,replace(clock,max_cross_contract_skew_seconds=0))
    good=review_stage114_asof(master,data,clock)
    assert good.maximum_quote_age_seconds==60 and good.cross_contract_skew_seconds==60
    with pytest.raises(Stage114Blocked):review_stage114_asof(master,data,replace(clock,max_quote_age_seconds=59))


def test_missing_contract_as_of_cutoff():
    raw=csv_payload(drops=(('PE',0),))
    _,master,m,raw,data,clock,session=base(raw)
    with pytest.raises(Stage114Blocked):review_stage114_asof(master,data,replace(clock,decision_at_ist=f'{DAY}T09:15:00+05:30'))

@pytest.mark.parametrize('part,mutation',[
    ('master',{'master_sha256':'0'*64}),
    ('master',{'live_trading_enabled':True}),
    ('master',{'verdict':'READY'}),
    ('dataset',{'master_sha256':'0'*64}),
    ('dataset',{'live_trading_enabled':True}),
    ('dataset',{'quote_origin_verified':True}),
    ('dataset',{'provider_authenticated':True}),
    ('dataset',{'market_data_license_verified':True}),
    ('dataset',{'verdict':'READY'}),
])
def test_tampered_predecessor_rejected(part,mutation):
    _,master,m,raw,data,clock,session=base()
    args={'master':master,'dataset':data,'clock':clock}
    args[part]=replace(args[part],**mutation)
    with pytest.raises(Stage114Blocked):review_stage114_asof(**args)


def test_missing_ce_pe_pair_even_if_source_complete():
    x=spec('CE')
    master=review_stage112_master([x],trading_date=DAY)
    quotes=[f'{x.contract_id},{DAY}T09:17:00+05:30,1000,1005,20,100']
    raw=csv_payload(quotes=quotes)
    data=review_stage113_csv(master,manifest(raw),raw)
    with pytest.raises(Stage114Blocked):review_stage114_asof(master,data,Stage114Clock(f'{DAY}T09:17:00+05:30'))
