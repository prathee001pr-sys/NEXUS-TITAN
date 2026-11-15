"""Stage80 frozen GitHub PR graph + local F&O cutover preflight. NO MERGE."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.stage80_integration_candidate_gate import (
    Stage80CutoverBlocked, inspect_stage80_integration_candidate,
)

DEFAULT_SNAPSHOT = ROOT / "docs/STAGE80_FROZEN_OPEN_PR_SNAPSHOT_2026-11-04.json"
MAX_BYTES = 512_000


def _reject_duplicate_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate snapshot JSON property")
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError("Invalid JSON number " + value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN Stage80 NO-MERGE offline review")
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    args = parser.parse_args(argv)
    try:
        file = args.snapshot
        if (file.is_symlink() or not file.is_file()
                or not 0 < file.stat().st_size <= MAX_BYTES):
            raise ValueError("Bounded regular non-symlink PR snapshot required")
        report = inspect_stage80_integration_candidate(
            ROOT,
            frozen_snapshot=json.loads(
                file.read_text(encoding="utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            ),
        )
        output = asdict(report)
        output["mode"] = "STAGE80_FROZEN_PR_AND_LOCAL_FO_GATEWAY_NO_GO"
        print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
        return 0 if (
            report.graph_topology_locally_consistent
            and report.stage79_local_sqlite_cas_shape_locally_inspected
            and report.stage77_cooperative_cas_call_sites_locally_inspected == 3
            and not report.merge_authorized and not report.live_trading_enabled
            and report.broker_orders_transmitted == 0
        ) else 2
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError,
            Stage80CutoverBlocked) as exc:
        print(json.dumps({
            "mode": "STAGE80_FROZEN_PR_AND_LOCAL_FO_GATEWAY_NO_GO",
            "error": type(exc).__name__, "detail": str(exc)[:150],
            "merge_authorized": False, "live_trading_enabled": False,
            "paper_order_authorized": False, "broker_orders_transmitted": 0,
            "verdict": "STAGE80_INVALID_LOCAL_PRE_FLIGHT_NO_GO",
        }, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
