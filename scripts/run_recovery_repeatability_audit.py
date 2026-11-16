"""Bounded Stage 121/123 *synthetic* recovery repeatability audit.

For an owner-controlled checkout only. Executes a fixed allowlist of pytest
files without network/broker access or arbitrary user-supplied commands. This
runs tests; it does not alter production watchdog limits or certify resilience.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TESTS = (
    "tests/test_stage121_research_supervisor.py",
    "tests/test_stage121_startup_hardening.py",
    "tests/test_stage123_recovery_fault_lab.py",
)


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid bounded integer")
    return value


def audit_recovery_repeatability(*, runs: int = 5, timeout_seconds: int = 120,
                                 root: Path | None = None) -> dict:
    runs = _integer(runs, 1, 20)
    timeout_seconds = _integer(timeout_seconds, 10, 300)
    project = ROOT if root is None else Path(root).resolve()
    if not project.is_dir() or any(not (project / name).is_file() for name in TESTS):
        raise ValueError("All fixed recovery test paths must exist")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project / "src")
    # Never fabricate passes when subprocess timed out or encountered an error.
    results = []
    cmd = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-W", "error", *TESTS]
    for i in range(runs):
        start = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=project, env=env, text=True, capture_output=True,
                                  timeout=timeout_seconds, check=False)
            result = {"attempt": i+1, "duration_seconds": round(time.monotonic()-start,3),
                      "return_code": proc.returncode, "timed_out": False,
                      "passed": proc.returncode == 0,
                      "stdout_tail": proc.stdout[-1000:], "stderr_tail": proc.stderr[-1000:]}
        except subprocess.TimeoutExpired as exc:
            result = {"attempt": i+1, "duration_seconds": round(time.monotonic()-start,3),
                      "return_code": None, "timed_out": True, "passed": False,
                      "stdout_tail": "", "stderr_tail": "Process timed out"}
        results.append(result)
        # Stop early on first real failure so reviewers see the original evidence.
        if not result["passed"]:
            break
    return {
        "schema": "titan.recovery_repeated_synthetic_audit.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "requested_runs": runs,
        "executed_runs": len(results),
        "all_passed": len(results) == runs and all(x["passed"] for x in results),
        "root_cause_proven": False,
        "production_recovery_certified": False,
        "live_trading_authorized": False,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--json-out", default="reports/recovery_repeatability_synthetic.json")
    opts = parser.parse_args()
    output = (ROOT / opts.json_out).resolve()
    # Never replace source or arbitrary absolute paths; only reports/ children.
    if (not output.is_relative_to(ROOT / "reports") or output.suffix != ".json"
            or any(part == ".." for part in Path(opts.json_out).parts)):
        parser.error("--json-out must name a JSON file under reports/")
    report = audit_recovery_repeatability(runs=opts.runs, timeout_seconds=opts.timeout_seconds)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(f"Synthetic recovery trials: {report['executed_runs']}/{report['requested_runs']}; "
          f"all_passed={report['all_passed']}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
