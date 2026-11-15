"""Connected synthetic CSV -> analysis -> research -> risk -> ledger -> report."""
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import os
import runpy
import sqlite3

import pytest

from nexus_titan.evolve.governance import GovernedEvolveService
from nexus_titan.intelligence.consensus import SignalProposal
from nexus_titan.intelligence.pipeline import PipelineStatus, RiskRequest
from nexus_titan.operations.fo_risk_boundary import SyntheticFOOperation, SyntheticFORiskBlocked
from nexus_titan.operations.isolated_atomic_execution_book import Stage55SyntheticBookBlocked, _hash_event
from nexus_titan.operations.release_security_audit import inspect_stage52_security_sources
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import inspect_stage76_fo_portfolio_risk
from nexus_titan.operations.stage83_fo_capital_reconciliation import inspect_stage83_fo_account_reconciliation
from nexus_titan.operations.synthetic_fo_execution import SyntheticFOExecutionGateway
from nexus_titan.operations.synthetic_fo_research import assess_synthetic_fo_research

ROOT = Path(__file__).resolve().parents[1]
helper = runpy.run_path(str(ROOT/'tests/helpers/fo_synthetic_fixture.py'))
environment, opening, issue, reopen = (helper[k] for k in ('environment','opening','issue','reopen'))


def assessment(env, market, *, age=0, conflict=False):
    c = env['chains'][market]
    snapshot = env['book'].snapshot_local_synthetic_portfolio()
    proposals = tuple(SignalProposal(
        role, 'SELL' if conflict and i else 'BUY',
        'Explicit fabricated engineering drill, no alpha claim', digest,
        'Stop this synthetic drill if source/risk gates fail',
    ) for i,(role,digest) in enumerate((
        ('synthetic-regime', c['71'].input_alignment_sha256),
        ('synthetic-options', c['72'].research_output_sha256),
    )))
    request = RiskRequest(
        capital=snapshot.initial_cents/100, entry_price=5.50,stop_price=5.0,
        symbol=c['75'].option_symbol,side='BUY',lot_size=c['contract'].lot_size,
        current_exposure=(snapshot.initial_cents-snapshot.cash_cents+snapshot.reserved_cents)/100,
        current_open_positions=sum(o.filled_quantity>0 or o.open_hold_cents>0 for o in snapshot.orders),
    )
    return assess_synthetic_fo_research(
        futures=c['futures'],aligned=c['71'],options=c['72'],evolve=c['73'],
        proposals=proposals,risk_request=request,
        now=datetime.fromtimestamp(env['clock'][0]+age,timezone.utc),
    )


def warm_env(tmp_path):
    return environment(tmp_path,history_bars=40,option_start_minute=35)


def test_both_synthetic_csv_chains_reach_assessment_capital_execution_reconciliation_report(tmp_path):
    env = warm_env(tmp_path)
    gateway = SyntheticFOExecutionGateway(env['book'])
    for market in ('NIFTY','BANKNIFTY'):
        c = env['chains'][market]
        assessed = assessment(env,market)
        assert assessed.completed_futures_bars == 35  # Future/incomplete rows excluded.
        assert assessed.regime.trend == 'RANGING'
        assert assessed.pipeline.status == PipelineStatus.SHADOW_CANDIDATE
        assert assessed.pipeline.consensus.confidence_label == 'UNCALIBRATED'
        assert c['73'].paired_count == 1 and not c['73'].research_review_suggested
        assert not c['73'].strategy_promotion_authorized
        assert len(c['74'].outcomes) == 4
        op = opening(env,'open-'+market,market)
        receipt = gateway.apply_assessed_open(op,assessment=assessed,risk_permit=issue(env,op))
        assert receipt.order_state == 'PENDING_SYNTHETIC'
        fill = SyntheticFOOperation('FILL','fill-'+market,op.order_id,
                                    quantity=10 if market=='NIFTY' else 25,
                                    price_cents=545,fee_cents=5)
        gateway.apply(fill,risk_permit=issue(env,fill))
    gateway.apply(SyntheticFOOperation('CANCEL','cancel-NIFTY','open-NIFTY'))
    research = inspect_stage76_fo_portfolio_risk(packets=env['boundary'].packets,
                policy=env['boundary'].policy,telemetry=env['telemetry'])
    reconciliation = inspect_stage83_fo_account_reconciliation(env['book'],research)
    report = gateway.performance_report()
    assert reconciliation.local_single_book_reconciliation_consistent
    assert reconciliation.local_budget_screen_passed
    assert report.journal_revision == 5
    assert report.journal_sha256 == reconciliation.journal_sha256
    assert report.paid_premium_cents == 35*545
    assert report.execution_fees_cents == 10
    assert report.reserved_cents == 0 and report.filled_units == 35
    assert report.initial_cents == report.cash_cents+report.paid_premium_cents+report.execution_fees_cents
    assert report.net_pnl_cents is None and report.profit_factor is None
    assert report.expectancy_cents is None and report.max_drawdown_percent is None
    assert not report.real_market_evidence_verified and not report.live_trading_enabled
    assert report.broker_orders_transmitted == 0


