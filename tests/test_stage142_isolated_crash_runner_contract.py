"""Safety contract for single-threaded synthetic F&O crash-test launcher."""
from __future__ import annotations

from pathlib import Path
import runpy
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
launch = runpy.run_path(str(ROOT / "tests/helpers/isolated_fo_crash_runner.py"))["launch"]


def test_unknown_stage_and_scenario_fail_before_subprocess(tmp_path, monkeypatch):
    def no_subprocess(*args, **kwargs):
        raise AssertionError("Invalid case unexpectedly spawned subprocess")
    monkeypatch.setattr(subprocess, "run", no_subprocess)
    with pytest.raises(AssertionError, match="Unexpected isolated"):
        launch("production", "uncommitted", tmp_path)
    with pytest.raises(AssertionError, match="Unexpected isolated"):
        launch("stage88", "unexpected-case", tmp_path)


def test_subprocess_failed_crash_assertions_are_propagated(tmp_path, monkeypatch):
    def failed(*args, **kwargs):
        assert kwargs["timeout"] == 90
        assert kwargs["check"] is False
        assert "-W" in args[0] and "error" in args[0]
        return subprocess.CompletedProcess(args[0], 91, stdout="", stderr="safety failure")
    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(AssertionError, match="safety failure"):
        launch("stage88", "uncommitted", tmp_path)


def test_hung_crash_drill_is_bounded_and_fails_closed(tmp_path, monkeypatch):
    def never_return(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", never_return)
    with pytest.raises(AssertionError, match="timed out"):
        launch("stage89", "before-commit", tmp_path)
