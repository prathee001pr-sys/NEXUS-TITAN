"""Run true F&O crash drills in a dedicated single-threaded Python process.

Unlike pytest's multithreaded process, this process starts with a clean
interpreter. A nested os.fork() still simulates the real abrupt exit at the
same SQLite transaction boundary as the legacy tests.

No broker, market-data provider, or live trading integration is used.
"""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    "stage88": (
        "test_stage88_combined_fo_reliability.py",
        "_isolated_stage88_crash_drill",
        ("uncommitted", "committed-response-lost"),
    ),
    "stage89": (
        "test_stage89_synthetic_option_close.py",
        "_isolated_stage89_crash_drill",
        ("before-commit", "after-commit-before-response"),
    ),
}


def launch(stage: str, scenario: str, tmp_path: Path) -> None:
    """Invoke a real, bounded subprocess and propagate every failure to pytest."""
    if stage not in CASES or scenario not in CASES[stage][2]:
        raise AssertionError("Unexpected isolated synthetic crash-drill request")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    # Keep numerical libraries single-threaded before the isolated fork.
    for setting in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        env[setting] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-W", "error", str(Path(__file__).resolve()),
             stage, scenario, str(tmp_path)],
            cwd=ROOT, env=env, capture_output=True, text=True,
            check=False, timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(f"Isolated {stage}/{scenario} crash drill timed out") from exc
    assert completed.returncode == 0, (
        f"Isolated {stage}/{scenario} crash drill failed with "
        f"exit {completed.returncode}\n"
        f"stdout:\n{completed.stdout[-5000:]}\n"
        f"stderr:\n{completed.stderr[-5000:]}"
    )


def _run(stage: str, scenario: str, directory: str) -> None:
    if stage not in CASES or scenario not in CASES[stage][2]:
        raise ValueError("Unexpected test case or scenario")
    if threading.active_count() != 1:
        raise RuntimeError("Crash fork parent is not single-threaded")
    filename, function_name, _ = CASES[stage]
    path = Path(directory)
    if not path.is_dir():
        raise ValueError("Pytest temporary directory is missing")
    loaded = runpy.run_path(str(ROOT / "tests" / filename), run_name="titan_crash_drill")
    if threading.active_count() != 1:
        raise RuntimeError("Test module started threads before crash drill fork")
    loaded[function_name](path, scenario)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: isolated_fo_crash_runner.py STAGE SCENARIO TMP_DIR")
    _run(*sys.argv[1:])
