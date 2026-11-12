"""Stage 153: read-only, fail-closed provenance receipt for OHLCV CSV datasets.

This gate supplements existing candle/CSV quality checks; it does not authorize
strategy promotion, order placement, or live trading.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from nexus_titan.data.csv_ohlcv import validate_ohlcv_csv


@dataclass(frozen=True, slots=True)
class DatasetGateReceipt:
    sha256: str
    bytes_checked: int
    rows_checked: int
    accepted: bool
    errors: tuple[str, ...]


def inspect_historical_csv(path: str | Path, *, max_bytes: int = 100_000_000) -> DatasetGateReceipt:
    """Validate a bounded regular file and produce a reproducible SHA-256 receipt.

    Symlinks, missing/empty files and oversized inputs fail closed. A passing
    receipt only establishes CSV structure and basic OHLCV checks, not market
    provenance, exchange completeness, or suitability for trading.
    """
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        raise ValueError("max_bytes must be a positive integer")
    file_path = Path(path)
    if file_path.is_symlink() or not file_path.is_file():
        return DatasetGateReceipt("", 0, 0, False, ("regular non-symlink file required",))
    try:
        size = file_path.stat().st_size
        if size == 0 or size > max_bytes:
            return DatasetGateReceipt("", size, 0, False, ("file size outside allowed bounds",))
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        # Detect modifications during the read, rather than certifying a moving target.
        if file_path.stat().st_size != size:
            return DatasetGateReceipt("", size, 0, False, ("file changed during inspection",))
        report = validate_ohlcv_csv(file_path)
        if file_path.stat().st_size != size:
            return DatasetGateReceipt("", size, report.rows_checked, False, ("file changed during inspection",))
        return DatasetGateReceipt(digest.hexdigest(), size, report.rows_checked, report.is_valid, report.errors)
    except OSError:
        return DatasetGateReceipt("", 0, 0, False, ("file could not be inspected",))
