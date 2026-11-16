"""Tests for bounded repetition harness, without invoking real subprocesses."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'run_recovery_repeatability_audit.py'
SPEC=importlib.util.spec_from_file_location('recovery_harness',SCRIPT)
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def fake_repo(tmp_path):
    for rel in MOD.TESTS:
        p=tmp_path/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('pass\n')
    (tmp_path/'src').mkdir()
    return tmp_path


def test_success_3_bounded_runs(tmp_path,monkeypatch):
    repo=fake_repo(tmp_path); observed=[]
    def run(command, **kw):
        observed.append((command,kw))
        return SimpleNamespace(returncode=0,stdout='3 passed',stderr='')
    monkeypatch.setattr(MOD.subprocess,'run',run)
    r=MOD.audit_recovery_repeatability(root=repo,runs=3,timeout_seconds=30)
    assert r['all_passed'] and r['executed_runs']==3
    assert all(x['passed'] for x in r['results'])
    assert not r['production_recovery_certified'] and not r['live_trading_authorized']
    assert all(x[0][:3]==[MOD.sys.executable,'-m','pytest'] for x in observed)
    assert all(x[1]['env']['PYTHONPATH']==str(repo/'src') for x in observed)


def test_stop_on_failed_run(tmp_path,monkeypatch):
    repo=fake_repo(tmp_path)
    outcomes=iter([0,1,0])
    monkeypatch.setattr(MOD.subprocess,'run',lambda *_a,**_k: SimpleNamespace(returncode=next(outcomes),stdout='',stderr='fail'))
    r=MOD.audit_recovery_repeatability(root=repo,runs=3)
    assert r['executed_runs']==2 and not r['all_passed']


def test_timeout_is_not_success(tmp_path,monkeypatch):
    repo=fake_repo(tmp_path)
    def timeout(command,**kw):raise MOD.subprocess.TimeoutExpired(command,kw['timeout'])
    monkeypatch.setattr(MOD.subprocess,'run',timeout)
    r=MOD.audit_recovery_repeatability(root=repo,runs=2)
    assert r['executed_runs']==1 and r['results'][0]['timed_out'] and not r['all_passed']

@pytest.mark.parametrize('runs,timeout',[(0,120),(21,120),(True,120),(1,9),(1,301),(1,True)])
def test_invalid_bounds(tmp_path,runs,timeout):
    with pytest.raises(ValueError):MOD.audit_recovery_repeatability(root=fake_repo(tmp_path),runs=runs,timeout_seconds=timeout)


def test_missing_tests_refused(tmp_path):
    with pytest.raises(ValueError):MOD.audit_recovery_repeatability(root=tmp_path)
