"""Stage78 source-only F&O gateway cutover audit; zero trading I/O."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.stage78_fo_gateway_cutover_audit import (
    Stage78CutoverBlocked, inspect_stage78_fo_cutover,
)


def main() -> int:
    try:
        report = inspect_stage78_fo_cutover(ROOT)
    except Stage78CutoverBlocked as exc:
        print(json.dumps({
            "mode": "STAGE78_OFFLINE_SOURCE_AUDIT_BLOCKED",
            "reason": str(exc), "verdict": "NO_GO",
            "live_trading_enabled": False, "broker_orders_transmitted": 0,
        }, sort_keys=True))
        return 2
    print(json.dumps(asdict(report), indent=2, sort_keys=True, allow_nan=False))
    return 0 if (
        report.local_source_inventory_complete
        and report.local_stage77_expected_calls_observed
        and not report.all_legacy_order_fill_paths_fenced
        and not report.independent_global_risk_gateway_verified
        and not report.live_trading_enabled
        and report.broker_orders_transmitted == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