@pytest.mark.parametrize('market',['NIFTY','BANKNIFTY'])
@pytest.mark.parametrize('failure',['stale','conflict','wrong-source','kill','risk-loss'])
def test_combined_market_signal_and_risk_failures_make_no_hold(tmp_path,market,failure):
    env = warm_env(tmp_path)
    gateway = SyntheticFOExecutionGateway(env['book'])
    op = opening(env,'failing-'+market,market)
    permit = issue(env,op)
    assessed = assessment(env,market,age=31 if failure=='stale' else 0,
                          conflict=failure=='conflict')
    if failure=='wrong-source':
        assessed = replace(assessed,source_stage72_sha256='0'*64)
    if failure=='kill':
        env['book'].set_local_synthetic_kill_switch(active=True,operation_id='stop')
    if failure=='risk-loss':
        with pytest.raises(SyntheticFORiskBlocked):
            issue(env,op,daily_realized_loss_bps=300)
        permit = None
    with pytest.raises(Stage55SyntheticBookBlocked):
        gateway.apply_assessed_open(op,assessment=assessed,risk_permit=permit)
    assert gateway.snapshot().journal_revision == 0 and gateway.snapshot().reserved_cents == 0


def test_short_history_does_not_manufacture_a_regime_or_signal(tmp_path):
    env = environment(tmp_path)
    assessed = assessment(env,'NIFTY')
    assert assessed.regime.trend == 'UNKNOWN'
    assert assessed.completed_futures_bars == 1
    assert assessed.pipeline.status == PipelineStatus.NO_TRADE
    op = opening(env)
    with pytest.raises(Stage55SyntheticBookBlocked,match='assessment denied'):
        SyntheticFOExecutionGateway(env['book']).apply_assessed_open(
            op,assessment=assessed,risk_permit=issue(env,op))


@pytest.mark.parametrize('corruption',['checksum','duplicate-timestamp','options-checksum'])
def test_corrupted_csvs_are_rejected_by_actual_importers_before_account_creation(tmp_path,monkeypatch,corruption):
    source_globals = helper['chain_fixture'].__globals__
    if corruption == 'options-checksum':
        original = source_globals['preflight_historical_fo_catalog']
        def corrupt(partitions):
            part = partitions[0]
            path = part.root/part.declaration.snapshots[0].filename
            path.write_bytes(path.read_bytes()+b'\n')
            return original(partitions)
        monkeypatch.setitem(source_globals,'preflight_historical_fo_catalog',corrupt)
    else:
        original = source_globals['preflight_stage59_futures_csv']
        def corrupt(root,**args):
            path = root/args['declaration'].filename
            lines = path.read_text().splitlines()
            if corruption=='duplicate-timestamp': lines[2]=lines[1]
            else: lines[1]=lines[1].replace('100.05','100.10')
            raw=('\n'.join(lines)+'\n').encode(); path.write_bytes(raw)
            if corruption=='duplicate-timestamp':
                args['declaration']=replace(args['declaration'],expected_sha256=hashlib.sha256(raw).hexdigest())
            return original(root,**args)
        monkeypatch.setitem(source_globals,'preflight_stage59_futures_csv',corrupt)
    with pytest.raises(ValueError):
        warm_env(tmp_path)
    assert not (tmp_path/'selected-fo.sqlite').exists()


