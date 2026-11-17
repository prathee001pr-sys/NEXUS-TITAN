"""Offline private snapshot storage checks; no owner auth or network asserted."""
from dataclasses import replace
import json
import os
from pathlib import Path
import stat

import pytest

from nexus_titan.dashboard.pwa_research_export import (
    export_local_pwa_research_status,
    _canon,
    _digest,
)
from nexus_titan.dashboard.private_snapshot_store import (
    LocalResearchSnapshotBlocked,
    SNAPSHOT_FILENAME,
    read_private_local_research_snapshot,
    write_private_local_research_snapshot,
)
from nexus_titan.operations.stage145_dashboard_status import DashboardResearchStatus


def _status(market, eligible):
    return DashboardResearchStatus(
        market=market,
        research_status="HUMAN_REVIEW" if eligible else "BLOCKED",
        research_review_eligible=eligible,
        human_review_required=True,
        live_trading_enabled=False,
        automatic_promotion_enabled=False,
        reasons=() if eligible else ("BLOCKED_UNVERIFIED_SOURCE",),
    )


def packet(indian=True, crypto=False):
    return export_local_pwa_research_status(
        _status("INDIAN_FO", indian), _status("CRYPTO", crypto)
    )


@pytest.fixture
def private(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    directory.chmod(0o700)
    return directory


def test_private_snapshot_roundtrip_and_restrictive_permissions(private):
    message = packet()
    write_private_local_research_snapshot(private, message)
    stored = private / SNAPSHOT_FILENAME
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert read_private_local_research_snapshot(private) == message
    assert stored.read_bytes() == _canon(message)
    assert list(private.iterdir()) == [stored]
    assert not read_private_local_research_snapshot(private)["safety"]["live_trading_authorized"]


def test_second_atomic_write_replaces_only_known_display_packet(private):
    first = packet()
    second = packet(indian=False, crypto=True)
    write_private_local_research_snapshot(private, first)
    write_private_local_research_snapshot(private, second)
    assert read_private_local_research_snapshot(private) == second
    assert len(list(private.iterdir())) == 1


@pytest.mark.parametrize("mode", [0o755, 0o750, 0o777])
def test_writable_or_readable_by_others_directory_is_rejected(private, mode):
    private.chmod(mode)
    with pytest.raises(LocalResearchSnapshotBlocked, match="0700"):
        write_private_local_research_snapshot(private, packet())
    with pytest.raises(LocalResearchSnapshotBlocked, match="0700"):
        read_private_local_research_snapshot(private)


def test_private_directory_symlink_rejected_without_writing(tmp_path, private):
    alias = tmp_path / "alias"
    alias.symlink_to(private, target_is_directory=True)
    with pytest.raises(OSError):
        write_private_local_research_snapshot(alias, packet())
    assert list(private.iterdir()) == []


def test_existing_symlink_cannot_overwrite_outside_file(private, tmp_path):
    outside = tmp_path / "owned-cannot-overwrite.txt"
    outside.write_text("UNCHANGED")
    (private / SNAPSHOT_FILENAME).symlink_to(outside)
    with pytest.raises(LocalResearchSnapshotBlocked):
        write_private_local_research_snapshot(private, packet())
    with pytest.raises(LocalResearchSnapshotBlocked):
        read_private_local_research_snapshot(private)
    assert outside.read_text() == "UNCHANGED"


@pytest.mark.parametrize("mode", [0o644, 0o666, 0o400])
def test_existing_snapshot_bad_mode_denied(private, mode):
    dest = private / SNAPSHOT_FILENAME
    dest.write_bytes(_canon(packet()))
    dest.chmod(mode)
    with pytest.raises(LocalResearchSnapshotBlocked):
        read_private_local_research_snapshot(private)
    with pytest.raises(LocalResearchSnapshotBlocked):
        write_private_local_research_snapshot(private, packet())


def test_json_rehashed_privilege_cannot_be_imported(private):
    p = packet()
    p["safety"]["owner_identity_authenticated"] = True
    p["content_sha256"] = _digest({
        key: val for key, val in p.items() if key != "content_sha256"
    })
    target = private / SNAPSHOT_FILENAME
    target.write_bytes(_canon(p))
    target.chmod(0o600)
    with pytest.raises(LocalResearchSnapshotBlocked, match="Untrusted"):
        read_private_local_research_snapshot(private)
    with pytest.raises(LocalResearchSnapshotBlocked):
        write_private_local_research_snapshot(private, p)


def test_duplicate_json_keys_denied_even_if_otherwise_safe(private):
    raw = _canon(packet())
    assert raw.count(b'"scope":') == 1
    corrupted = raw.replace(
        b'"scope":',
        b'"scope":"DISPLAY_ONLY_LOCAL_RESEARCH_NO_GO","scope":', 1,
    )
    dest = private / SNAPSHOT_FILENAME
    dest.write_bytes(corrupted)
    dest.chmod(0o600)
    with pytest.raises(LocalResearchSnapshotBlocked):
        read_private_local_research_snapshot(private)


def test_noncanonical_json_or_extra_bytes_denied(private):
    target = private / SNAPSHOT_FILENAME
    target.write_bytes(json.dumps(packet(), indent=2).encode("utf-8"))
    target.chmod(0o600)
    with pytest.raises(LocalResearchSnapshotBlocked, match="Untrusted"):
        read_private_local_research_snapshot(private)


def test_oversized_untrusted_file_rejected_before_json_parse(private):
    target = private / SNAPSHOT_FILENAME
    target.write_bytes(b"x" * 4097)
    target.chmod(0o600)
    with pytest.raises(LocalResearchSnapshotBlocked, match="Unsafe"):
        read_private_local_research_snapshot(private)


def test_simulated_atomic_rename_failure_leaves_previous_valid_snapshot(private, monkeypatch):
    import nexus_titan.dashboard.private_snapshot_store as store
    before = packet()
    write_private_local_research_snapshot(private, before)
    def denied_replace(*args, **kwargs):
        raise OSError("simulated disk rename refusal")
    monkeypatch.setattr(store.os, "replace", denied_replace)
    with pytest.raises(OSError, match="simulated"):
        write_private_local_research_snapshot(private, packet(False, True))
    assert read_private_local_research_snapshot(private) == before
    assert sorted(p.name for p in private.iterdir()) == [SNAPSHOT_FILENAME]


def test_packet_market_spoofing_never_accepted(private):
    forged = packet()
    forged["markets"]["CRYPTO"] = replace(
        _status("CRYPTO", True), market="CRYPTO"
    ).__dict__
    with pytest.raises(LocalResearchSnapshotBlocked):
        write_private_local_research_snapshot(private, forged)


def test_absent_snapshot_does_not_invent_verified_owner_or_market_evidence(private):
    with pytest.raises(FileNotFoundError):
        read_private_local_research_snapshot(private)
    assert list(private.iterdir()) == []
