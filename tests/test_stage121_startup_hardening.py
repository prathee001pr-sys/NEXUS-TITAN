"""Guardrail tests for the fixed, synthetic-only supervisor startup path."""
from __future__ import annotations

import hashlib
import subprocess

from nexus_titan.operations.stage117_guardian_jobs import GuardianJobLedger
from nexus_titan.operations import stage121_research_supervisor as supervisor

FINGERPRINT = hashlib.sha256(b"stage121_site_free_child_startup_guard").hexdigest()


def test_only_fixed_child_runs_without_site_initialization(tmp_path, monkeypatch):
    observed = []
    original_run = subprocess.run

    def inspect_command(command, **kwargs):
        observed.append((tuple(command), kwargs["env"]))
        return original_run(command, **kwargs)

    monkeypatch.setattr(supervisor.subprocess, "run", inspect_command)
    r = supervisor.supervise_synthetic_research(
        tmp_path / "normal.sqlite", job_id="startup-guard", source_sha256=FINGERPRINT,
        total_chunks=2, mode="normal", timeout_seconds=2.0,
    )
    assert r.state == "COMPLETED" and r.checkpoint == 2 and r.attempts == 1
    assert len(observed) == 1
    cmd, env = observed[0]
    assert cmd[:4] == (supervisor.sys.executable, "-B", "-S", "-m")
    assert cmd[4] == "nexus_titan.operations.stage121_research_supervisor"
    assert len(cmd) == 13
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["PYTHONPATH"] == str(supervisor.Path(supervisor.__file__).resolve().parents[2])
    assert r.broker_orders_sent == 0 and r.live_trading_enabled is False


def test_site_free_child_recovers_fixed_crash(tmp_path):
    r = supervisor.supervise_synthetic_research(
        tmp_path / "crash.sqlite", job_id="crash-guard", source_sha256=FINGERPRINT,
        total_chunks=3, mode="crash_once", timeout_seconds=2.0,
    )
    assert (r.state, r.checkpoint, r.attempts, r.process_failures) == ("COMPLETED", 3, 2, 1)
    with GuardianJobLedger(tmp_path / "crash.sqlite") as db:
        assert db.get("crash-guard").state == "COMPLETED"
        assert db.inspect_integrity()


def test_true_timeout_keeps_retry_cap_and_quarantine(tmp_path, monkeypatch):
    """Startup hardening must not turn a genuine timeout into success."""
    def always_hangs(command, **kwargs):
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs["timeout"])

    monkeypatch.setattr(supervisor.subprocess, "run", always_hangs)
    r = supervisor.supervise_synthetic_research(
        tmp_path / "stalled.sqlite", job_id="timeout-guard", source_sha256=FINGERPRINT,
        total_chunks=2, mode="normal", max_attempts=2, timeout_seconds=1.2,
    )
    assert (r.state, r.attempts, r.timeouts, r.process_failures, r.fully_resumed) == (
        "QUARANTINED", 2, 2, 2, False,
    )
    assert r.checkpoint == 0 and r.live_trading_enabled is False and r.broker_orders_sent == 0
    with GuardianJobLedger(tmp_path / "stalled.sqlite", max_attempts=2) as db:
        assert db.get("timeout-guard").state == "QUARANTINED"
        assert db.inspect_integrity()
