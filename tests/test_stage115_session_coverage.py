from dataclasses import replace,FrozenInstanceError
import pytest
from nexus_titan.operations.stage115_session_coverage import (Stage115Blocked, Stage115Session,review_stage115_coverage)
from phase02_fixtures import base,csv_payload,DAY


def test_full_chunk_not_15year_verified():
    _,master,m,raw,data,clock,session=base()
    x=review_stage115_coverage(master,data,session)
    assert x.expected_quote_minutes==6 and x.actual_in_session_quote_minutes==6
    assert x.missing_quote_minutes==0 and x.outside_session_rows==0
    assert x.chunk_coverage_complete and not x.fifteen_year_minute_coverage_verified
    assert not x.official_calendar_verified and not x.independent_data_provider_verified
    assert x.verdict.endswith('NO_GO') and x==review_stage115_coverage(master,data,session)
    with pytest.raises(FrozenInstanceError):x.live_trading_enabled=True


def test_missing_minute_is_reported_not_ignored():
    raw=csv_payload(drops=(('CE',1),))
    _,master,m,raw,data,clock,session=base(raw)
    r=review_stage115_coverage(master,data,session)
    assert r.expected_quote_minutes==6 and r.actual_in_session_quote_minutes==5
    assert r.missing_quote_minutes==1 and r.outside_session_rows==0
    assert not r.chunk_coverage_complete
    assert len(r.sample_missing)==1 and '09:16:00+05:30' in r.sample_missing[0]


def test_extra_after_exclusive_close_reported():
    items,master,m,raw,data,clock,session=base()
    extra=f'{items[0].contract_id},{DAY}T09:18:00+05:30,1000,1005,1,2'
    from nexus_titan.operations.stage113_fo_source_provenance import review_stage113_csv
    from phase02_fixtures import manifest
    raw=csv_payload(extras=[extra])
    data=review_stage113_csv(master,manifest(raw),raw)
    r=review_stage115_coverage(master,data,session)
    assert r.outside_session_rows==1 and not r.chunk_coverage_complete

@pytest.mark.parametrize('mut',[
 {'trading_date':'2026-11-09'},
 {'trading_date':'bad'},
 {'expected_open_ist':f'{DAY}T09:18:00+05:30'},
 {'expected_open_ist':f'{DAY}T09:19:00+05:30'},
 {'expected_open_ist':f'{DAY}T09:15:01+05:30'},
 {'expected_open_ist':f'{DAY}T09:15:00+00:00'},
 {'expected_close_ist':f'{DAY}T09:15:00+05:30'},
 {'expected_close_ist':'2026-11-11T09:18:00+05:30'},
 {'calendar_source':'NSE_VERIFIED'},
 {'official_calendar_verified':True},
 {'live_trading_enabled':True},
])
def test_calendar_boundary_fail_closed(mut):
    _,master,m,raw,data,clock,session=base()
    with pytest.raises(Stage115Blocked):review_stage115_coverage(master,data,replace(session,**mut))

@pytest.mark.parametrize('part,mut',[
 ('master',{'master_sha256':'b'*64}),
 ('master',{'live_trading_enabled':True}),
 ('master',{'official_contract_master_verified':True}),
 ('master',{'exchange_expiry_verified':True}),
 ('dataset',{'master_sha256':'b'*64}),
 ('dataset',{'verdict':'READY'}),
 ('dataset',{'live_trading_enabled':True}),
 ('dataset',{'provider_authenticated':True}),
 ('dataset',{'market_data_license_verified':True}),
 ('dataset',{'quote_origin_verified':True}),
])
def test_source_relation_fail_closed(part,mut):
    _,master,m,raw,data,clock,session=base()
    kw={'master':master,'dataset':data,'session':session}
    kw[part]=replace(kw[part],**mut)
    with pytest.raises(Stage115Blocked):review_stage115_coverage(**kw)
