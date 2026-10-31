import json

import pytest

from nexus_titan.evolve.sandbox import ExperimentSandbox


def test_workspace_is_created_with_execution_disabled(tmp_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    workspace = sandbox.create_workspace("experiment_001")
    manifest = json.loads((workspace / "manifest.json").read_text())
    assert manifest["code_execution_enabled"] is False
    assert manifest["network_access_enabled"] is False
    assert manifest["trading_execution_enabled"] is False


def test_artifact_write_read_and_listing_are_isolated(tmp_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    sandbox.create_workspace("alpha")
    sandbox.create_workspace("beta")
    sandbox.write_artifact("alpha", "notes/findings.txt", "paper study")
    assert sandbox.read_artifact("alpha", "notes/findings.txt") == b"paper study"
    assert sandbox.list_artifacts("alpha") == ("notes/findings.txt",)
    assert sandbox.list_artifacts("beta") == ()


@pytest.mark.parametrize("bad_path", ["../escape.txt", "/tmp/escape.txt", ".", ""])
def test_unsafe_artifact_paths_are_rejected(tmp_path, bad_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    sandbox.create_workspace("alpha")
    with pytest.raises(ValueError):
        sandbox.write_artifact("alpha", bad_path, "blocked")


def test_artifact_overwrite_is_rejected(tmp_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    sandbox.create_workspace("alpha")
    sandbox.write_artifact("alpha", "note.txt", "first")
    with pytest.raises(FileExistsError):
        sandbox.write_artifact("alpha", "note.txt", "second")


def test_reserved_manifest_cannot_be_overwritten(tmp_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    sandbox.create_workspace("alpha")
    with pytest.raises(ValueError):
        sandbox.write_artifact("alpha", "manifest.json", "changed")


def test_invalid_experiment_id_is_rejected(tmp_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    with pytest.raises(ValueError):
        sandbox.create_workspace("../outside")


def test_oversized_artifact_is_rejected(tmp_path):
    sandbox = ExperimentSandbox(str(tmp_path / "research"))
    sandbox.create_workspace("alpha")
    with pytest.raises(ValueError):
        sandbox.write_artifact("alpha", "large.bin", b"x" * (5 * 1024 * 1024 + 1))
