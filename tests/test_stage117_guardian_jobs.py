"""Guardian recovery research-only tests; no process launch/trade adapters."""
import hashlib
from dataclasses import FrozenInstanceError
import pytest
from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger

H = hashlib.sha256(b'document').hexdigest()

def test_idempotent_submission_and_checkpoint_resume(tmp_path):
    p=tmp_path/'ledger.sqlite'
    with GuardianJobLedger(p) as jobs:
        r=jobs.submit(job_id='doc-42',kind='source_review',fingerprint=H)
        assert r.state=='QUEUED' and r.checkpoint==0 and r.no_live
        assert jobs.submit(job_id='doc-42',kind='source_review',fingerprint=H)==r
        tok=jobs.claim('doc-42',lease_seconds=10,now=100)
        assert jobs.checkpoint('doc-42',tok,3,now=101).checkpoint==3
        with pytest.raises(PermissionError):jobs.claim('doc-42',now=102)
        assert jobs.inspect_integrity()
    with GuardianJobLedger(p) as jobs:
        with pytest.raises(PermissionError):jobs.checkpoint('doc-42',tok,4,now=111)
        newer=jobs.claim('doc-42',lease_seconds=10,now=112)
        assert newer!=tok and jobs.get('doc-42').checkpoint==3
        with pytest.raises(PermissionError):jobs.complete('doc-42',tok,now=113)
        assert jobs.complete('doc-42',newer,now=113).state=='COMPLETED'
        with pytest.raises(PermissionError):jobs.claim('doc-42',now=114)

def test_repeated_fail_quarantine(tmp_path):
    with GuardianJobLedger(tmp_path/'r.sqlite',max_attempts=2) as jobs:
        jobs.submit(job_id='j',kind='advisor_refresh',fingerprint=H)
        for attempt in (1,2):
            tok=jobs.claim('j',now=attempt*100)
            row=jobs.fail('j',tok,reason='offline worker error',now=attempt*100+1)
            assert row.state==('QUEUED' if attempt==1 else 'QUARANTINED')
        with pytest.raises(PermissionError):jobs.claim('j',now=300)

def test_expired_crash_quarantine(tmp_path):
    with GuardianJobLedger(tmp_path/'r.sqlite',max_attempts=1) as jobs:
        jobs.submit(job_id='a',kind='research_evaluation',fingerprint=H)
        tok=jobs.claim('a',lease_seconds=2,now=200)
        assert jobs.quarantine_expired(now=201)==0
        assert jobs.quarantine_expired(now=202)==1
        assert jobs.get('a').state=='QUARANTINED'
        with pytest.raises(PermissionError):jobs.checkpoint('a',tok,1,now=202)

def test_lease_renewal_and_token_fencing(tmp_path):
    with GuardianJobLedger(tmp_path/'r.sqlite') as jobs:
        jobs.submit(job_id='a',kind='source_review',fingerprint=H)
        tok=jobs.claim('a',lease_seconds=2,now=100)
        assert jobs.renew('a',tok,lease_seconds=20,now=101).lease_until==121
        with pytest.raises(PermissionError):jobs.renew('a','f'*48,now=102)
        with pytest.raises(PermissionError):jobs.renew('a',tok,now=121)
        assert jobs.claim('a',lease_seconds=2,now=122)!=tok

def test_durable_backup(tmp_path):
    p=tmp_path/'data.sqlite'
    with GuardianJobLedger(p) as jobs:
        jobs.submit(job_id='x',kind='source_review',fingerprint=H)
        jobs.backup_to(tmp_path/'backup.sqlite')
        with pytest.raises(ValueError):jobs.backup_to(p)
    with GuardianJobLedger(tmp_path/'backup.sqlite') as copied:
        assert copied.get('x').state=='QUEUED' and copied.inspect_integrity()

@pytest.mark.parametrize('bad', ['trade','live_execution','broker_order','risk_override','code_exec','strategy_promotion'])
def test_deny_protected_job_kind(tmp_path,bad):
    with GuardianJobLedger(tmp_path/'x.sqlite') as jobs:
        with pytest.raises(PermissionError):jobs.submit(job_id='j',kind=bad,fingerprint=H)

@pytest.mark.parametrize('bad', ['../x','a/b','', 'a'*101,'á'])
def test_reject_invalid_job_id(tmp_path,bad):
    with GuardianJobLedger(tmp_path/'x.sqlite') as jobs:
        with pytest.raises(ValueError):jobs.submit(job_id=bad,kind='source_review',fingerprint=H)

def test_collision_and_checkpoint_regression(tmp_path):
    with GuardianJobLedger(tmp_path/'x.sqlite') as jobs:
        jobs.submit(job_id='a',kind='source_review',fingerprint=H)
        with pytest.raises(ValueError):jobs.submit(job_id='a',kind='advisor_refresh',fingerprint=H)
        tok=jobs.claim('a',now=100)
        jobs.checkpoint('a',tok,5,now=100)
        with pytest.raises(ValueError):jobs.checkpoint('a',tok,4,now=100)
        assert jobs.get('a').checkpoint==5

def test_immutable_job(tmp_path):
    with GuardianJobLedger(tmp_path/'x.sqlite') as jobs:
        row=jobs.submit(job_id='j',kind='source_review',fingerprint=H)
        with pytest.raises(FrozenInstanceError):row.no_live=False

def test_process_hard_exit_recovery_without_doubled_checkpoint(tmp_path):
    """Research worker dies after durable checkpoint; a new process continues safely."""
    import os
    from pathlib import Path
    import subprocess
    import sys
    p=tmp_path/'hard_exit.sqlite'
    with GuardianJobLedger(p) as jobs:
        jobs.submit(job_id='video-1',kind='source_review',fingerprint=H)
    source="""
from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger
import os,sys
with GuardianJobLedger(sys.argv[1]) as q:
    token=q.claim('video-1',lease_seconds=2,now=100)
    q.checkpoint('video-1',token,5,now=101)
    os._exit(0)
"""
    env=os.environ.copy()
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'src')
    result=subprocess.run([sys.executable,'-c',source,str(p)],env=env,timeout=10,check=False)
    assert result.returncode==0
    with GuardianJobLedger(p) as jobs:
        assert jobs.inspect_integrity() and jobs.get('video-1').checkpoint==5
        token=jobs.claim('video-1',lease_seconds=10,now=105)
        assert jobs.complete('video-1',token,now=106).state=='COMPLETED'


def test_corrupt_database_never_silently_becomes_healthy(tmp_path):
    from sqlite3 import DatabaseError
    p=tmp_path/'corrupt.sqlite'
    p.write_bytes(b'junk-and-not-a-sqlite-database')
    with pytest.raises(DatabaseError): GuardianJobLedger(p)
