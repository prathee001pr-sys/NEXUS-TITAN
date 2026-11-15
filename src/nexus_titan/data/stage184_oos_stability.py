"""Stage 184: bounded fold-level out-of-sample stability check, offline only.

The independent caller must verify all fold P&L and trade counts against real
immutable out-of-sample artifacts. A receipt does not certify profitability.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
import re
from .stage174_walkforward_purge import WalkForwardReceipt
from .stage176_quote_sanity import parse_amount

_SHA = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, slots=True)
class OOSFoldMetric:
    fold_number: int
    closed_trades: int
    profitable: bool
    net_pnl: str  # signed decimal, bounded by sign prefix
    max_drawdown_bps: int
    dataset_sha256: str


def signed_decimal(text: str) -> Decimal:
    if not isinstance(text, str):
        raise ValueError('invalid signed amount')
    return -parse_amount(text[1:]) if text.startswith('-') else parse_amount(text)


@dataclass(frozen=True, slots=True)
class OOSStabilityReceipt:
    accepted: bool
    checked_folds: int
    positive_fold_ratio_bps: int | None
    dataset_sha256: str
    blockers: tuple[str, ...]


def audit_oos_stability(metrics: tuple[OOSFoldMetric, ...], *, walkforward: WalkForwardReceipt,
                        dataset_sha256: str, min_trades_per_fold: int,
                        min_positive_fold_ratio_bps: int,
                        max_drawdown_bps: int,
                        metrics_independently_verified: bool) -> OOSStabilityReceipt:
    blockers: list[str] = []
    if (not isinstance(metrics, tuple) or not 2 <= len(metrics) <= 64
            or not isinstance(walkforward, WalkForwardReceipt) or not walkforward.accepted
            or walkforward.blockers or walkforward.folds_checked != len(metrics)):
        return OOSStabilityReceipt(False, 0, None, '', ('invalid or missing walk-forward evidence',))
    if metrics_independently_verified is not True:
        blockers.append('fold metrics not independently verified')
    if not isinstance(dataset_sha256, str) or not _SHA.fullmatch(dataset_sha256):
        blockers.append('invalid dataset digest')
    if (type(min_trades_per_fold) is not int or not 1 <= min_trades_per_fold <= 100_000
            or type(min_positive_fold_ratio_bps) is not int or not 0 <= min_positive_fold_ratio_bps <= 10_000
            or type(max_drawdown_bps) is not int or not 0 <= max_drawdown_bps <= 10_000):
        blockers.append('invalid policy bounds')
    positives = 0
    for i, metric in enumerate(metrics):
        if not isinstance(metric, OOSFoldMetric):
            blockers.append(f'fold {i}: invalid record')
            continue
        try:
            pnl = signed_decimal(metric.net_pnl)
            if (type(metric.fold_number) is not int or metric.fold_number != i
                    or type(metric.closed_trades) is not int or metric.closed_trades < 1
                    or type(metric.max_drawdown_bps) is not int
                    or not 0 <= metric.max_drawdown_bps <= 10_000
                    or type(metric.profitable) is not bool
                    or metric.profitable is not (pnl > 0)
                    or metric.dataset_sha256 != dataset_sha256):
                raise ValueError('invalid fold metric')
            if type(min_trades_per_fold) is int and metric.closed_trades < min_trades_per_fold:
                blockers.append(f'fold {i}: insufficient trade sample')
            if type(max_drawdown_bps) is int and metric.max_drawdown_bps > max_drawdown_bps:
                blockers.append(f'fold {i}: drawdown limit breached')
            positives += int(pnl > 0)
        except ValueError:
            blockers.append(f'fold {i}: invalid values or provenance')
    ratio = positives * 10_000 // len(metrics)
    if type(min_positive_fold_ratio_bps) is int and ratio < min_positive_fold_ratio_bps:
        blockers.append('insufficient positive-fold ratio')
    return OOSStabilityReceipt(not blockers, len(metrics), ratio, dataset_sha256 if isinstance(dataset_sha256, str) and _SHA.fullmatch(dataset_sha256) else '', tuple(blockers[:32]))
