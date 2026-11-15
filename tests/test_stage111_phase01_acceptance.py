"""Phase01 cross-stage controlled research fixture; excludes live authority."""
from dataclasses import replace, FrozenInstanceError
from hashlib import sha256
import pytest
from nexus_titan.operations.stage108_upgrade_compatibility import review_stage108_compatibility
from nexus_titan.operations.stage109_effective_dated_stt import (Stage109SyntheticTrade,Stage109OtherCharges,review_stage109_cost)
from nexus_titan.operations.stage110_deterministic_execution_replay import review_stage110_execution
from nexus_titan.operations.stage111_phase01_acceptance import (Stage111Blocked,Stage111ResearchProposal,review_stage111_phase01)
from test_stage108_upgrade_compatibility import valid
from test_stage110_deterministic_execution_replay import fixtures as replay_fixtures


def fixtures():
    c,e,r,adv=valid()
    comp=review_stage108_compatibility(c,e,r,adv)
    preview,intent,events=replay_fixtures()
    assert preview==e
    replay=review_stage110_execution(e,intent,events)
    costs=review_stage109_cost(Stage109SyntheticTrade(
        '2026-11-10','OPTION_PREMIUM','BUY',replay.filled_quantity,replay.modeled_turnover_paise))
    proposal=Stage111ResearchProposal('upgrade-phase01',sha256(b'candidate-code-untrusted').hexdigest(),comp.catalog_sha256,42)
    return comp,e,costs,replay,proposal


def check(override=None,**parts):
    c,e,t,r,p=fixtures()
    parts=dict(compatibility=c,execution_preview=e,costs=t,replay=r,proposal=p)|parts
    return review_stage111_phase01(**parts)


def test_cross_stage_conservation_and_immutable_no_go():
    x=check(); assert x==check()
    assert x.filled_quantity==25 and x.turnover_paise==27775
    assert x.modeled_total_charges_paise==0 and x.modeled_cash_delta_paise==-27775
    assert x.indian_currency=='INR' and x.crypto_currency=='USDT'
    assert x.verdict=='PHASE01_SYNTHETIC_INTEGRATION_ONLY_NO_GO'
    assert len(x.report_sha256)==64
    assert not any((x.independent_market_data_verified,x.real_market_execution_verified,
        x.independent_risk_veto_runtime_certified,x.exchange_fee_breakdown_verified,
        x.strategy_promotion_enabled,x.trade_authorized,x.live_trading_enabled))
    with pytest.raises(FrozenInstanceError):x.trade_authorized=True


def test_paper_fee_is_not_double_counted_from_stage105():
    _,e,_,_,_=fixtures()
    x=check()
    assert e.hypothetical_fee_paise != x.modeled_total_charges_paise


def test_zero_fill_cost_allowed_but_not_authentic():
    c,e,t,r,p=fixtures()
    r=replace(r,filled_quantity=0,unfilled_quantity=50,modeled_turnover_paise=0,fill_count=0)
    t=review_stage109_cost(Stage109SyntheticTrade('2026-11-10','OPTION_PREMIUM','BUY',0,0))
    x=check(costs=t,replay=r)
    assert x.modeled_cash_delta_paise==0 and x.trade_authorized is False


def test_hypothetical_fees_reduce_cash_not_increase():
    c,e,t,r,p=fixtures()
    tr=Stage109SyntheticTrade('2026-11-10','OPTION_PREMIUM','BUY',r.filled_quantity,r.modeled_turnover_paise)
    more=review_stage109_cost(tr,Stage109OtherCharges(brokerage_paise=25,gst_paise=5))
    x=check(costs=more)
    assert x.modeled_cash_delta_paise==-r.modeled_turnover_paise-30
    assert x.report_sha256!=check().report_sha256


