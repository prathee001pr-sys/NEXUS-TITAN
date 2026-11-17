"""POSIX-only, private offline handoff for local PWA research display packets.

This module DOES NOT serve HTTP, connect to GitHub, authenticate the PWA
owner, verify a source commit, or authorize trading or paper orders. A
SHA-256 digest detects accidental alteration; it is not a signature.
A trusted, separately authenticated backend must enforce any future
transport or user/session security boundary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import stat

from nexus_titan.dashboard.pwa_research_export import (
    _canon,
    validate_local_pwa_research_status,
)

SNAPSHOT_FILENAME = "pwa-research-status.json"
MAX_BYTES = 4096


class LocalResearchSnapshotBlocked(ValueError):
    """Fail-closed local-only research snapshot storage refusal."""


def _open_private_directory(directory: Path) -> int:
    if not isinstance(directory, Path):
        raise LocalResearchSnapshotBlocked("Private snapshot directory must be Path")
    if not all(hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")):
        raise LocalResearchSnapshotBlocked("Required no-follow POSIX directory controls unavailable")
    fd = os.open(
        directory,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.getuid()
        ):
            raise LocalResearchSnapshotBlocked("Directory must be owner-owned and mode 0700")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _check_existing_entry(directory_fd: int) -> os.stat_result | None:
    try:
        info = os.stat(
            SNAPSHOT_FILENAME, dir_fd=directory_fd, follow_symlinks=False
        )
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_uid != os.getuid()
    ):
        raise LocalResearchSnapshotBlocked("Unsafe existing snapshot; refuse replacement")
    return info


def write_private_local_research_snapshot(directory: Path, packet: object) -> None:
    """Atomically place an already-validated display-only packet, mode 0600.

    The directory must already exist, be owner-owned and mode 0700.
    The caller must provide an actual Path; no network or directories created.
    """
    if not validate_local_pwa_research_status(packet):
        raise LocalResearchSnapshotBlocked("Invalid or privileged local status packet")
    data = _canon(packet)
    if len(data) > MAX_BYTES:
        raise LocalResearchSnapshotBlocked("Research packet exceeds byte limit")
    folder_fd = _open_private_directory(directory)
    temporary = ".pwa-status-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        _check_existing_entry(folder_fd)
        if not hasattr(os, "O_NOFOLLOW"):
            raise LocalResearchSnapshotBlocked("No-follow source writes unavailable")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        temp_fd = os.open(temporary, flags, 0o600, dir_fd=folder_fd)
        created = True
        with os.fdopen(temp_fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        _check_existing_entry(folder_fd)
        os.replace(
            temporary, SNAPSHOT_FILENAME,
            src_dir_fd=folder_fd, dst_dir_fd=folder_fd,
        )
        created = False
        os.fsync(folder_fd)
    finally:
        if created:
            try:
                os.unlink(temporary, dir_fd=folder_fd)
            except FileNotFoundError:
                pass
        os.close(folder_fd)


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    values: dict[str, object] = {}
    for key, value in pairs:
        if key in values:
            raise LocalResearchSnapshotBlocked("Duplicate JSON key")
        values[key] = value
    return values


def read_private_local_research_snapshot(directory: Path) -> dict[str, object]:
    """Read and verify a bounded local status packet; NEVER imply owner auth."""
    folder_fd = _open_private_directory(directory)
    try:
        original_path = _check_existing_entry(folder_fd)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        flags |= getattr(os, "O_NONBLOCK", 0)
        fd = os.open(SNAPSHOT_FILENAME, flags, dir_fd=folder_fd)
        with os.fdopen(fd, "rb") as source:
            before = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_uid != os.getuid()
                or before.st_size > MAX_BYTES
                or original_path is None
                or (before.st_dev, before.st_ino)
                   != (original_path.st_dev, original_path.st_ino)
            ):
                raise LocalResearchSnapshotBlocked("Unsafe snapshot file")
            data = source.read(MAX_BYTES + 1)
            after = os.fstat(source.fileno())
        if (
            len(data) > MAX_BYTES
            or len(data) != before.st_size
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        ):
            raise LocalResearchSnapshotBlocked("Source file altered during read")
        final_path = _check_existing_entry(folder_fd)
        if (
            final_path is None
            or (final_path.st_dev, final_path.st_ino, final_path.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
        ):
            raise LocalResearchSnapshotBlocked("Snapshot path identity changed")
        try:
            parsed = json.loads(data, object_pairs_hook=_reject_duplicate_keys)
        except (ValueError, UnicodeDecodeError, TypeError) as exc:
            raise LocalResearchSnapshotBlocked("Malformed research status JSON") from exc
        if (
            type(parsed) is not dict
            or _canon(parsed) != data
            or not validate_local_pwa_research_status(parsed)
        ):
            raise LocalResearchSnapshotBlocked("Untrusted, modified or privileged status JSON")
        return parsed
    finally:
        os.close(folder_fd)
