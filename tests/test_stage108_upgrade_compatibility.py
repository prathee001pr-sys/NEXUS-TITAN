"""Stage108 real predecessor-chain compatibility checks, no synthetic certificates."""
from dataclasses import replace, FrozenInstanceError
import pytest
from nexus_titan.operations.stage107_adversarial_assurance_review import review_stage107_adversarial
from nexus_titan.operations.stage108_upgrade_compatibility import (
    review_stage108_compatibility, Stage108Blocked)
from test_stage107_adversarial_assurance_review import fixtures


def valid():
    a,c,e,r,cases = fixtures()
    return c,e,r,review_stage107_adversarial(a,c,e,r,cases)


def test_linked_receipt_is_readonly_and_deterministic():
    values = valid()
    x = review_stage108_compatibility(*values)
    assert x == review_stage108_compatibility(*values)
    assert len(x.reference_names) == 6
    assert len(x.compatibility_sha256) == 64
    assert x.symbol == 'NIFTY' and x.india_currency == 'INR' and x.crypto_currency == 'USDT'
    assert x.verdict.endswith('NO_GO')
    assert not any([x.third_party_code_imported,x.independent_market_source_verified,
                    x.risk_veto_runtime_certified,x.live_trading_enabled,
                    x.strategy_promotion_enabled])
    with pytest.raises(FrozenInstanceError):x.live_trading_enabled=True


@pytest.mark.parametrize('part,change', [
    (0,{'symbol':'BANKNIFTY'}),(0,{'currency':'USDT'}),
    (0,{'independent_data_provider_verified':True}),(0,{'complete_trading_calendar_verified':True}),
    (0,{'historical_15y_coverage_verified':True}),(0,{'strategy_signal_authorized':True}),
    (0,{'live_trading_enabled':True}),(0,{'verdict':'READY'}),
    (0,{'catalog_sha256':'0'*64}),
    (1,{'currency':'USDT'}),(1,{'actual_fill_verified':True}),
    (1,{'statutory_charges_verified':True}),(1,{'execution_liquidity_verified':True}),
    (1,{'trade_authorized':True}),(1,{'live_trading_enabled':True}),
    (1,{'verdict':'READY'}),(1,{'catalog_sha256':'a'*64}),
    (1,{'scenario_sha256':'broken'}),
    (2,{'symbol':'BANKNIFTY'}),(2,{'lookahead_window_overlap':True}),
    (2,{'real_accuracy_verified':True}),(2,{'autonomous_strategy_promotion':True}),
    (2,{'out_of_sample_market_evidence_verified':True}),
    (2,{'live_trading_enabled':True}),(2,{'verdict':'READY'}),
    (2,{'evidence_sha256':'broken'}),
    (3,{'actual_independent_veto_verified':True}),
    (3,{'production_risk_policy_certified':True}),(3,{'market_source_verified':True}),
    (3,{'real_security_audit_completed':True}),(3,{'shadow_trading_verified':True}),
    (3,{'live_trading_enabled':True}),(3,{'automated_promotion_approved':True}),
    (3,{'verdict':'GO'}),(3,{'synthetic_negative_case_count':0}),
    (3,{'negative_scenarios':()}),(3,{'review_sha256':'short'}),
    (3,{'stage104_sha256':'0'*64}),(3,{'stage105_sha256':'0'*64}),
    (3,{'stage106_sha256':'0'*64}),(3,{'stage103_sha256':'0'*64}),
])
def test_tamper_is_blocked(part,change):
    args=list(valid());args[part]=replace(args[part],**change)
    with pytest.raises(Stage108Blocked):review_stage108_compatibility(*args)

@pytest.mark.parametrize('bad', [None,{},'fake',0,True])
def test_wrong_predecessor_type(bad):
    args=list(valid());args[3]=bad
    with pytest.raises(Stage108Blocked):review_stage108_compatibility(*args)
