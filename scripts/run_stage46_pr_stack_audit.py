"""Stage46 offline PR stack snapshot audit CLI; never contacts GitHub or merges.

Usage: python scripts/run_stage46_pr_stack_audit.py
       python scripts/run_stage46_pr_stack_audit.py --snapshot path/to/export.json

Default input is the frozen GitHub read snapshot recorded for this stage.
Only snapshot validity is reported; a successful exit is NOT merge clearance.
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

from nexus_titan.operations.pr_stack_audit import (
    StackAuditError, inspect_pr_dependency_snapshot,
)

MAX_BYTES = 512 * 1024
DEFAULT_SNAPSHOT = ROOT / "docs" / "STAGE46_PR_STACK_SNAPSHOT_2026-11-03.json"


def _unique_json_keys(pairs: list[tuple[str, object]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise StackAuditError(f"Duplicate JSON property {key!r}")
        out[key] = value
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research-only read-only PR graph QA")
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    args = parser.parse_args(argv)
    try:
        path = Path(args.snapshot)
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise StackAuditError("Snapshot must be a 1..512KiB regular non-symlink JSON file")
        raw = path.read_bytes()
        if not 0 < len(raw) <= MAX_BYTES:
            raise StackAuditError("Snapshot exceeds byte budget")
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_json_keys)
        report = inspect_pr_dependency_snapshot(obj)
        # Normal successful analysis still flags release/merge NOT authorized.
        output = asdict(report)
        output["mode"] = "OFFLINE_PR_SNAPSHOT_REVIEW_ONLY"
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (OSError, UnicodeError, json.JSONDecodeError, StackAuditError) as exc:
        print(f"STAGE46 SNAPSHOT AUDIT BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