@pytest.mark.skipif(not hasattr(os,'fork'),reason='Abrupt process-death drill requires POSIX fork')
@pytest.mark.parametrize('crash',['uncommitted','committed-response-lost'])
def test_real_process_death_recovery_keeps_event_proof_and_capital_atomic(tmp_path,crash):
    env = warm_env(tmp_path)
    gateway = SyntheticFOExecutionGateway(env['book'])
    op,permit = opening(env),issue(env,opening(env))
    child = os.fork()
    if child == 0:
        try:
            if crash=='uncommitted':
                original = env['book']._write_event
                def die(*args):
                    original(*args)
                    os._exit(73)
                env['book']._write_event=die
            gateway.apply_assessed_open(op,assessment=assessment(env,'NIFTY'),risk_permit=permit)
            os._exit(73)
        except BaseException:
            os._exit(91)
    _,status = os.waitpid(child,0)
    assert os.waitstatus_to_exitcode(status) == 73
    env['book'] = reopen(env)
    recovered = SyntheticFOExecutionGateway(env['book'])
    snap = recovered.snapshot()
    expected = 0 if crash=='uncommitted' else 1
    assert snap.journal_revision == expected
    assert snap.reserved_cents == expected*13761
    with sqlite3.connect(env['path']) as db:
        assert db.execute('SELECT count(*) FROM execution_fo_permits').fetchone()[0] == expected
    receipt = recovered.apply(op,risk_permit=permit)
    assert receipt.replayed is (crash=='committed-response-lost')
    assert recovered.snapshot().journal_revision == 1


def test_rewritten_unkeyed_event_and_head_still_fail_risk_signature_binding(tmp_path):
    env = warm_env(tmp_path)
    gateway = SyntheticFOExecutionGateway(env['book'])
    op=opening(env)
    gateway.apply_assessed_open(op,assessment=assessment(env,'NIFTY'),risk_permit=issue(env,op))
    with sqlite3.connect(env['path']) as db:
        event=list(db.execute('SELECT * FROM execution_events').fetchone())
        event[5]=24
        digest=_hash_event(tuple(event[:-1]))
        db.execute('UPDATE execution_events SET qty=24,event_sha=?',(digest,))
        db.execute('UPDATE execution_head SET reserved_cents=?,event_sha=?',(24*550+11,digest))
    assert not env['book'].inspect().local_integrity_verified
    with pytest.raises(Stage55SyntheticBookBlocked):
        gateway.performance_report()


@pytest.mark.parametrize('target',['risk_controls','permissions','live_trading'])
def test_evolve_cannot_modify_protected_controls_or_acquire_order_authority(tmp_path,target):
    env=warm_env(tmp_path)
    before=env['book'].selected_fo_boundary_sha256
    with pytest.raises(ValueError,match='protected target'):
        GovernedEvolveService().propose(name='forbidden',hypothesis='test',target=target)
    assert env['book'].selected_fo_boundary_sha256 == before
    assert env['book'].inspect().revision == 0


def test_release_readiness_and_accounting_report_do_not_claim_real_trading(tmp_path):
    env=warm_env(tmp_path)
    report=SyntheticFOExecutionGateway(env['book']).performance_report()
    security=inspect_stage52_security_sources(ROOT)
    assert security.local_structural_controls_passed
    assert not security.production_release_allowed and security.release_blockers
    assert not security.global_unbypassable_risk_enforced
    assert report.verdict.endswith('NO_GO')
    assert env['key'] not in env['path'].read_bytes()
    assert env['key'].hex().encode() not in env['path'].read_bytes()
    assert asdict(report)['net_pnl_cents'] is None
