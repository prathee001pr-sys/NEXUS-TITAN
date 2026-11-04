"""Stage70 offline-only static F&O integration review; no network or trades."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.stage70_fo_integration_gate import (
    Stage70AuditBlocked, inspect_stage70_fo_integration,
)


def main() -> int:
    try:
        audit = inspect_stage70_fo_integration(ROOT)
    except Stage70AuditBlocked as exc:
        print(json.dumps({"status": "STATIC_AUDIT_BLOCKED", "detail": str(exc),
                          "release": "NO_GO"}, sort_keys=True))
        return 2
    print(json.dumps(asdict(audit), indent=2, sort_keys=True, allow_nan=False))
    return 0 if (
        audit.static_inventory_complete
        and len(audit.observed_execution_entrypoints) == 5
        and not audit.safe_to_merge
        and not audit.production_ready
        and not audit.live_trading_enabled
        and audit.broker_orders_transmitted == 0
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
