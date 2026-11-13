"""Stage 201: read-only Stage44 catalog reconciliation for bounded Indian F&O data.

Neither catalogue acceptance nor this digest authenticates a market-data provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re

from .historical_fo_catalog import HistoricalCatalogResult
from .historical_fo_bundle import HistoricalBundleResearchResult

_HEX = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class FOCatalogInventoryReceipt:
    accepted_structurally: bool
    dataset_ids: tuple[str, ...]
    inventory_sha256: str
    snapshot_count: int
    blockers: tuple[str, ...]
    external_market_source_verified: bool = False
    historical_coverage_verified: bool = False
    live_trading_authorized: bool = False
    source_manifest_sha256: str = ''
    underlyings: tuple[str, ...] = ()
    observation_windows: tuple[tuple[str, str, str], ...] = ()


def audit_fo_catalog_inventory(catalog: HistoricalCatalogResult) -> FOCatalogInventoryReceipt:
    errors: list[str] = []
    ids: list[str] = []
    records: list[dict] = []
    source_records: list[tuple[str, str, str]] = []
    if type(catalog) is not HistoricalCatalogResult:
        return FOCatalogInventoryReceipt(False, (), '', 0, ('Stage44 catalog receipt required',))
    if (type(catalog.dataset_count) is not int or type(catalog.snapshot_count) is not int
            or type(catalog.unique_contracts) is not int or not isinstance(catalog.partitions, tuple)
            or not 1 <= catalog.dataset_count <= 128 or catalog.dataset_count != len(catalog.partitions)
            or not 1 <= catalog.snapshot_count <= 20000 or not 1 <= catalog.unique_contracts <= catalog.dataset_count):
        errors.append('invalid catalog counts')
    for idx, part in enumerate(catalog.partitions[:129] if isinstance(catalog.partitions, tuple) else ()):
        if type(part) is not HistoricalBundleResearchResult:
            errors.append(f'{idx}: invalid Stage26 receipt'); continue
        pre = part.preflight
        try:
            name = pre.dataset_id
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', name):
                raise ValueError('invalid dataset_id')
            if name in ids: raise ValueError('duplicate dataset_id')
            if pre.underlying not in ('NIFTY', 'BANKNIFTY'): raise ValueError('unsupported underlying')
            if (type(pre.snapshot_count) is not int or not 1 <= pre.snapshot_count <= 20000
                    or type(pre.expected_slots) is not int or pre.expected_slots < pre.snapshot_count):
                raise ValueError('invalid snapshot count')
            start, end = pre.first_observed_at, pre.last_observed_at
            if not isinstance(start, datetime) or not isinstance(end, datetime) or start.utcoffset() is None or end.utcoffset() is None or start > end:
                raise ValueError('invalid timezone-aware observation window')
            hashes = pre.source_file_sha256
            if not isinstance(hashes, tuple) or len(hashes) != pre.snapshot_count:
                raise ValueError('invalid source manifest length')
            seen = set()
            for filename, digest in hashes:
                if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.csv', filename) or filename in seen or not isinstance(digest, str) or not _HEX.fullmatch(digest):
                    raise ValueError('invalid file hash manifest')
                seen.add(filename)
                source_records.append((name, filename, digest))
            ids.append(name)
            records.append({'id': name, 'underlying': pre.underlying, 'n': pre.snapshot_count,
                            'start': start.astimezone(timezone.utc).isoformat(),
                            'end': end.astimezone(timezone.utc).isoformat(),
                            'files': sorted(hashes)})
        except (TypeError, ValueError, AttributeError) as exc:
            errors.append(f'{idx}: {exc}')
    if not errors and (sum(item['n'] for item in records) != catalog.snapshot_count
                       or catalog.first_observed_at != min(datetime.fromisoformat(x['start']) for x in records)
                       or catalog.last_observed_at != max(datetime.fromisoformat(x['end']) for x in records)):
        errors.append('catalog aggregate mismatch')
    digest = hashlib.sha256(json.dumps(sorted(records, key=lambda x:x['id']), sort_keys=True, separators=(',', ':')).encode()).hexdigest() if not errors else ''
    source_manifest = hashlib.sha256(json.dumps(sorted(source_records), separators=(',', ':')).encode()).hexdigest() if not errors else ''
    return FOCatalogInventoryReceipt(not errors, tuple(sorted(ids)) if not errors else (), digest,
                                      catalog.snapshot_count if not errors else 0, tuple(errors),
                                      source_manifest_sha256=source_manifest,
                                      underlyings=tuple(sorted({r["underlying"] for r in records})) if not errors else (),
                                      observation_windows=tuple(sorted((r["id"],r["start"],r["end"]) for r in records)) if not errors else ())
