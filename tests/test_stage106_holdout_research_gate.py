"""Synthetic-only chronological research/OOS negative guards."""
from dataclasses import replace, FrozenInstanceError
import pytest
from nexus_titan.operations.stage101_historical_bar_preflight import Stage101SyntheticBar, review_stage101_synthetic_window
from nexus_titan.operations.stage102_option_chain_preflight import Stage102SyntheticQuote, review_stage102_synthetic_chain
from nexus_titan.operations.stage103_readonly_assurance_gate import verify_stage103_readonly_assurance
from nexus_titan.operations.stage104_historical_catalog_review import review_stage104_catalog
from nexus_titan.operations.stage105_execution_stress_review import Stage105PaperIntent, preview_stage105_execution
from nexus_titan.operations.stage106_holdout_research_gate import (
    Stage106Blocked, Stage106SyntheticObservation, review_stage106_holdout,
)
from test_stage103_readonly_assurance_gate import fixtures as prior_fixtures


def bars(day: str, n: int = 6):
    return review_stage101_synthetic_window([Stage101SyntheticBar('NIFTY',
        f'{day}T09:{15+i:02d}:00+05:30',2500000,2500200,2499900,2500100,100)
        for i in range(n)])


def fixtures():
    fo,_,_,dual=prior_fixtures()
    train=review_stage104_catalog([bars('2026-11-09')])
    window=bars('2026-11-10')
    holdout=review_stage104_catalog([window])
    quotes=[Stage102SyntheticQuote(f'NIFTY-2026-11-12-{kind}-2500000','NIFTY','2026-11-12',
        '2026-11-10T09:20:00+05:30',kind,2500000,1000,1100,100,100,25)
        for kind in ('CE','PE')]
    chain=review_stage102_synthetic_chain(window,quotes)
    assure=verify_stage103_readonly_assurance(fo,window,chain,dual)
    intent=Stage105PaperIntent('research-106',quotes[0].contract_id,'BUY',50,10000,100,10)
    execs=preview_stage105_execution(holdout,window,chain,quotes,intent)
    obs=[Stage106SyntheticObservation('2026-11-10T09:16:00+05:30','2026-11-10T09:17:00+05:30',1,1),
         Stage106SyntheticObservation('2026-11-10T09:18:00+05:30','2026-11-10T09:19:00+05:30',-1,1)]
    return train,holdout,assure,execs,obs


def check(train=None, holdout=None, assurance=None, execution=None, obs=None, experiment='candidate-106'):
    tr,ho,asr,exe,ob=fixtures()
    return review_stage106_holdout(experiment, tr if train is None else train,
        ho if holdout is None else holdout, asr if assurance is None else assurance,
        exe if execution is None else execution, ob if obs is None else obs)


def test_nominal_synthetic_holdout_remains_no_go():
    r=check()
    assert r==check() and len(r.evidence_sha256)==64
    assert r.observation_count==2 and r.illustrative_direction_matches==1
    assert r.lookahead_window_overlap is False
    assert r.out_of_sample_market_evidence_verified is False
    assert r.real_accuracy_verified is False and r.autonomous_strategy_promotion is False
    assert r.live_trading_enabled is False


def test_no_leakage_with_reversed_labels():
    tr,ho,a,e,o=fixtures()
    with pytest.raises(Stage106Blocked):check(obs=list(reversed(o)))


@pytest.mark.parametrize('changes', [
    dict(source='NSE'),dict(predicted_direction=2),dict(predicted_direction=True),
    dict(synthetic_observed_direction=-2),dict(synthetic_observed_direction=False),
    dict(forecast_at_ist='2026-11-10T09:16:00Z'),
    dict(forecast_at_ist='2026-11-10T09:16:00'),
    dict(forecast_at_ist='2026-11-10T09:16:01+05:30'),
    dict(forecast_at_ist='2026-11-10T09:13:00+05:30'),
    dict(forecast_at_ist='2026-11-10T09:19:00+05:30'),
    dict(outcome_known_at_ist='2026-11-10T09:16:00+05:30'),
    dict(outcome_known_at_ist='2026-11-10T09:22:00+05:30'),
    dict(outcome_known_at_ist='2026-11-11T09:17:00+05:30'),
])
def test_forecast_label_failure_closed(changes):
    tr,ho,a,e,o=fixtures()
    o[0]=replace(o[0],**changes)
    with pytest.raises(Stage106Blocked):check(obs=o)


@pytest.mark.parametrize('changes', [
    dict(symbol='BANKNIFTY'),dict(currency='USDT'),dict(complete_trading_calendar_verified=True),
    dict(independent_data_provider_verified=True),dict(historical_15y_coverage_verified=True),
    dict(strategy_signal_authorized=True),dict(live_trading_enabled=True),dict(verdict='READY'),
    dict(catalog_sha256='bad'),dict(session_count=True),dict(session_count=2),
])
def test_training_provenance_tamper(changes):
    tr,ho,a,e,o=fixtures()
    with pytest.raises(Stage106Blocked):check(train=replace(tr,**changes))


def test_train_holdout_reuse_rejected():
    tr,ho,a,e,o=fixtures()
    with pytest.raises(Stage106Blocked):check(train=ho)


def test_out_of_order_training_date_rejected():
    tr,ho,a,e,o=fixtures()
    with pytest.raises(Stage106Blocked):check(train=replace(tr,last_date='2026-11-10'))


@pytest.mark.parametrize('changes', [
    dict(currency='USDT'),dict(catalog_sha256='0'*64),dict(window_sha256='0'*64),
    dict(chain_sha256='0'*64),dict(actual_fill_verified=True),
    dict(execution_liquidity_verified=True),dict(statutory_charges_verified=True),
    dict(trade_authorized=True),dict(live_trading_enabled=True),dict(verdict='READY'),
    dict(source_last_asof_ist='2026-11-10T09:17:00+05:30'),
])
def test_execution_tamper(changes):
    tr,ho,a,e,o=fixtures()
    with pytest.raises(Stage106Blocked):check(execution=replace(e,**changes))


@pytest.mark.parametrize('changes', [
    dict(source_authenticity_verified=True),dict(trade_authorized=True),
    dict(real_market_shadow_verified=True),dict(live_trading_enabled=True),
    dict(synthetic_inputs_consistent=False),dict(verdict='READY'),dict(review_sha256='bad'),
])
def test_assurance_tamper(changes):
    tr,ho,a,e,o=fixtures()
    with pytest.raises(Stage106Blocked):check(assurance=replace(a,**changes))


@pytest.mark.parametrize('obs', [[],[5],list(range(101))])
def test_observation_type_and_bound(obs):
    with pytest.raises(Stage106Blocked):check(obs=obs)


def test_explicit_none_observations_fail():
    tr,ho,a,e,_=fixtures()
    with pytest.raises(Stage106Blocked):review_stage106_holdout('candidate-106',tr,ho,a,e,None)


@pytest.mark.parametrize('experiment', ['',None,'bad/id'])
def test_bad_experiment_id(experiment):
    with pytest.raises(Stage106Blocked):check(experiment=experiment)


def test_no_unauthorized_mutation_of_research_verdict():
    with pytest.raises(FrozenInstanceError):check().autonomous_strategy_promotion=True
