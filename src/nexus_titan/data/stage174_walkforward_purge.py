"""Stage 174: chronological walk-forward fold and purging/embargo audit.

Caller must supply the training labels' FINAL availability timestamp; providing
only feature timestamps would not detect overlapping label horizons.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class Fold:
    train_start: datetime
    train_label_end: datetime
    test_start: datetime
    test_end: datetime


@dataclass(frozen=True, slots=True)
class WalkForwardReceipt:
    accepted: bool
    folds_checked: int
    blockers: tuple[str, ...]


def audit_walkforward_folds(
    folds: tuple[Fold, ...], *, embargo_minutes: int,
) -> WalkForwardReceipt:
    """Verify each fold's latest *label end* precedes its OOS test plus embargo."""
    if type(embargo_minutes) is not int or not 0 <= embargo_minutes <= 525_600:
        return WalkForwardReceipt(False, 0, ('invalid embargo',))
    if not isinstance(folds, tuple) or not 0 < len(folds) <= 64:
        return WalkForwardReceipt(False, 0, ('missing or oversized folds',))
    blockers: list[str] = []
    previous_test_end: datetime | None = None
    for idx, fold in enumerate(folds):
        if not isinstance(fold, Fold):
            blockers.append(f'fold {idx}: invalid fold')
            continue
        times = (fold.train_start, fold.train_label_end, fold.test_start, fold.test_end)
        if any(not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None for t in times):
            blockers.append(f'fold {idx}: timezone-aware timestamps required')
            continue
        train_start, label_end, test_start, test_end = (t.astimezone(timezone.utc) for t in times)
        if not train_start <= label_end < test_start <= test_end:
            blockers.append(f'fold {idx}: train/test time reversal or label leakage')
        if label_end < test_start and test_start - label_end <= timedelta(minutes=embargo_minutes):
            blockers.append(f'fold {idx}: insufficient label embargo')
        if previous_test_end is not None and test_start <= previous_test_end:
            blockers.append(f'fold {idx}: overlapping or nonchronological test windows')
        previous_test_end = test_end
    return WalkForwardReceipt(not blockers, len(folds), tuple(blockers[:32]))
