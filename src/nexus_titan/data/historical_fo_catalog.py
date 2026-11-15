"""Stage 44: offline, bounded multi-contract historical F&O catalog preflight.

Each partition is independently checked by the Stage26 per-contract importer.
A green structural catalog is NOT proof of vendor identity, licence, historical
exchange metadata, quote depth, execution realism or trading readiness.
There is no network, write, broker, order, strategy or dashboard integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Sequence

from nexus_titan.data.historical_fo_bundle import (
    HistoricalBundleDeclaration,
    HistoricalBundleResearchResult,
    load_declared_historical_option_chain_bundle,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import MarketCalendar


class HistoricalCatalogError(ValueError):
    """The complete multi-contract catalog is rejected without partial results."""


@dataclass(frozen=True, slots=True)
class HistoricalContractPartition:
    """Operator-declared partition; references are claims, not authenticated evidence."""

    root: str | Path
    declaration: HistoricalBundleDeclaration
    contract: PointInTimeContractSpec
    calendar: MarketCalendar


@dataclass(frozen=True, slots=True)
class HistoricalCatalogResult:
    partitions: tuple[HistoricalBundleResearchResult, ...]
    dataset_count: int
    snapshot_count: int
    unique_contracts: int
    first_observed_at: datetime
    last_observed_at: datetime
    # These flags can never become true merely because declared bytes passed QA.
    external_source_authenticated: bool = False
    licence_authenticated: bool = False
    point_in_time_exchange_metadata_authenticated: bool = False
    exchange_calendar_authenticated: bool = False
    full_market_history_coverage_verified: bool = False
    realistic_fo_backtest_verified: bool = False
    strategy_promotion_allowed: bool = False
    live_orders_transmitted: int = 0


def _bound(name: str, value: int, upper: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= upper:
        raise HistoricalCatalogError(f"{name} must be an integer in [1, {upper}]")


def _date_at_market(t: datetime, calendar: MarketCalendar) -> date:
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
        raise HistoricalCatalogError("Partition dates must be timezone-aware")
    return t.astimezone(calendar.zone).date()


def preflight_historical_fo_catalog(
    partitions: Sequence[HistoricalContractPartition],
    *,
    max_partitions: int = 32,
    max_total_snapshots: int = 5000,
    max_total_source_bytes: int = 256 * 1024 * 1024,
) -> HistoricalCatalogResult:
    """Check contract identity, effective dates, overlap, provenance and all CSVs.

    The scope is deliberately a bounded subset, NOT a fifteen-year full-universe
    NSE index F&O database. Dates outside each explicitly supplied partition
    are never inferred as complete. Stage26 checks the within-partition minute
    grid; no external source/holiday/metadata authentication is performed.
    """
    _bound("max_partitions", max_partitions, 128)
    _bound("max_total_snapshots", max_total_snapshots, 20000)
    _bound("max_total_source_bytes", max_total_source_bytes, 1024 * 1024 * 1024)
    if not isinstance(partitions, (tuple, list)) or not 1 <= len(partitions) <= max_partitions:
        raise HistoricalCatalogError("A bounded nonempty list/tuple of partitions is required")

    seen_dataset_ids: set[str] = set()
    seen_digests: set[str] = set()
    contract_windows: dict[tuple[str, str, date], list[tuple[datetime, datetime]]] = {}
    outputs: list[HistoricalBundleResearchResult] = []
    count = 0
    total_bytes = 0
    earliest: datetime | None = None
    latest: datetime | None = None

    for index, item in enumerate(partitions):
        if not isinstance(item, HistoricalContractPartition):
            raise HistoricalCatalogError(f"Partition {index}: invalid partition type")
        declaration, contract, calendar = item.declaration, item.contract, item.calendar
        if (not isinstance(declaration, HistoricalBundleDeclaration)
                or not isinstance(contract, PointInTimeContractSpec)
                or not isinstance(calendar, MarketCalendar)
                or calendar.timezone_name != "Asia/Kolkata"):
            raise HistoricalCatalogError(f"Partition {index}: missing typed declaration, contract or NSE calendar")
        if declaration.dataset_id in seen_dataset_ids:
            raise HistoricalCatalogError(f"Partition {index}: duplicate dataset_id")
        seen_dataset_ids.add(declaration.dataset_id)
        if not isinstance(contract.expiry_date, date):
            raise HistoricalCatalogError(f"Partition {index}: explicit expiry_date is required")
        first_day = _date_at_market(declaration.declared_start, calendar)
        last_day = _date_at_market(declaration.declared_end, calendar)
        if not (contract.effective_from <= first_day <= last_day <= contract.effective_to):
            raise HistoricalCatalogError(f"Partition {index}: outside contract metadata effective window")
        if not (first_day <= last_day <= contract.expiry_date):
            raise HistoricalCatalogError(f"Partition {index}: observations past contract expiry")
        if not contract.symbol.strip():
            raise HistoricalCatalogError(f"Partition {index}: contract symbol missing")
        key = (declaration.underlying, contract.symbol, contract.expiry_date)
        start = declaration.declared_start.astimezone(timezone.utc)
        end = declaration.declared_end.astimezone(timezone.utc)
        if end < start:
            raise HistoricalCatalogError(f"Partition {index}: reversed observation window")
        for prior_start, prior_end in contract_windows.get(key, []):
            if start <= prior_end and prior_start <= end:
                raise HistoricalCatalogError(f"Partition {index}: overlapping same-contract observation window")
        contract_windows.setdefault(key, []).append((start, end))

        count += len(declaration.snapshots) if isinstance(declaration.snapshots, tuple) else max_total_snapshots + 1
        if count > max_total_snapshots:
            raise HistoricalCatalogError("Combined snapshot count exceeds limit")

        # Stage26 performs hash-verified reads, quote consistency, calendar
        # alignment and in-window continuity. Never bypass it.
        output = load_declared_historical_option_chain_bundle(
            item.root,
            declaration=declaration,
            contract=contract,
            calendar=calendar,
        )
        base = Path(item.root).resolve(strict=True)
        for filename, digest in output.preflight.source_file_sha256:
            if digest in seen_digests:
                raise HistoricalCatalogError(f"Partition {index}: replayed source hash across partitions")
            seen_digests.add(digest)
            # The original Stage26 importer already bans links/traversal.
            total_bytes += (base / filename).stat().st_size
            if total_bytes > max_total_source_bytes:
                raise HistoricalCatalogError("Combined source byte budget exceeded")
        outputs.append(output)
        earliest = start if earliest is None else min(earliest, start)
        latest = end if latest is None else max(latest, end)

    assert earliest is not None and latest is not None
    return HistoricalCatalogResult(
        partitions=tuple(outputs),
        dataset_count=len(outputs),
        snapshot_count=count,
        unique_contracts=len(contract_windows),
        first_observed_at=earliest,
        last_observed_at=latest,
    )
