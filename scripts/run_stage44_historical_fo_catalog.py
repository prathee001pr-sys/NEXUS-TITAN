"""Stage44 bounded local historical F&O catalog CLI. No network or trading.

Each manifest is in the existing Stage26 format. The outer catalog JSON contains
{"partitions": [{"directory": "part_a", "manifest": "part_a.json"}, ...]}.
All paths are strict local basenames under --catalog-root; no vendor bytes are
saved to GitHub. A passing report is structural QA ONLY, never source approval.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from scripts.run_stage26_fo_bundle_preflight import _load_manifest, _parsed
from nexus_titan.data.historical_fo_catalog import (
    HistoricalContractPartition,
    preflight_historical_fo_catalog,
)

_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


def _safe_child(root: Path, value: object) -> Path:
    if (not isinstance(value, str) or not _NAME.fullmatch(value)
            or value in (".", "..")):
        raise ValueError("Each partition path must be a plain basename")
    candidate = root / value
    if candidate.is_symlink() or candidate.resolve(strict=True).parent != root:
        raise ValueError("Linked or escaped partition path rejected")
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage44 offline multi-contract F&O preflight")
    parser.add_argument("--catalog-root", required=True, help="Local directory containing declared files")
    parser.add_argument("--catalog", required=True, help="Local bounded JSON catalog")
    args = parser.parse_args()
    try:
        root = Path(args.catalog_root)
        if root.is_symlink() or not root.is_dir():
            raise ValueError("catalog-root must be an existing non-symlink directory")
        root = root.resolve(strict=True)
        # The catalog itself may be in a distinct location; it must be an
        # existing, bounded non-symlink JSON file via the Stage26 parser.
        declared = _load_manifest(Path(args.catalog))
        entries = declared.get("partitions")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 32:
            raise ValueError("partitions must contain 1..32 declarations")
        parts = []
        for record in entries:
            if not isinstance(record, dict) or set(record) != {"directory", "manifest"}:
                raise ValueError("Each partition needs only directory and manifest")
            directory = _safe_child(root, record["directory"])
            manifest = _safe_child(root, record["manifest"])
            if not directory.is_dir() or not manifest.is_file():
                raise ValueError("Expected a regular partition directory and manifest JSON")
            declaration, contract, calendar = _parsed(_load_manifest(manifest))
            parts.append(HistoricalContractPartition(directory, declaration, contract, calendar))
        result = preflight_historical_fo_catalog(tuple(parts))
        print(json.dumps({
            "mode": "OFFLINE_STRUCTURAL_RESEARCH_ONLY",
            "dataset_count": result.dataset_count,
            "snapshot_count": result.snapshot_count,
            "unique_contracts": result.unique_contracts,
            "first_observed_at": result.first_observed_at.isoformat(),
            "last_observed_at": result.last_observed_at.isoformat(),
            "external_source_authenticated": False,
            "licence_authenticated": False,
            "point_in_time_exchange_metadata_authenticated": False,
            "exchange_calendar_authenticated": False,
            "full_market_history_coverage_verified": False,
            "realistic_fo_backtest_verified": False,
            "strategy_promotion_allowed": False,
            "live_orders_transmitted": 0,
        }, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
        print(f"STAGE44 CATALOG BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
