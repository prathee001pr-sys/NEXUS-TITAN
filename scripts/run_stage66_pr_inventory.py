"""Inspect the Stage66 captured PR inventory — never merge or trade."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.stage66_pr_inventory import (
    Stage66InventoryError, inspect_stage66_inventory,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage66 frozen GitHub PR filename audit")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        review = inspect_stage66_inventory(args.repo_root)
        payload = asdict(review)
        payload["mode"] = "STAGE66_FROZEN_COMPLETE_PR_FILENAME_AUDIT_NO_MERGE"
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0 if review.graph_consistent_at_capture and review.frozen_file_list_coverage_complete else 2
    except (OSError, ValueError, TypeError, Stage66InventoryError) as exc:
        print(json.dumps({
            "mode": "STAGE66_FROZEN_COMPLETE_PR_FILENAME_AUDIT_NO_MERGE",
            "safe_to_merge": False,
            "production_ready": False,
            "live_trading_enabled": False,
            "broker_orders_transmitted": 0,
            "error": type(exc).__name__,
            "detail": str(exc)[:200],
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
