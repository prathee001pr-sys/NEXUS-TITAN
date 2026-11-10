"""Stage121: opt-in, bounded *synthetic research* subprocess recovery harness.

This is NOT a production supervisor or a general-purpose worker launcher. Only
this module's hard-coded demonstration worker may run. No trading APIs, secrets,
network requests, dynamic commands, process daemon, or background scheduling.
GuardianJobLedger (Stage117) remains authoritative for leases and checkpoints.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import math
import os
import subprocess
import sys
import time

from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger

MODES = frozenset({"normal", "crash_once", "hang_once", "crash_always"})


@dataclass(frozen=True, slots=True)
class SupervisorResult:
    job_id: str
    state: str
    checkpoint: int
    attempts: int
    process_failures: int
    timeouts: int
    fully_resumed: bool
    live_trading_enabled: bool = False
    broker_orders_sent: int = 0


def _check_int(value: int, lo: int, hi: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise ValueError(f"{label} must be an integer from {lo} to {hi}")
    return value


def _child(*, db: str, job_id: str, start: int, total: int, attempt: int,
           mode: str, memory_mb: int) -> int:
    """Fixed-purpose child: writes only research checkpoints, no arbitrary scripts."""
    # Use OS-enforced memory cap where available; fail closed if not available.
    import resource
    cap = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
    token = sys.stdin.readline().strip()
    if len(token) != 48:
        return 72
    with GuardianJobLedger(db) as jobs:
        for index in range(start + 1, total + 1):
            jobs.checkpoint(job_id, token, index)
            if index == start + 1 and (mode == "crash_always" or (mode == "crash_once" and attempt == 1)):
                os._exit(73)  # simulate abrupt SIGKILL-like exit after SQLite commit
            if index == start + 1 and mode == "hang_once" and attempt == 1:
                time.sleep(10.0)  # watchdog timeout must kill this child
    return 0


def supervise_synthetic_research(
    db_path: str | Path, *, job_id: str, source_sha256: str, total_chunks: int = 3,
    mode: str = "normal", max_attempts: int = 3, timeout_seconds: float = 2.0,
    memory_mb: int = 768,
) -> SupervisorResult:
    """Run a *fixed synthetic* task with retry/quarantine; no automatic other jobs.

    Parent holds lease token. A subprocess may only move a checkpoint forward.
    After parent observes the child EXITED, parent marks failure or completion.
    Unknown pre-existing RUNNING leases are never stolen or force-expired.
    """
    _check_int(total_chunks, 1, 50, "total_chunks")
    _check_int(max_attempts, 1, 5, "max_attempts")
    _check_int(memory_mb, 512, 2048, "memory_mb")
    if mode not in MODES:
        raise PermissionError("unapproved research worker mode")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (float, int)) or not (
        math.isfinite(timeout_seconds) and .1 <= timeout_seconds <= 30
    ):
        raise ValueError("invalid worker timeout")
    if not isinstance(source_sha256, str) or len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("source_sha256 required")
    failures = timeouts = 0
    with GuardianJobLedger(db_path, max_attempts=max_attempts) as jobs:
        submitted = jobs.submit(job_id=job_id, kind="research_evaluation", fingerprint=source_sha256)
        if submitted.state != "QUEUED" or submitted.attempts:
            raise PermissionError("existing job must be recovered by explicit operator review")
        for _ in range(max_attempts):
            token = jobs.claim(job_id, lease_seconds=max(12, math.ceil(timeout_seconds) + 5))
            before = jobs.get(job_id)
            env = {"PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                   "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
            cmd = [sys.executable, "-B", "-m", "nexus_titan.operations.stage121_research_supervisor",
                   "--guardian-child", str(Path(db_path).resolve()), job_id,
                   str(before.checkpoint), str(total_chunks), str(before.attempts),
                   mode, str(memory_mb)]
            try:
                child = subprocess.run(cmd, input=token + "\n", text=True, capture_output=True,
                                       env=env, timeout=timeout_seconds, check=False)
                ok = child.returncode == 0 and jobs.get(job_id).checkpoint == total_chunks
                if not ok:
                    failures += 1
            except subprocess.TimeoutExpired:
                # subprocess.run kills AND waits for this fixed child before returning.
                ok = False
                failures += 1
                timeouts += 1
            if ok:
                result = jobs.complete(job_id, token)
                return SupervisorResult(job_id, result.state, result.checkpoint,
                                        result.attempts, failures, timeouts, True)
            jobs.fail(job_id, token, reason="ISOLATED_WORKER_FAILURE")
        result = jobs.get(job_id)
        return SupervisorResult(job_id, result.state, result.checkpoint,
                                result.attempts, failures, timeouts, False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fixed research checkpoint child only")
    parser.add_argument("--guardian-child", action="store_true")
    parser.add_argument("args", nargs="*")
    a = parser.parse_args()
    if not a.guardian_child or len(a.args) != 7:
        return 64
    db, job, start, total, attempt, mode, mem = a.args
    if mode not in MODES:
        return 65
    try:
        return _child(db=db, job_id=job, start=_check_int(int(start), 0, 50, "start"),
                      total=_check_int(int(total), 1, 50, "total"),
                      attempt=_check_int(int(attempt), 1, 5, "attempt"),
                      mode=mode, memory_mb=_check_int(int(mem), 512, 2048, "memory_mb"))
    except (ValueError, PermissionError, OSError):
        return 66


if __name__ == "__main__":
    raise SystemExit(main())
