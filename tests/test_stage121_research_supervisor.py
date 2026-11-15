"""Stage121 bounded subprocess recovery: offline synthetic-only tests."""
import hashlib
import sqlite3
import pytest

from nexus_titan.operations.stage121_research_supervisor import supervise_synthetic_research, SupervisorResult
from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger

H = hashlib.sha256(b'fixed trusted synthetic research input').hexdigest()


def run(tmp_path, mode='normal', **kw):
    return supervise_synthetic_research(tmp_path/'state.sqlite', job_id='research-1',
                                        source_sha256=H, mode=mode, **kw)


def test_normal_subprocess_and_checkpoint(tmp_path):
    r=run(tmp_path,total_chunks=5)
    assert r==SupervisorResult('research-1','COMPLETED',5,1,0,0,True)
    assert r.broker_orders_sent==0 and r.live_trading_enabled is False
    with GuardianJobLedger(tmp_path/'state.sqlite') as l:
        assert l.inspect_integrity() and l.get('research-1').checkpoint==5


def test_abrupt_exit_recovers_exactly_once(tmp_path):
    r=run(tmp_path,mode='crash_once',total_chunks=4)
    assert (r.state,r.checkpoint,r.attempts,r.process_failures)==('COMPLETED',4,2,1)
    with GuardianJobLedger(tmp_path/'state.sqlite') as l:
        assert l.get('research-1').checkpoint==4


def test_hanging_worker_killed_and_recovered(tmp_path):
    r=run(tmp_path,mode='hang_once',total_chunks=2,timeout_seconds=1.2)
    assert (r.state,r.checkpoint,r.attempts,r.timeouts)==('COMPLETED',2,2,1)


def test_retry_cap_quarantines(tmp_path):
    r=run(tmp_path,mode='crash_always',total_chunks=10,max_attempts=2)
    assert r.state=='QUARANTINED' and r.attempts==2 and not r.fully_resumed
    assert r.broker_orders_sent==0


def test_completed_job_rejects_duplicate_run(tmp_path):
    run(tmp_path)
    with pytest.raises(PermissionError,match='explicit operator'):
        run(tmp_path)

@pytest.mark.parametrize('mode', ['trade','broker_call','shell','code_execution','risk_override','',None])
def test_bad_modes_rejected(tmp_path,mode):
    with pytest.raises(PermissionError): run(tmp_path,mode=mode)

@pytest.mark.parametrize('kw', [{'total_chunks':0},{'total_chunks':True},{'total_chunks':51},
                                {'max_attempts':0},{'max_attempts':True},{'memory_mb':10},
                                {'memory_mb':True},{'timeout_seconds':0},{'timeout_seconds':float('nan')},
                                {'timeout_seconds':True}])
def test_bad_limits_rejected(tmp_path,kw):
    with pytest.raises(ValueError):run(tmp_path,**kw)


def test_invalid_fingerprint_fails_before_job(tmp_path):
    with pytest.raises(ValueError):
        supervise_synthetic_research(tmp_path/'bad.sqlite',job_id='x',source_sha256='bad')
    assert not (tmp_path/'bad.sqlite').exists()


def test_occupied_lease_cannot_be_stolen(tmp_path):
    with GuardianJobLedger(tmp_path/'state.sqlite') as l:
        l.submit(job_id='research-1',kind='research_evaluation',fingerprint=H)
        tok=l.claim('research-1',lease_seconds=60)
    with pytest.raises(PermissionError):run(tmp_path)
    with GuardianJobLedger(tmp_path/'state.sqlite') as l:
        assert l.get('research-1').state=='RUNNING'
