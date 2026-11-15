"""Stage 204: strictly time-ordered train/holdout index with an embargo.

Timestamp checks don't prove absence of leakage in upstream feature construction.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re


@dataclass(frozen=True, slots=True)
class FOObservationIndex:
    dataset_id: str
    observed_at: datetime
    subset: str  # TRAIN or HOLDOUT


@dataclass(frozen=True, slots=True)
class FOTemporalEmbargoReceipt:
    accepted_structurally: bool
    dataset_ids: tuple[str, ...]
    temporal_sha256: str
    train_count: int
    holdout_count: int
    blockers: tuple[str, ...]
    upstream_feature_leakage_audited: bool = False
    live_trading_authorized: bool = False
    observation_windows: tuple[tuple[str, str, str], ...] = ()


def audit_fo_temporal_embargo(
    points: tuple[FOObservationIndex, ...], *, embargo_minutes: int = 1440,
) -> FOTemporalEmbargoReceipt:
    if (not isinstance(points, tuple) or not 4 <= len(points) <= 10000
            or type(embargo_minutes) is not int or not 1 <= embargo_minutes <= 43200):
        return FOTemporalEmbargoReceipt(False, (), '', 0, 0, ('invalid bounded timeline or embargo',))
    errors = []; train = []; holdout = []; seen = set(); ids = set(); records = []
    dataset_times: dict[str, dict[str, list[datetime]]] = {}
    last = None
    for i, p in enumerate(points):
        if type(p) is not FOObservationIndex:
            errors.append(f'{i}: typed observation required'); continue
        if (not isinstance(p.dataset_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', p.dataset_id)
                or not isinstance(p.observed_at, datetime) or p.observed_at.utcoffset() is None
                or p.subset not in ('TRAIN', 'HOLDOUT')):
            errors.append(f'{i}: invalid dataset, timestamp or split'); continue
        at = p.observed_at.astimezone(timezone.utc)
        key = (p.dataset_id, at)
        if key in seen: errors.append(f'{i}: duplicate dataset timestamp')
        if last is not None and at <= last: errors.append(f'{i}: input not strictly time ordered')
        seen.add(key); last = at; ids.add(p.dataset_id)
        (train if p.subset == 'TRAIN' else holdout).append(at)
        dataset_times.setdefault(p.dataset_id, {'TRAIN': [], 'HOLDOUT': []})[p.subset].append(at)
        records.append((p.dataset_id, at.isoformat(), p.subset))
    if len(train) < 2 or len(holdout) < 2:
        errors.append('at least two train and two holdout samples required')
    if train and holdout:
        if max(train) >= min(holdout): errors.append('train/holdout overlap or interleave')
        elif min(holdout) - max(train) < timedelta(minutes=embargo_minutes):
            errors.append('embargo gap not respected')
    if any(x[2] == 'TRAIN' for x in records[len(train):]):
        errors.append('train records after holdout boundary')
    for dataset, parts in dataset_times.items():
        if len(parts['TRAIN']) < 2 or len(parts['HOLDOUT']) < 2:
            errors.append(f'{dataset}: requires two train and holdout observations')
        elif min(parts['HOLDOUT'])-max(parts['TRAIN']) < timedelta(minutes=embargo_minutes):
            errors.append(f'{dataset}: embargo gap not respected')
    digest = hashlib.sha256(json.dumps({'points':records,'embargo_minutes':embargo_minutes},separators=(',',':'),sort_keys=True).encode()).hexdigest() if not errors else ''
    windows=tuple(sorted((dataset, min(parts['TRAIN']+parts['HOLDOUT']).isoformat(),
                               max(parts['TRAIN']+parts['HOLDOUT']).isoformat())
                              for dataset,parts in dataset_times.items())) if not errors else ()
    return FOTemporalEmbargoReceipt(not errors,tuple(sorted(ids)) if not errors else (),digest,len(train) if not errors else 0,len(holdout) if not errors else 0,tuple(errors),observation_windows=windows)
