"""Stage26 offline CLI for per-contract historical option-chain bundle preflight.

Vendor files and metadata are operator-supplied; a successful run NEVER
authenticates NSE source, vendor licensing, or permits broker operations.
Usage:
  python scripts/run_stage26_fo_bundle_preflight.py --root ./data/vendor-contract \
      --declaration ./my-contract-manifest.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.data.historical_fo_bundle import (
    HistoricalBundleDeclaration, HistoricalSnapshotFile,
    load_declared_historical_option_chain_bundle,
)
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import nse_equity_derivatives_baseline


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest JSON field: {key}")
        result[key] = value
    return result


def _load_manifest(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024:
        raise ValueError("Manifest must be a regular non-symlink JSON file <=128 KiB")
    document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    if not isinstance(document, dict):
        raise ValueError("Manifest JSON root must be object")
    return document


def _parsed(manifest: dict[str, object]):
    raw = manifest["contract"]
    if not isinstance(raw, dict):
        raise ValueError("contract must be an object")
    spec = PointInTimeContractSpec(
        symbol=raw["symbol"], underlying=raw["underlying"], exchange=raw["exchange"],
        segment=raw["segment"], lot_size=raw["lot_size"], tick_size=raw["tick_size"],
        freeze_quantity=raw["freeze_quantity"],
        effective_from=date.fromisoformat(raw["effective_from"]),
        effective_to=date.fromisoformat(raw["effective_to"]),
        expiry_date=date.fromisoformat(raw["expiry_date"]),
        strike_step=raw["strike_step"], max_lots_per_trade=raw["max_lots_per_trade"],
        source_reference=raw["source_reference"], source_verified=raw["source_verified"],
    )
    raw_files = manifest["snapshots"]
    if not isinstance(raw_files, list) or not 1 <= len(raw_files) <= 2000:
        raise ValueError("snapshots must be nonempty bounded list")
    files = tuple(
        HistoricalSnapshotFile(
            filename=x["filename"], observed_at=datetime.fromisoformat(x["observed_at"]),
            sha256=x["sha256"],
        ) for x in raw_files
    )
    declaration = HistoricalBundleDeclaration(
        dataset_id=manifest["dataset_id"],
        underlying=manifest["underlying"],
        provider_reference=manifest["provider_reference"],
        licence_reference=manifest["licence_reference"],
        calendar_reference=manifest["calendar_reference"],
        contract_reference=manifest["contract_reference"],
        declared_start=datetime.fromisoformat(manifest["declared_start"]),
        declared_end=datetime.fromisoformat(manifest["declared_end"]),
        snapshots=files,
        source_review_reference=manifest.get("source_review_reference", ""),
        dataset_class_claim=manifest.get("dataset_class_claim", "UNVERIFIED_RESEARCH_SAMPLE"),
    )
    raw_holidays = manifest.get("declared_holidays", [])
    if not isinstance(raw_holidays, list) or len(raw_holidays) > 3660:
        raise ValueError("declared_holidays must be bounded list")
    holidays = frozenset(date.fromisoformat(item) for item in raw_holidays)
    # Baseline is an OPERATOR declaration, NOT automatically authentic NSE calendar.
    calendar = nse_equity_derivatives_baseline(holidays=holidays)
    return declaration, spec, calendar


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN research-only F&O source preflight")
    parser.add_argument("--root", required=True, help="Directory of exact operator-supplied snapshot CSV files")
    parser.add_argument("--declaration", required=True, help="JSON manifest with operator-supplied SHA-256 for each CSV")
    args = parser.parse_args()
    try:
        manifest = _load_manifest(Path(args.declaration))
        declaration, contract, calendar = _parsed(manifest)
        result = load_declared_historical_option_chain_bundle(
            args.root, declaration=declaration, contract=contract, calendar=calendar,
        )
        report = {
            "mode": "STRUCTURAL_RESEARCH_ONLY",
            "dataset_id": result.preflight.dataset_id,
            "underlying": result.preflight.underlying,
            "snapshot_count": result.preflight.snapshot_count,
            "expected_slots": result.preflight.expected_slots,
            "file_sha256": dict(result.preflight.source_file_sha256),
            "self_declared_licence_or_vendor_authenticated": False,
            "official_exchange_metadata_authenticated": False,
            "exchange_calendar_authenticated": False,
            "backtest_profits_verified": False,
            "broker_orders_sent": 0,
            "strategy_promotion_allowed": False,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"STAGE26 PREFLIGHT BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
