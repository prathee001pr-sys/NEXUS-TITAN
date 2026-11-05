"""Stage91-94 bounded synthetic-only audit regression checks."""
from dataclasses import replace
from pathlib import Path
import runpy
import pytest
from nexus_titan.operations.stage90_signed_valuation_history import capture_stage90_checkpoint, inspect_stage90_history
from nexus_titan.operations.stage91_performance_eligibility import evaluate_stage91
from nexus_titan.operations.stage92_accounting_reconciliation import reconcile_stage92
from nexus_titan.operations.stage93_recovery_consistency import inspect_stage93_recovery
from nexus_titan.operations.stage94_audit_boundary import inspect_stage94_boundary

fixture=runpy.run_path(str(Path(__file__).resolve().parent/'helpers/fo_synthetic_fixture.py'))
environment=fixture['environment']

def evidence(tmp_path):
    env=environment(tmp_path,lots=1)
    marks=[]
    for _ in range(3):
        env['clock'][0]+=1
        marks.append(capture_stage90_checkpoint(env['book'],env['boundary'],issuer_key=env['key'],quotes=(),previous=marks[-1] if marks else None))
    snap=env['book'].snapshot_local_synthetic_portfolio()
    history=inspect_stage90_history(env['boundary'],tuple(marks),current_snapshot=snap)
    return history,snap

def test_stage91_never_promotes_official_metrics(tmp_path):
    history,_=evidence(tmp_path)
    result=evaluate_stage91(history)
    assert result.exploratory_drawdown_allowed
    assert not result.official_performance_allowed and not result.live_trading_allowed
    assert not evaluate_stage91(replace(history,profit_factor=1.5)).exploratory_drawdown_allowed

def test_stage92_reconciles_and_detects_corruption(tmp_path):
    _,snap=evidence(tmp_path)
    assert reconcile_stage92(snap).consistent
    assert not reconcile_stage92(replace(snap,available_cents=snap.available_cents+1)).consistent
    assert not reconcile_stage92(replace(snap,live_trading_enabled=True)).consistent

def test_stage93_requires_exact_recovery_head(tmp_path):
    history,snap=evidence(tmp_path)
    assert inspect_stage93_recovery(history,snap).consistent
    assert not inspect_stage93_recovery(history,replace(snap,journal_tip='f'*64)).consistent

def test_stage94_never_enables_live_execution(tmp_path):
    history,snap=evidence(tmp_path)
    verdict=inspect_stage94_boundary(history,snap)
    assert verdict.synthetic_research_readable
    assert not verdict.official_performance_allowed
    assert not verdict.broker_execution_allowed
    assert not inspect_stage94_boundary(history,replace(snap,broker_orders_transmitted=1)).synthetic_research_readable

@pytest.mark.parametrize('value',[None,{},'invalid'])
def test_stage91_rejects_untyped_input(value):
    with pytest.raises(TypeError):
        evaluate_stage91(value)
