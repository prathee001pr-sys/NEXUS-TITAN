"""Stage 26: bounded, local, fail-closed historical NSE option-chain bundle preflight.

The caller supplies vendor files, declared SHA-256 digests, point-in-time
contract metadata and trading calendar. These are *not* independently trusted.
Structural acceptance is NOT a licensed data or production trading approval.
No network connections, broker orders, file writes or strategy promotion.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import (
    OptionChainIngestionError, load_research_option_chain_csv,
)
from nexus_titan.data.option_chain_history import (
    ResearchOptionChainHistory, OptionChainHistoryError,
    assemble_research_option_chain_history,
)
from nexus_titan.data.sessions import MarketCalendar


class HistoricalBundleError(ValueError):
    """Entire operator-supplied F&O dataset failed preflight; nothing released."""


@dataclass(frozen=True, slots=True)
class HistoricalSnapshotFile:
    filename: str  # basename only; never an arbitrary read path
    observed_at: datetime
    sha256: str


@dataclass(frozen=True, slots=True)
class HistoricalBundleDeclaration:
    dataset_id: str
    underlying: str  # strictly NIFTY or BANKNIFTY
    provider_reference: str
    licence_reference: str
    calendar_reference: str
    contract_reference: str
    declared_start: datetime
    declared_end: datetime
    snapshots: tuple[HistoricalSnapshotFile, ...]
    source_review_reference: str = ""
    dataset_class_claim: str = "UNVERIFIED_RESEARCH_SAMPLE"


@dataclass(frozen=True, slots=True)
class HistoricalBundlePreflight:
    dataset_id: str
    underlying: str
    snapshot_count: int
    expected_slots: int
    first_observed_at: datetime
    last_observed_at: datetime
    source_file_sha256: tuple[tuple[str, str], ...]
    source_licence_authenticated: bool = False
    exchange_metadata_authenticated: bool = False
    exchange_calendar_authenticated: bool = False
    external_vendor_verified: bool = False
    real_market_backtest_verified: bool = False
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


@dataclass(frozen=True, slots=True)
class HistoricalBundleResearchResult:
    preflight: HistoricalBundlePreflight
    history: ResearchOptionChainHistory


def _reference(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise HistoricalBundleError(f"Missing or invalid declared {name}")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise HistoricalBundleError(f"{name} requires timezone-aware ISO timestamp")
    return value.astimezone(timezone.utc)


def _integer(value: int, name: str, *, minimum: int, maximum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise HistoricalBundleError(f"{name} must be a bounded positive integer")


def load_declared_historical_option_chain_bundle(
    root: str | Path,
    *,
    declaration: HistoricalBundleDeclaration,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    max_files: int = 500,
    max_file_bytes: int = 8 * 1024 * 1024,
    max_total_bytes: int = 64 * 1024 * 1024,
    interval_minutes: int = 1,
) -> HistoricalBundleResearchResult:
    """Verify exact declared *per-contract* observation window, files and QA.

    A 'LICENSED_EXCHANGE_HISTORY' declaration is merely an assertion, never
    verifiable licence proof. This routine cannot approve/promote ANY input.
    Sessions outside first and last declared timestamp are NOT checked; for
    an entire market day the caller must supply start/open and end/last grid
    slot explicitly. A single expiry/contract must not span historical lot
    size revisions or changing expiry terms.
    """
    if not isinstance(declaration, HistoricalBundleDeclaration):
        raise HistoricalBundleError("HistoricalBundleDeclaration required")
    if not isinstance(contract, PointInTimeContractSpec):
        raise HistoricalBundleError("PointInTimeContractSpec required")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise HistoricalBundleError("Asia/Kolkata calendar required")
    for name, val, bound in (
        ("max_files", max_files, 2000),
        ("max_file_bytes", max_file_bytes, 64 * 1024 * 1024),
        ("max_total_bytes", max_total_bytes, 512 * 1024 * 1024),
        ("interval_minutes", interval_minutes, 120),
    ):
        _integer(val, name, minimum=1, maximum=bound)
    if max_file_bytes > max_total_bytes:
        raise HistoricalBundleError("max_file_bytes exceeds max_total_bytes")
    _reference(declaration.dataset_id, "dataset_id")
    for n in ("provider_reference", "licence_reference", "calendar_reference",
              "contract_reference"):
        _reference(getattr(declaration, n), n)
    if not isinstance(declaration.source_review_reference, str):
        raise HistoricalBundleError("source_review_reference must be string")
    if declaration.dataset_class_claim not in (
        "SYNTHETIC_SMOKE_FIXTURE", "UNVERIFIED_RESEARCH_SAMPLE",
        "LICENSED_EXCHANGE_HISTORY",
    ):
        raise HistoricalBundleError("Invalid dataset_class_claim")
    if (not isinstance(declaration.underlying, str)
            or declaration.underlying not in ("NIFTY", "BANKNIFTY")
            or contract.exchange.upper() != "NSE" or contract.segment != "OPTIONS"
            or contract.underlying != declaration.underlying
            or contract.source_verified is not True
            or contract.source_reference != declaration.contract_reference):
        raise HistoricalBundleError("Per-expiry NSE NIFTY/BANKNIFTY OPTIONS contract identity or declaration mismatch")
    start = _aware(declaration.declared_start, "declared_start")
    end = _aware(declaration.declared_end, "declared_end")
    if start > end:
        raise HistoricalBundleError("declared_start exceeds declared_end")
    if not calendar.is_open(declaration.declared_start) or not calendar.is_open(declaration.declared_end):
        raise HistoricalBundleError("Declared observations outside supplied exchange sessions")
    if not isinstance(declaration.snapshots, tuple):
        raise HistoricalBundleError("Snapshot manifest must be immutable tuple")
    if not 1 <= len(declaration.snapshots) <= min(max_files, 2000):
        raise HistoricalBundleError("Snapshot count is missing or exceeds bounded limit")
    if len(declaration.snapshots) > (max_total_bytes // 1):
        raise HistoricalBundleError("Snapshot entry count exceeds allowed bytes")
    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise HistoricalBundleError("Nonempty local root directory required")
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise HistoricalBundleError("Existing non-symlink root directory required")
    base = base.resolve(strict=True)

    seen_names: set[str] = set()
    seen_instants: set[datetime] = set()
    snapshots = []
    file_hashes = []
    used_bytes = 0
    previous: datetime | None = None
    for idx, entry in enumerate(declaration.snapshots):
        if not isinstance(entry, HistoricalSnapshotFile):
            raise HistoricalBundleError(f"Entry {idx}: HistoricalSnapshotFile required")
        if (not isinstance(entry.filename, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.csv", entry.filename
        ) or entry.filename in (".csv", "..csv")):
            raise HistoricalBundleError(f"Entry {idx}: only plain CSV basenames allowed")
        if entry.filename in seen_names:
            raise HistoricalBundleError(f"Entry {idx}: duplicate filename")
        seen_names.add(entry.filename)
        if not isinstance(entry.sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", entry.sha256):
            raise HistoricalBundleError(f"Entry {idx}: invalid declared SHA-256")
        moment = _aware(entry.observed_at, f"Entry {idx} observed_at")
        if moment in seen_instants or (previous is not None and moment <= previous):
            raise HistoricalBundleError(f"Entry {idx}: replayed, duplicate or out-of-order observation")
        previous = moment
        seen_instants.add(moment)
        if not start <= moment <= end:
            raise HistoricalBundleError(f"Entry {idx}: snapshot outside declared boundary")

        target = base / entry.filename
        if target.is_symlink() or not target.is_file() or target.resolve().parent != base:
            raise HistoricalBundleError(f"Entry {idx}: missing, linked or escaped source file")
        size = target.stat().st_size
        used_bytes += size
        if size > max_file_bytes or used_bytes > max_total_bytes:
            raise HistoricalBundleError("Historical source exceeds per-file or total size budget")
        # Each importer rehashes the original bytes and independently checks
        # quote identity, bid/ask coherence, timestamps and exchange session.
        snap = load_research_option_chain_csv(
            target,
            expected_sha256=entry.sha256,
            contract=contract,
            observed_at=entry.observed_at,
            calendar=calendar,
            provider_reference=declaration.provider_reference,
            licence_evidence_reference=declaration.licence_reference,
            calendar_evidence_reference=declaration.calendar_reference,
            max_file_bytes=max_file_bytes,
        )
        snapshots.append(snap)
        file_hashes.append((entry.filename, snap.sha256))
    if seen_instants != {start, end} and (previous != end or snapshots[0].observed_at.astimezone(timezone.utc) != start):
        raise HistoricalBundleError("First/last source timestamps don't match declared coverage boundaries")
    if snapshots[0].observed_at.astimezone(timezone.utc) != start or previous != end:
        raise HistoricalBundleError("First/last snapshots must exactly match declared window")
    # Existing Stage16-18 time-grid quality rejects all missing in-window minutes.
    history = assemble_research_option_chain_history(
        snapshots, contract=contract, calendar=calendar,
        interval_minutes=interval_minutes, max_snapshots=max_files,
        max_expected_slots=max_files, max_calendar_days=366,
    )
    # Protect against files changed mid-audit. No success if original digests
    # change after the importer read (e.g. another process overwrites source).
    for name, expected in file_hashes:
        current = hashlib.sha256((base / name).read_bytes()).hexdigest()
        if not hmac.compare_digest(current, expected):
            raise HistoricalBundleError(f"Source changed during bundle verification: {name}")
    return HistoricalBundleResearchResult(
        preflight=HistoricalBundlePreflight(
            dataset_id=declaration.dataset_id, underlying=declaration.underlying,
            snapshot_count=len(snapshots), expected_slots=history.expected_slots,
            first_observed_at=declaration.declared_start,
            last_observed_at=declaration.declared_end,
            source_file_sha256=tuple(file_hashes),
        ),
        history=history,
    )
