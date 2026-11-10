"""Stage107 explicit synthetic adversarial matrix; never security certification."""
from dataclasses import replace, FrozenInstanceError
from hashlib import sha256
import pytest
from nexus_titan.operations.stage106_holdout_research_gate import review_stage106_holdout
from nexus_titan.operations.stage107_adversarial_assurance_review import (
    Stage107Blocked, Stage107SyntheticNegativeCase, SCENARIOS, review_stage107_adversarial,
)
from test_stage106_holdout_research_gate import fixtures as previous_fixtures


def fixtures():
    train,holdout,assurance,execution,obs=previous_fixtures()
    research=review_stage106_holdout('candidate-106',train,holdout,assurance,execution,obs)
    scenarios=[Stage107SyntheticNegativeCase(s,True,sha256(s.encode()).hexdigest()) for s in sorted(SCENARIOS)]
    return assurance,holdout,execution,research,scenarios


def check(assurance=None,catalog=None,execution=None,research=None,cases=None):
    a,c,e,r,s=fixtures()
    return review_stage107_adversarial(a if assurance is None else assurance,
        c if catalog is None else catalog,e if execution is None else execution,
        r if research is None else research,s if cases is None else cases)


def test_declared_fixture_review_never_grants_real_permission():
    r=check()
    assert r==check() and len(r.review_sha256)==64
    assert r.negative_scenarios==tuple(sorted(SCENARIOS))
    assert r.synthetic_negative_case_count==7
    assert r.india_currency=='INR' and r.crypto_currency=='USDT'
    for flag in ('actual_independent_veto_verified','production_risk_policy_certified',
        'market_source_verified','real_security_audit_completed','shadow_trading_verified',
        'live_trading_enabled','automated_promotion_approved'):
        assert getattr(r,flag) is False
    assert r.verdict=='DECLARED_SYNTHETIC_NEGATIVE_FIXTURES_ONLY_NO_GO'


def test_fingerprint_changes_with_negative_fixture():
    a,c,e,r,s=fixtures()
    old=check()
    s[0]=replace(s[0], fixture_sha256='e'*64)
    assert review_stage107_adversarial(a,c,e,r,s).review_sha256!=old.review_sha256


@pytest.mark.parametrize('mutation', [
    dict(scenario='UNKNOWN'),dict(scenario=None),dict(rejection_observed=False),
    dict(rejection_observed=1),dict(rejection_observed=None),
    dict(fixture_sha256='bad'),dict(fixture_sha256='A'*64),
    dict(source='REAL_NSE'),dict(source=''),
])
def test_invalid_scenario_gates(mutation):
    a,c,e,r,s=fixtures()
    s[0]=replace(s[0],**mutation)
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,c,e,r,s)


def test_missing_duplicate_and_unordered_cases():
    a,c,e,r,s=fixtures()
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,c,e,r,s[:-1])
    s[-1]=s[0]
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,c,e,r,s)
    assert review_stage107_adversarial(a,c,e,r,list(reversed(fixtures()[-1]))).review_sha256==check().review_sha256


@pytest.mark.parametrize('change', [
    dict(underlying='BANKNIFTY'),dict(indian_currency='USDT'),dict(crypto_currency='INR'),
    dict(synthetic_inputs_consistent=False),dict(source_authenticity_verified=True),
    dict(real_market_shadow_verified=True),dict(trade_authorized=True),
    dict(live_trading_enabled=True),dict(verdict='READY'),dict(review_sha256='bad'),
])
def test_assurance_tamper_rejected(change):
    a,c,e,r,s=fixtures()
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(replace(a,**change),c,e,r,s)


@pytest.mark.parametrize('change', [
    dict(symbol='BANKNIFTY'),dict(currency='USDT'),dict(independent_data_provider_verified=True),
    dict(complete_trading_calendar_verified=True),dict(historical_15y_coverage_verified=True),
    dict(strategy_signal_authorized=True),dict(live_trading_enabled=True),
    dict(verdict='READY'),dict(catalog_sha256='0'*64),
])
def test_catalog_tamper_rejected(change):
    a,c,e,r,s=fixtures()
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,replace(c,**change),e,r,s)


@pytest.mark.parametrize('change', [
    dict(currency='USDT'),dict(catalog_sha256='0'*64),dict(chain_sha256='0'*64),
    dict(window_sha256='0'*64),dict(trade_authorized=True),dict(actual_fill_verified=True),
    dict(live_trading_enabled=True),dict(verdict='READY'),dict(scenario_sha256='bad'),
])
def test_execution_tamper_rejected(change):
    a,c,e,r,s=fixtures()
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,c,replace(e,**change),r,s)


@pytest.mark.parametrize('change', [
    dict(symbol='BANKNIFTY'),dict(currency='USDT'),dict(holdout_catalog_sha256='0'*64),
    dict(stage103_review_sha256='0'*64),dict(stage105_scenario_sha256='0'*64),
    dict(real_accuracy_verified=True),dict(autonomous_strategy_promotion=True),
    dict(live_trading_enabled=True),dict(verdict='READY'),dict(evidence_sha256='bad'),
])
def test_research_tamper_rejected(change):
    a,c,e,r,s=fixtures()
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,c,e,replace(r,**change),s)


@pytest.mark.parametrize('cases', [None,{},'cases',[1],list(range(8))])
def test_invalid_collection_types_rejected(cases):
    a,c,e,r,_=fixtures()
    with pytest.raises(Stage107Blocked):review_stage107_adversarial(a,c,e,r,cases)


def test_frozen_report():
    with pytest.raises(FrozenInstanceError):check().live_trading_enabled=True
