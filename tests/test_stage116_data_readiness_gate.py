from dataclasses import replace,FrozenInstanceError
import pytest
from nexus_titan.operations.stage116_data_readiness_gate import (Stage116Blocked,review_stage116_pipeline)
from test_stage111_phase01_acceptance import check as stage111_checked_fixture
from phase02_fixtures import base,csv_payload,DAY,manifest


def arguments():
    items,master,m,raw,data,clock,session=base()
    p=stage111_checked_fixture()
    assert p.symbol==master.underlying
    return dict(predecessor=p,contracts=items,trading_date=DAY,manifest=m,
                raw_bytes=raw,clock=clock,session=session)


def test_integrated_stage111_to_stage116_never_promotes():
    x=review_stage116_pipeline(**arguments())
    assert x==review_stage116_pipeline(**arguments())
    assert x.underlying=='NIFTY' and x.selected_quote_count==2
    assert x.single_chunk_coverage_complete and x.missing_quote_minutes==0
    assert len(x.phase02_sha256)==64
    assert x.verdict=='PHASE02_UNVERIFIED_DATA_FOUNDATION_ONLY_NO_GO'
    assert not any((x.data_rights_verified,x.licensed_market_data_verified,
        x.official_contract_calendar_verified,x.fifteen_year_coverage_verified,
        x.real_quote_liquidity_verified,x.strategy_promotion_enabled,
        x.trade_authorized,x.live_trading_enabled))
    with pytest.raises(FrozenInstanceError):x.trade_authorized=True


def test_missing_market_data_does_not_claim_pass():
    raw=csv_payload(drops=(('CE',1),))
    x=arguments()
    x['raw_bytes']=raw;x['manifest']=manifest(raw)
    r=review_stage116_pipeline(**x)
    assert not r.single_chunk_coverage_complete and r.missing_quote_minutes==1
    assert not r.trade_authorized and r.verdict.endswith('NO_GO')


def test_local_unverified_external_source_still_not_authentic():
    x=arguments()
    x['manifest']=replace(x['manifest'],source_kind='LOCAL_UNVERIFIED_FILE',rights_status='RIGHTS_UNVERIFIED')
    r=review_stage116_pipeline(**x)
    assert r.source_kind=='LOCAL_UNVERIFIED_FILE'
    assert r.single_chunk_coverage_complete
    assert not r.data_rights_verified and not r.licensed_market_data_verified

@pytest.mark.parametrize('key,mut',[
 ('predecessor',{'independent_market_data_verified':True}),
 ('predecessor',{'real_market_execution_verified':True}),
 ('predecessor',{'independent_risk_veto_runtime_certified':True}),
 ('predecessor',{'exchange_fee_breakdown_verified':True}),
 ('predecessor',{'strategy_promotion_enabled':True}),
 ('predecessor',{'trade_authorized':True}),
 ('predecessor',{'live_trading_enabled':True}),
 ('predecessor',{'verdict':'READY'}),
 ('predecessor',{'symbol':'BANKNIFTY'}),
 ('predecessor',{'indian_currency':'USD'}),
 ('predecessor',{'crypto_currency':'INR'}),
 ('predecessor',{'stage108_sha256':'broken'}),
 ('predecessor',{'report_sha256':'broken'}),
 ('manifest',{'independently_authenticated':True}),
 ('manifest',{'rights_status':'LICENSED'}),
 ('manifest',{'raw_sha256':'f'*64}),
 ('manifest',{'live_trading_enabled':True}),
 ('clock',{'live_trading_enabled':True}),
 ('clock',{'decision_at_ist':f'{DAY}T09:40:00+05:30'}),
 ('session',{'official_calendar_verified':True}),
 ('session',{'live_trading_enabled':True}),
])
def test_fail_closed_on_authority_and_lineage_tamper(key,mut):
    x=arguments();x[key]=replace(x[key],**mut)
    with pytest.raises(Stage116Blocked):review_stage116_pipeline(**x)


def test_incorrect_contract_or_date_rejected():
    x=arguments();x['trading_date']='2026-11-11'
    with pytest.raises(Stage116Blocked):review_stage116_pipeline(**x)


def test_tampered_csv_direct_bytes_fails_sha():
    x=arguments()
    x['raw_bytes']+=b'\n'
    with pytest.raises(Stage116Blocked):review_stage116_pipeline(**x)


def test_unsafe_input_type_rejected():
    x=arguments();x['raw_bytes']=bytearray(x['raw_bytes'])
    with pytest.raises(Stage116Blocked):review_stage116_pipeline(**x)
