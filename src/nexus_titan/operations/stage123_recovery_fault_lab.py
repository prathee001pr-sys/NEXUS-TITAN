"""Stage123: explicitly opt-in, fully synthetic failure drills in temp storage.

No network, broker, live-account state, real market data or runtime activation.
Contains actual subprocess crashes/timeouts against the sealed Stage121 worker.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
import tempfile

from nexus_titan.operations.stage121_research_supervisor import supervise_synthetic_research
from nexus_titan.operations.stage122_verified_recovery import (
    snapshot_guardian_ledger, verify_guardian_backup, stage_guardian_restore)
from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger

H = hashlib.sha256(b'PHASE04_FIXED_SYNTHETIC_RESEARCH_NO_LIVE').hexdigest()


@dataclass(frozen=True, slots=True)
class FaultCase:
    name: str
    passed: bool
    outcome: str


@dataclass(frozen=True, slots=True)
class FaultLabReport:
    cases: tuple[FaultCase, ...]
    all_passed: bool
    root_is_temporary: bool = True
    live_trading_enabled: bool = False
    broker_orders_sent: int = 0


def run_guardian_fault_lab(*, explicit_opt_in: bool = False, parent: str | Path | None = None,
                           timeout_seconds: float = 2.0) -> FaultLabReport:
    """Every artifact lives in a new temporary directory and is cleaned up."""
    if explicit_opt_in is not True:
        raise PermissionError('failure injection requires explicit opt-in')
    if parent is not None and (not Path(parent).is_dir() or Path(parent).is_symlink()):
        raise ValueError('safe existing parent directory required')
    results: list[FaultCase] = []
    with tempfile.TemporaryDirectory(prefix='titan-guardian-fault-', dir=parent) as work:
        root = Path(work)
        normal = supervise_synthetic_research(root/'normal.sqlite',job_id='normal',source_sha256=H,
                                              total_chunks=3)
        results.append(FaultCase('bounded_normal_worker', normal.state=='COMPLETED' and normal.attempts==1,
                                 normal.state))
        crash = supervise_synthetic_research(root/'crash.sqlite',job_id='crash',source_sha256=H,
                                             total_chunks=4,mode='crash_once')
        results.append(FaultCase('hard_process_exit_resume',crash.state=='COMPLETED' and crash.attempts==2 and
                                 crash.process_failures==1 and crash.checkpoint==4,crash.state))
        timeout = supervise_synthetic_research(root/'hang.sqlite',job_id='timeout',source_sha256=H,
                                               total_chunks=3,mode='hang_once',timeout_seconds=timeout_seconds)
        results.append(FaultCase('watchdog_timeout_resume',timeout.state=='COMPLETED' and timeout.timeouts==1 and
                                 timeout.checkpoint==3,timeout.state))
        quarantine = supervise_synthetic_research(root/'quarantine.sqlite',job_id='quarantine',source_sha256=H,
                                                   total_chunks=8,max_attempts=2,mode='crash_always')
        results.append(FaultCase('bounded_quarantine',quarantine.state=='QUARANTINED' and
                                 quarantine.attempts==2 and not quarantine.fully_resumed,quarantine.state))
        receipt = snapshot_guardian_ledger(root/'crash.sqlite',root/'crash-backup.sqlite')
        assert verify_guardian_backup(receipt.path,receipt.sha256).rows == 1
        restored = stage_guardian_restore(receipt.path,root/'staged-recovery.sqlite',receipt.sha256)
        with GuardianJobLedger(restored.path) as jobs:
            checkpoint = jobs.get('crash').checkpoint
        results.append(FaultCase('verified_staged_backup',checkpoint == 4 and
                                 restored.state=='STAGED_FOR_HUMAN_REVIEW','STAGED_ONLY'))
        bad = root/'corrupt.sqlite'
        bad.write_bytes(b'not-a-valid-sqlite-ledger')
        blocked = False
        try:
            snapshot_guardian_ledger(bad,root/'invalid-backup.sqlite')
        except sqlite3.DatabaseError:
            blocked = not (root/'invalid-backup.sqlite').exists()
        results.append(FaultCase('corrupt_database_fails_closed',blocked,'REJECTED' if blocked else 'UNSAFE'))
    return FaultLabReport(tuple(results),all(item.passed for item in results))
