"""Stage122 backup, corruption and fail-closed restore tests."""
import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import pytest
from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger
from nexus_titan.operations.stage122_verified_recovery import (
    snapshot_guardian_ledger, verify_guardian_backup, stage_guardian_restore)

H=hashlib.sha256(b'read-only input').hexdigest()

def ledger(tmp_path):
    p=tmp_path/'ledger.sqlite'
    with GuardianJobLedger(p) as db:
        db.submit(job_id='x',kind='source_review',fingerprint=H)
        t=db.claim('x',now=100)
        db.checkpoint('x',t,5,now=101)
    return p


def test_snapshot_and_staged_restore_checkpoint(tmp_path):
    p=ledger(tmp_path)
    snap=snapshot_guardian_ledger(p,tmp_path/'snap.sqlite')
    assert snap.rows==1 and snap.live_trading_enabled is False
    assert verify_guardian_backup(snap.path,snap.sha256)==snap
    restored=stage_guardian_restore(snap.path,tmp_path/'staged.sqlite',snap.sha256)
    assert restored.state=='STAGED_FOR_HUMAN_REVIEW' and not restored.auto_restored
    with GuardianJobLedger(tmp_path/'staged.sqlite') as db:
        assert db.inspect_integrity() and db.get('x').checkpoint==5
    assert p.exists()


def test_snapshot_wal_active_writer(tmp_path):
    p=ledger(tmp_path)
    with GuardianJobLedger(p) as active:
        active.submit(job_id='y',kind='advisor_refresh',fingerprint=H)
        result=snapshot_guardian_ledger(p,tmp_path/'snap.sqlite')
    assert result.rows==2


def test_no_overwrite_backup_or_restore(tmp_path):
    p=ledger(tmp_path)
    b=tmp_path/'snap.sqlite'
    first=snapshot_guardian_ledger(p,b)
    with pytest.raises(FileExistsError):snapshot_guardian_ledger(p,b)
    staged=tmp_path/'restore.sqlite'
    stage_guardian_restore(b,staged,first.sha256)
    with pytest.raises(FileExistsError):stage_guardian_restore(b,staged,first.sha256)


def test_checksum_tampering_rejected(tmp_path):
    p=ledger(tmp_path)
    rec=snapshot_guardian_ledger(p,tmp_path/'snap.sqlite')
    with closing(sqlite3.connect(rec.path)) as db:
        with db:
            db.execute("UPDATE guardian_research_jobs SET checkpoint=8 WHERE job_id='x'")
    with pytest.raises(PermissionError,match='checksum'):
        verify_guardian_backup(rec.path,rec.sha256)
    assert not (tmp_path/'staged.sqlite').exists()


def test_corrupt_original_fails_closed(tmp_path):
    p=tmp_path/'bad.sqlite';p.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):snapshot_guardian_ledger(p,tmp_path/'backup.sqlite')
    assert not (tmp_path/'backup.sqlite').exists()


def test_empty_database_rejected(tmp_path):
    p=tmp_path/'empty.sqlite'
    with closing(sqlite3.connect(p)):pass
    with pytest.raises(sqlite3.DatabaseError,match='schema'):
        snapshot_guardian_ledger(p,tmp_path/'b.sqlite')


def test_missing_original_not_recreated(tmp_path):
    p=tmp_path/'not-there.sqlite'
    with pytest.raises(FileNotFoundError):snapshot_guardian_ledger(p,tmp_path/'b.sqlite')
    assert not p.exists()


def test_symlink_source_denied(tmp_path):
    p=ledger(tmp_path)
    sym=tmp_path/'shortcut.sqlite';sym.symlink_to(p)
    with pytest.raises(PermissionError):snapshot_guardian_ledger(sym,tmp_path/'b.sqlite')


def test_symlink_destination_denied(tmp_path):
    p=ledger(tmp_path)
    dest=tmp_path/'link.sqlite';dest.symlink_to(p)
    with pytest.raises(PermissionError):snapshot_guardian_ledger(p,dest)

@pytest.mark.parametrize('bad',['bad','A'*64,'0'*65,''])
def test_bad_digest(tmp_path,bad):
    p=ledger(tmp_path)
    with pytest.raises(ValueError):verify_guardian_backup(p,bad)


def test_restore_different_file_required(tmp_path):
    p=ledger(tmp_path)
    rec=snapshot_guardian_ledger(p,tmp_path/'b.sqlite')
    with pytest.raises(FileExistsError):stage_guardian_restore(rec.path,rec.path,rec.sha256)


def test_recovery_never_activates_trade(tmp_path):
    p=ledger(tmp_path)
    rec=snapshot_guardian_ledger(p,tmp_path/'b.sqlite')
    staged=stage_guardian_restore(rec.path,tmp_path/'s.sqlite',rec.sha256)
    assert staged.live_trading_enabled is False
    assert staged.auto_restored is False