@pytest.mark.parametrize('part,change',[
 ('compatibility',{'symbol':'BANKNIFTY'}),('compatibility',{'india_currency':'USDT'}),
 ('compatibility',{'crypto_currency':'INR'}),('compatibility',{'catalog_sha256':'0'*64}),
 ('compatibility',{'execution_sha256':'0'*64}),('compatibility',{'compatibility_sha256':'bad'}),
 ('compatibility',{'reference_names':()}),
 ('compatibility',{'duplicate_execution_engine_added':True}),
 ('compatibility',{'third_party_code_imported':True}),
 ('compatibility',{'independent_market_source_verified':True}),
 ('compatibility',{'risk_veto_runtime_certified':True}),
 ('compatibility',{'strategy_promotion_enabled':True}),
 ('compatibility',{'live_trading_enabled':True}),('compatibility',{'verdict':'GO'}),
 ('execution_preview',{'underlying':'BANKNIFTY'}),('execution_preview',{'actual_fill_verified':True}),
 ('execution_preview',{'trade_authorized':True}),('execution_preview',{'live_trading_enabled':True}),
 ('execution_preview',{'verdict':'READY'}),
 ('costs',{'quantity':50}),('costs',{'turnover_paise':100}),
 ('costs',{'instrument':'FUTURE'}),('costs',{'side':'SELL'}),
 ('costs',{'trading_date':'2026-11-09'}),
 ('costs',{'modeled_total_charges_paise':-1}),
 ('costs',{'modeled_total_charges_paise':100}),
 ('costs',{'modeled_stt_paise':999}),('costs',{'stt_rate_ppm':1500}),
 ('costs',{'taxable_value_paise':1}),('costs',{'rate_source':'UNKNOWN'}),
 ('costs',{'actual_broker_charges_verified':True}),
 ('costs',{'exchange_rounding_verified':True}),
 ('costs',{'trade_authorized':True}),('costs',{'live_trading_enabled':True}),
 ('costs',{'verdict':'READY'}),('costs',{'source_sha256':'bad'}),
 ('replay',{'filled_quantity':50}),('replay',{'unfilled_quantity':0}),
 ('replay',{'modeled_turnover_paise':1}),('replay',{'request_id':'other'}),
 ('replay',{'contract_id':'other'}),('replay',{'evidence_tier':'REAL_L2'}),
 ('replay',{'real_order_book_verified':True}),
 ('replay',{'real_exchange_fill_verified':True}),
 ('replay',{'independent_risk_veto_verified':True}),
 ('replay',{'trade_authorized':True}),('replay',{'live_trading_enabled':True}),
 ('replay',{'verdict':'READY'}),('replay',{'stage105_scenario_sha256':'0'*64}),
 ('replay',{'replay_sha256':'bad'}),
 ('proposal',{'experiment_id':'bad/experiment'}),('proposal',{'experiment_id':None}),
 ('proposal',{'dataset_sha256':'0'*64}),('proposal',{'proposed_code_sha256':'bad'}),
 ('proposal',{'fixed_seed':-1}),('proposal',{'fixed_seed':True}),
 ('proposal',{'fixed_seed':2**33}),('proposal',{'state':'APPROVED'}),
 ('proposal',{'source':'PUBLIC_INTERNET'}),
 ('proposal',{'autonomous_promotion_enabled':True}),
 ('proposal',{'live_trading_enabled':True}),
])
def test_tamper_rejected(part,change):
    c,e,t,r,p=fixtures()
    args=dict(compatibility=c,execution_preview=e,costs=t,replay=r,proposal=p)
    args[part]=replace(args[part],**change)
    with pytest.raises(Stage111Blocked):review_stage111_phase01(**args)


def test_typed_only_no_implicit_external_execution():
    for bad in [None,0,True,{},'live order']:
        with pytest.raises(Stage111Blocked):check(proposal=bad)


def test_single_entrypoint_reuses_existing_stage_responsibilities():
    from nexus_titan.operations.stage111_phase01_acceptance import review_stage111_pipeline
    from test_stage110_deterministic_execution_replay import fixtures as execution_inputs
    c,e,r,a=valid(); _,intent,events=execution_inputs()
    manifest=fixtures()[-1]
    direct=review_stage111_pipeline(c,e,r,a,intent,events,manifest)
    assert direct==check()
    assert direct.trade_authorized is False


def test_single_entrypoint_errors_fail_closed_without_order_submission():
    from nexus_titan.operations.stage111_phase01_acceptance import review_stage111_pipeline
    from nexus_titan.operations.stage110_deterministic_execution_replay import Stage110Blocked
    from test_stage110_deterministic_execution_replay import fixtures as execution_inputs
    c,e,r,a=valid();_,intent,events=execution_inputs()
    with pytest.raises(Stage110Blocked):
        review_stage111_pipeline(c,e,r,a,replace(intent,live_trading_enabled=True),events,fixtures()[-1])
    with pytest.raises(Stage111Blocked):
        review_stage111_pipeline(c,e,r,a,intent,events,replace(fixtures()[-1],state='APPROVED'))
