"""Filesystem workspace for research artifacts; deliberately executes no code."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re


_EXPERIMENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_MAX_ARTIFACT_BYTES = 5 * 1024 * 1024


class ExperimentSandbox:
    """Create isolated per-experiment folders for artifacts and notes only.

    This is not an execution sandbox. It does not run Python, shell commands,
    notebooks, strategies, plugins, or network requests.
    """

    def __init__(self, root: str) -> None:
        if not root.strip():
            raise ValueError("sandbox root must not be empty")
        self._root = Path(root).expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        if self._root.is_symlink():
            raise ValueError("sandbox root must not be a symlink")
        try:
            os.chmod(self._root, 0o700)
        except OSError:
            # Some platforms do not support POSIX permission bits.
            pass

    @staticmethod
    def _validate_experiment_id(experiment_id: str) -> None:
        if not _EXPERIMENT_ID.fullmatch(experiment_id):
            raise ValueError("invalid experiment_id")

    def _workspace(self, experiment_id: str) -> Path:
        self._validate_experiment_id(experiment_id)
        workspace = self._root / experiment_id
        if workspace.is_symlink():
            raise ValueError("workspace must not be a symlink")
        resolved = workspace.resolve()
        if self._root not in resolved.parents:
            raise ValueError("workspace path escapes sandbox root")
        return workspace

    def create_workspace(self, experiment_id: str) -> Path:
        workspace = self._workspace(experiment_id)
        workspace.mkdir(mode=0o700, parents=False, exist_ok=False)
        manifest = {
            "experiment_id": experiment_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "purpose": "research artifact storage only",
            "code_execution_enabled": False,
            "network_access_enabled": False,
            "trading_execution_enabled": False,
        }
        (workspace / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        return workspace

    def _artifact_path(self, experiment_id: str, relative_path: str) -> tuple[Path, Path]:
        workspace = self._workspace(experiment_id)
        if not workspace.is_dir():
            raise FileNotFoundError(f"workspace does not exist: {experiment_id}")
        relative = Path(relative_path)
        if relative.is_absolute() or not relative.parts or any(
            part in {"", ".", ".."} for part in relative.parts
        ):
            raise ValueError("artifact path must be a safe relative path")
        if relative.name == "manifest.json":
            raise ValueError("manifest.json is reserved")
        candidate = workspace.joinpath(relative)
        current = workspace
        for part in relative.parts[:-1]:
            current = current / part
            if current.is_symlink():
                raise ValueError("symlink directories are not allowed")
        if candidate.is_symlink():
            raise ValueError("symlink artifacts are not allowed")
        resolved = candidate.resolve()
        if workspace.resolve() not in resolved.parents:
            raise ValueError("artifact path escapes workspace")
        return workspace, candidate

    def write_artifact(self, experiment_id: str, relative_path: str,
                       content: bytes | str) -> Path:
        _, target = self._artifact_path(experiment_id, relative_path)
        data = content.encode("utf-8") if isinstance(content, str) else content
        if not isinstance(data, bytes):
            raise TypeError("artifact content must be str or bytes")
        if len(data) > _MAX_ARTIFACT_BYTES:
            raise ValueError("artifact exceeds 5 MiB limit")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Re-check after directory creation to reduce path substitution risk.
        self._artifact_path(experiment_id, relative_path)
        with target.open("xb") as handle:
            handle.write(data)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return target

    def read_artifact(self, experiment_id: str, relative_path: str) -> bytes:
        _, target = self._artifact_path(experiment_id, relative_path)
        return target.read_bytes()

    def list_artifacts(self, experiment_id: str) -> tuple[str, ...]:
        workspace = self._workspace(experiment_id)
        if not workspace.is_dir():
            raise FileNotFoundError(f"workspace does not exist: {experiment_id}")
        return tuple(sorted(
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*")
            if path.is_file() and not path.is_symlink() and path.name != "manifest.json"
        ))
