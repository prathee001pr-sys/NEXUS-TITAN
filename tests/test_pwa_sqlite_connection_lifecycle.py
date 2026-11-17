"""SQLite connection lifecycle regression: explicit closure under strict warnings.

This is a *test-only* handle-accounting instrument, not an authenticated
operator authority or a trading capability. The true Stage50 dashboard suite
is also executed under pytest -W error.
"""
from contextlib import closing
from pathlib import Path
import sqlite3

import pytest

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.operations.paper_deployment import (
    PaperDeploymentBlocked, _check_existing_virtual,
)


def _watch_sqlite(monkeypatch):
    original = sqlite3.connect
    handles = []

    class Tracked(sqlite3.Connection):
        was_closed = False

        def close(self):
            self.was_closed = True
            return super().close()

    def connect(*args, **kwargs):
        # Avoid silently overriding an unexpected caller's custom factory.
        assert "factory" not in kwargs
        handle = original(*args, factory=Tracked, **kwargs)
        handles.append(handle)
        return handle

    monkeypatch.setattr(sqlite3, "connect", connect)
    return handles


def test_approval_verifier_initialization_closes_replay_database(tmp_path, monkeypatch):
    handles = _watch_sqlite(monkeypatch)
    verifier = CryptographicApprovalVerifier(
        "LOCAL_SYNTHETIC_TEST_KEY_NOT_AN_IDENTITY",
        db_path=tmp_path / "approval-replay.sqlite3",
    )
    assert verifier.db_path.exists()
    assert len(handles) >= 1
    assert all(handle.was_closed for handle in handles)


def _fixture_policy_db(path: Path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE account_state ("
            "account_id TEXT, strict_paper_mode INTEGER,"
            "gateway_only_mode INTEGER, initial_capital REAL)"
        )
        conn.execute(
            "INSERT INTO account_state VALUES (?,?,?,?)",
            ("S151", 1, 1, 50000.0),
        )


def test_existing_virtual_policy_read_closes_ro_connection(tmp_path, monkeypatch):
    path = tmp_path / "account.sqlite3"
    _fixture_policy_db(path)
    handles = _watch_sqlite(monkeypatch)
    assert _check_existing_virtual(path, "S151", 50000.0) is None
    assert handles and all(conn.was_closed for conn in handles)


def test_rejected_virtual_policy_read_closes_ro_connection(tmp_path, monkeypatch):
    path = tmp_path / "invalid-account.sqlite3"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("CREATE TABLE unrelated (id INTEGER)")
    handles = _watch_sqlite(monkeypatch)
    with pytest.raises(PaperDeploymentBlocked):
        _check_existing_virtual(path, "S151", 50000.0)
    assert handles and all(conn.was_closed for conn in handles)
