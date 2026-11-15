"""Stage67 PR3/PR5 byte-level reconciliation preflight (NO-MERGE)."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.stage67_calibration_reconcile import (
    Stage67LineageError, inspect_stage67_calibration_reconciliation,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="PR3/PR5 research calibration lineage no-go audit")
    p.add_argument("--repo-root", type=Path, default=ROOT)
    args = p.parse_args(argv)
    try:
        audit = inspect_stage67_calibration_reconciliation(args.repo_root)
        payload = asdict(audit)
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0 if audit.frozen_source_lineage_check_passed else 2
    except (Stage67LineageError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "scope": "STAGE67_MANUAL_CALIBRATION_LINEAGE_CANDIDATE_OFFLINE_NO_GO",
            "frozen_source_lineage_check_passed": False,
            "merge_authorized": False,
            "production_ready": False,
            "real_money_trading_enabled": False,
            "broker_orders_transmitted": 0,
            "error": type(exc).__name__,
            "detail": str(exc)[:180],
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
