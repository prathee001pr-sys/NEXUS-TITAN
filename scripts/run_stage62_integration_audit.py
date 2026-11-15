"""Stage62 read-only candidate integration preflight CLI.

Usage:
    python scripts/run_stage62_integration_audit.py
    python scripts/run_stage62_integration_audit.py --snapshot docs/my-pr-export.json

Prints a NO-GO structural review. A zero exit status ONLY means the
selected local source/workflow contracts were inspectable; it NEVER
authorizes a merge, production release, paper fill or live trade.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.integration_candidate_audit import (
    inspect_stage62_candidate,
)
from nexus_titan.operations.pr_stack_audit import StackAuditError

DEFAULT_SNAPSHOT = ROOT / "docs" / "STAGE62_PR_DEPENDENCY_SNAPSHOT_2026-11-03.json"
MAX_BYTES = 512 * 1024


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def _reject_constant(token: str):
    raise ValueError("NaN/Infinity not allowed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN Stage62 offline no-merge audit")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        path = args.snapshot
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= MAX_BYTES):
            raise ValueError("Bounded regular non-symlink PR snapshot required")
        raw = path.read_bytes()
        if len(raw) > MAX_BYTES or not raw:
            raise ValueError("Oversized or empty PR snapshot")
        snapshot = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_keys,
            parse_constant=_reject_constant,
        )
        result = inspect_stage62_candidate(args.root, pr_snapshot=snapshot)
        payload = asdict(result)
        payload["mode"] = "STAGE62_FROZEN_SNAPSHOT_NO_MERGE_LOCAL_AST_ONLY"
        print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
        return 0 if result.local_static_review_passed else 2
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError, StackAuditError) as exc:
        print(json.dumps({
            "mode": "STAGE62_FROZEN_SNAPSHOT_NO_MERGE_LOCAL_AST_ONLY",
            "local_static_review_passed": False,
            "merge_authorized": False,
            "production_ready": False,
            "real_money_trading_enabled": False,
            "broker_orders_transmitted": 0,
            "error": type(exc).__name__,
            "detail": str(exc)[:200],
        }, indent=2, sort_keys=True), file=sys.stdout)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
