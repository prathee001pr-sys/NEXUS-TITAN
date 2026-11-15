"""Stages 196–200: offline-only integrated portfolio regression and bad-input tests."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from nexus_titan.data.stage190_e2e_paper_replay import E2EPaperReplayReceipt
from nexus_titan.data.stage191_portfolio_replay_ledger import ClosedReplay, audit_portfolio_replay_ledger
from nexus_titan.data.stage196_integrated_synthetic_audit import (
    SyntheticAuditPolicy, audit_integrated_synthetic_portfolio,
)
from nexus_titan.data.stage197_friction_scenario_grid import (
    FrictionScenario, audit_friction_scenario_grid,
)
from nexus_titan.data.stage198_replay_stability import audit_replay_stability
from nexus_titan.data.stage199_integrity_recheck import audit_integrated_integrity
from nexus_titan.data.stage200_synthetic_no_go_gate import evaluate_stage200_no_go

UTC = timezone.utc
START = datetime(2026, 11, 1, tzinfo=UTC)


def sample_trades():
    pnls = ('20', '-12', '18', '-4')
    days = (0, 1, 10, 11)
    return tuple(
        ClosedReplay('synthetic_' + str(i), START + timedelta(days=d),
                     E2EPaperReplayReceipt(True, Decimal(p), format(i + 11, '064x'), ()))
        for i, (d, p) in enumerate(zip(days, pnls))
    )


def policy(**overrides):
    values = dict(opening_equity='1000', max_drawdown_bps=9000,
                  extra_cost_per_roundtrip='2', max_acceptable_loss='100',
                  train_end=START + timedelta(days=2),
                  holdout_start=START + timedelta(days=5), config_sha256='d' * 64)
    values.update(overrides)
    return SyntheticAuditPolicy(**values)


def scenarios():
    return (FrictionScenario('base', '1', '100'),
            FrictionScenario('severe', '5', '100'))


def pipeline(t=None, p=None, **flags):
    values = dict(provenance_attested=True,
                  independent_risk_veto_attested=True,
                  holdout_separation_attested=True)
    values.update(flags)
    return audit_integrated_synthetic_portfolio(
        sample_trades() if t is None else t, policy=policy() if p is None else p, **values)


def evidence(t=None, p=None, s=None):
    t = sample_trades() if t is None else t
    p = policy() if p is None else p
    s = scenarios() if s is None else s
    verified = pipeline(t, p)
    friction = audit_friction_scenario_grid(t, s)
    replay = audit_replay_stability(t, ledger=audit_portfolio_replay_ledger(t))
    integrity = audit_integrated_integrity(
        t, policy=p, scenarios=s, pipeline=verified, friction=friction, replay=replay,
        provenance_attested=True, independent_risk_veto_attested=True,
        holdout_separation_attested=True)
    return integrity, verified, friction, replay


def stage200(t=None, p=None, s=None, **changes):
    t = sample_trades() if t is None else t
    p = policy() if p is None else p
    s = scenarios() if s is None else s
    integrity, *_ = evidence(t, p, s)
    settings = dict(provenance_attested=True, independent_risk_veto_attested=True,
                    holdout_separation_attested=True, independent_review_attested=True)
    settings.update(changes)
    return evaluate_stage200_no_go(t, policy=p, scenarios=s, evidence=integrity, **settings)


def test_stage196_pipeline_chain_has_bound_evidence():
    t = sample_trades()
    result = pipeline(t)
    assert result.accepted_for_synthetic_review and result.trade_count == 4
    assert len(result.evidence_sha256) == 64
    assert all(len(x) == 64 for x in (
        result.ledger_sha256, result.equity_sha256, result.cost_sha256, result.holdout_sha256))
    assert result == pipeline(t)
    assert (result.live_trading_authorized, result.autonomous_execution_authorized,
            result.strategy_promotion_authorized) == (False, False, False)


@pytest.mark.parametrize('key', [
    'provenance_attested', 'independent_risk_veto_attested', 'holdout_separation_attested',
])
def test_stage196_attestation_missing_fails_closed(key):
    r = pipeline(**{key: False})
    assert not r.accepted_for_synthetic_review and not r.evidence_sha256


@pytest.mark.parametrize('key', ['live_requested', 'autonomous_requested', 'promotion_requested'])
def test_stage196_forbidden_request_fails_closed(key):
    r = pipeline(**{key: True})
    assert not r.accepted_for_synthetic_review and not r.live_trading_authorized


@pytest.mark.parametrize('mutate', [
    lambda t: (t[0], t[0]) + t[2:],
    lambda t: (t[1], t[0]) + t[2:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, live_trading_authorized=True)),) + t[1:],
    lambda t: (replace(t[0], receipt=replace(t[0].receipt, replay_sha256='bogus')),) + t[1:],
])
def test_stage196_corrupted_receipts_are_rejected(mutate):
    assert not pipeline(mutate(sample_trades())).accepted_for_synthetic_review


def test_stage196_bad_drawdown_and_holdout_rejected():
    assert not pipeline(p=policy(max_drawdown_bps=1)).accepted_for_synthetic_review
    assert not pipeline(p=policy(holdout_start=START + timedelta(days=20))).accepted_for_synthetic_review
    assert not pipeline(p=policy(extra_cost_per_roundtrip='9999')).accepted_for_synthetic_review
    assert not pipeline(p=None, live_requested=1).accepted_for_synthetic_review


def test_stage197_friction_scenarios_worst_net():
    r = audit_friction_scenario_grid(sample_trades(), scenarios())
    assert r.accepted and r.worst_stressed_net_pnl == Decimal('2')
    assert len(r.scenario_sha256) == 64
    assert r == audit_friction_scenario_grid(sample_trades(), scenarios())


@pytest.mark.parametrize('cases', [
    (), (FrictionScenario('one','1','100'),),
    (FrictionScenario('dup','1','100'), FrictionScenario('dup','2','100')),
    (FrictionScenario('bad name','1','100'), FrictionScenario('ok','2','100')),
    (FrictionScenario('low','1','100'), FrictionScenario('huge','99999','10')),
    (FrictionScenario('low','-1','100'), FrictionScenario('ok','2','100')),
])
def test_stage197_invalid_cost_scenarios_blocked(cases):
    assert not audit_friction_scenario_grid(sample_trades(), cases).accepted


def test_stage198_timezone_normalized_replay_is_stable():
    t = sample_trades()
    ledger = audit_portfolio_replay_ledger(t)
    r = audit_replay_stability(t, ledger=ledger)
    assert r.accepted and len(r.replay_stability_sha256) == 64
    offset = timezone(timedelta(hours=5, minutes=30))
    shifted = tuple(replace(row, closed_at=row.closed_at.astimezone(offset)) for row in t)
    assert audit_replay_stability(shifted, ledger=ledger) == r


def test_stage198_tampered_ledger_is_blocked():
    t = sample_trades()
    ledger = audit_portfolio_replay_ledger(t)
    assert not audit_replay_stability(t, ledger=replace(ledger, net_pnl=Decimal('999'))).accepted


def test_stage199_checks_original_records_not_only_hash_shape():
    integrity, integrated, friction, replay = evidence()
    assert integrity.accepted and len(integrity.evidence_sha256) == 64
    r = audit_integrated_integrity(
        sample_trades(), policy=policy(), scenarios=scenarios(),
        pipeline=replace(integrated, evidence_sha256='0'*64), friction=friction, replay=replay,
        provenance_attested=True, independent_risk_veto_attested=True,
        holdout_separation_attested=True)
    assert not r.accepted and not r.evidence_sha256


def test_stage199_tampered_friction_and_replay_rejected():
    integrity, pipeline_receipt, friction, replay = evidence()
    for fr, rp in ((replace(friction, scenario_sha256='f'*64), replay),
                   (friction, replace(replay, replay_stability_sha256='e'*64))):
        r = audit_integrated_integrity(
            sample_trades(), policy=policy(), scenarios=scenarios(),
            pipeline=pipeline_receipt, friction=fr, replay=rp,
            provenance_attested=True, independent_risk_veto_attested=True,
            holdout_separation_attested=True)
        assert not r.accepted


def test_stage200_all_pass_is_still_offline_only():
    r = stage200()
    assert r.eligible_for_offline_synthetic_review
    assert len(r.synthetic_evidence_sha256) == 64
    assert (r.live_trading_authorized, r.autonomous_execution_authorized,
            r.strategy_promotion_authorized) == (False, False, False)
    assert r == stage200()


@pytest.mark.parametrize('key', [
    'live_requested', 'autonomous_requested', 'promotion_requested',
])
def test_stage200_forbidden_authorization_never_succeeds(key):
    r = stage200(**{key: True})
    assert not r.eligible_for_offline_synthetic_review
    assert not r.live_trading_authorized


def test_stage200_independent_review_mandatory():
    assert not stage200(independent_review_attested=False).eligible_for_offline_synthetic_review


def test_stage200_rejects_forged_integrity_receipt():
    t = sample_trades()
    passed, *_ = evidence()
    forged = replace(passed, evidence_sha256='0'*64)
    result = evaluate_stage200_no_go(
        t, policy=policy(), scenarios=scenarios(), evidence=forged,
        provenance_attested=True, independent_risk_veto_attested=True,
        holdout_separation_attested=True, independent_review_attested=True)
    assert not result.eligible_for_offline_synthetic_review


def test_stage190_through_stage200_real_synthetic_module_chain():
    """Uses actual Stage 186–190 APIs, not only fabricated Stage 190 receipts."""
    from nexus_titan.data.stage185_derivatives_review_gate import DerivativesReviewReceipt
    from nexus_titan.data.stage186_quote_tape import TapeQuote, audit_quote_tape
    from nexus_titan.data.stage187_causal_signal import SignalIntent
    from nexus_titan.data.stage188_synthetic_fill import SyntheticFillEvent
    from nexus_titan.data.stage190_e2e_paper_replay import replay_synthetic_roundtrip

    contract = 'NIFTY:2026-11-26:CE:24000'
    trades = []
    # Actual full-module E2E for four separate chronologically closed roundtrips.
    for i, day in enumerate((0, 1, 10, 11)):
        t = datetime(2026, 11, 1 + day, 9, tzinfo=UTC)
        dataset = format(1000 + i, '064x')
        exit_bid, exit_ask = ('110', '111') if i % 2 == 0 else ('94', '95')
        quotes = (
            TapeQuote('q1', t, t + timedelta(milliseconds=100), '99', '100', 10, 10),
            TapeQuote('q2', t + timedelta(seconds=10),
                      t + timedelta(seconds=10, milliseconds=100), exit_bid, exit_ask, 10, 10),
        )
        tape = audit_quote_tape(quotes, contract_id=contract, dataset_sha256=dataset)
        assert tape.accepted
        entry = SignalIntent('buy', contract, dataset, tape.tape_sha256, 'q1',
                             t + timedelta(milliseconds=200), 'BUY', 2, 100)
        exit_signal = SignalIntent('sell', contract, dataset, tape.tape_sha256, 'q2',
                                   t + timedelta(seconds=10, milliseconds=200), 'SELL', 2, 100)
        replay = replay_synthetic_roundtrip(
            quotes=quotes, contract_id=contract, dataset_sha256=dataset,
            entry_signal=entry, exit_signal=exit_signal,
            entry_fills=(SyntheticFillEvent(f'entry_{i}', 'buy',
                                            t + timedelta(milliseconds=300), 2, '100'),),
            exit_fills=(SyntheticFillEvent(f'exit_{i}', 'sell',
                                           t + timedelta(seconds=10, milliseconds=300),
                                           2, exit_bid),),
            contract_multiplier=1, entry_fees='1', exit_fees='1',
            independent_review=DerivativesReviewReceipt(True, (), False, False, False),
            source_independently_verified=True,
            contract_independently_verified=True,
            fee_schedule_independently_verified=True,
            risk_veto_independently_verified=True)
        assert replay.accepted_for_offline_paper_review
        trades.append(ClosedReplay('end_to_end_' + str(i), t + timedelta(hours=1), replay))

    trades = tuple(trades)
    integrated = pipeline(trades)
    assert integrated.accepted_for_synthetic_review
    frictions = audit_friction_scenario_grid(trades, scenarios())
    assert frictions.accepted
    stable = audit_replay_stability(trades, ledger=audit_portfolio_replay_ledger(trades))
    assert stable.accepted
    integrity = audit_integrated_integrity(
        trades, policy=policy(), scenarios=scenarios(), pipeline=integrated,
        friction=frictions, replay=stable, provenance_attested=True,
        independent_risk_veto_attested=True, holdout_separation_attested=True)
    assert integrity.accepted
    assert evaluate_stage200_no_go(
        trades, policy=policy(), scenarios=scenarios(), evidence=integrity,
        provenance_attested=True, independent_risk_veto_attested=True,
        holdout_separation_attested=True,
        independent_review_attested=True).eligible_for_offline_synthetic_review


def test_stage190_duplicate_fill_event_rejected_before_stage196_admission():
    """Real Stage 190 fails closed on duplicate entry/exit event IDs."""
    from nexus_titan.data.stage185_derivatives_review_gate import DerivativesReviewReceipt
    from nexus_titan.data.stage186_quote_tape import TapeQuote, audit_quote_tape
    from nexus_titan.data.stage187_causal_signal import SignalIntent
    from nexus_titan.data.stage188_synthetic_fill import SyntheticFillEvent
    from nexus_titan.data.stage190_e2e_paper_replay import replay_synthetic_roundtrip

    t = datetime(2026, 11, 12, 9, tzinfo=UTC)
    contract = 'NIFTY:2026-11-26:CE:24000'
    dataset = 'a' * 64
    quotes = (
        TapeQuote('q1', t, t + timedelta(milliseconds=100), '99', '100', 10, 10),
        TapeQuote('q2', t + timedelta(seconds=10), t + timedelta(seconds=10, milliseconds=100),
                  '110', '111', 10, 10),
    )
    tape = audit_quote_tape(quotes, contract_id=contract, dataset_sha256=dataset)
    entry = SignalIntent('buy', contract, dataset, tape.tape_sha256, 'q1',
                         t + timedelta(milliseconds=200), 'BUY', 2, 100)
    exit_signal = SignalIntent('sell', contract, dataset, tape.tape_sha256, 'q2',
                               t + timedelta(seconds=10, milliseconds=200), 'SELL', 2, 100)
    result = replay_synthetic_roundtrip(
        quotes=quotes, contract_id=contract, dataset_sha256=dataset,
        entry_signal=entry, exit_signal=exit_signal,
        entry_fills=(SyntheticFillEvent('duplicate', 'buy',
                                        t + timedelta(milliseconds=300), 2, '100'),),
        exit_fills=(SyntheticFillEvent('duplicate', 'sell',
                                       t + timedelta(seconds=10, milliseconds=300), 2, '110'),),
        contract_multiplier=1, entry_fees='1', exit_fees='1',
        independent_review=DerivativesReviewReceipt(True, (), False, False, False),
        source_independently_verified=True, contract_independently_verified=True,
        fee_schedule_independently_verified=True,
        risk_veto_independently_verified=True)
    assert not result.accepted_for_offline_paper_review
    assert not audit_portfolio_replay_ledger((
        ClosedReplay('tampered', t + timedelta(hours=1), result),
    )).accepted
