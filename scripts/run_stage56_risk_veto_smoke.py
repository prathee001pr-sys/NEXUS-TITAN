"""Stage56 offline brokerless risk-screen and bypass-inventory smoke.

Run a strict one-shot subprocess on two fabricated synthetic BUY proposals.
A local pass is *never* trade approval; the known legacy Python entrypoints
remain accessible. No broker credentials, market feed, order or fill writes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.risk_boundary_inventory import (
    inspect_stage56_bypass_paths,
)


def _request(kill: bool) -> dict:
    return {
        "schema_version": 1,
        "intent": {
            "request_id": "S56-QA-BUY-ONE",
            "symbol": "QAABC",
            "quantity": 3,
            "limit_price_cents": 10000,
            "stop_price_cents": 9500,
            "fee_buffer_cents": 100,
            "instrument_type": "EQUITY_DELIVERY",
            "side": "BUY",
        },
        "quote": {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "bid_cents": 9995,
            "ask_cents": 10000,
            "ask_depth_units": 15,
            "expected_slippage_bps": 5,
            "expected_edge_bps": 40,
            "source_reference": "SYNTHETIC/LOCAL_QA",
        },
        "account": {
            "account_id": "S56-QA",
            "initial_cents": 5000000,
            "available_cents": 5000000,
            "already_reserved_cents": 0,
            "daily_realized_loss_bps": 0,
            "current_drawdown_bps": 0,
            "consecutive_losses": 0,
            "kill_switch_active": kill,
            "risk_module_healthy": True,
        },
    }


def _run(kind: bool) -> dict:
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_stage56_brokerless_risk_gate.py")],
        input=json.dumps(_request(kind)), capture_output=True,
        text=True, cwd=ROOT, timeout=15, check=False,
    )
    if p.returncode:
        raise RuntimeError("Stage56 local QA subprocess rejected its own synthetic fixture")
    return json.loads(p.stdout)


def main() -> int:
    passed = _run(False)
    denied = _run(True)
    scanned = inspect_stage56_bypass_paths(ROOT)
    result = {
        "mode": "STAGE56_BROKERLESS_LOCAL_RISK_QA",
        "accepted_local_qa_screen": passed["local_synthetic_screen_passed"],
        "kill_switch_vetoed": (
            not denied["local_synthetic_screen_passed"]
            and "KILL_SWITCH_ACTIVE" in denied["blockers"]
        ),
        "legacy_entrypoints_still_exposed": (
            "VirtualAccount.execute_fill" in scanned.known_callable_surfaces
            and "VirtualAccount.submit_order" in scanned.known_callable_surfaces
        ),
        "structural_source_scan_complete": scanned.local_static_scan_complete,
        "global_risk_enforced": False,
        "trusted_market_feed_connected": False,
        "independently_authenticated_human_identity": False,
        "order_submission_authorized": False,
        "live_orders_transmitted": 0,
        "production_ready": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if all((
        result["accepted_local_qa_screen"], result["kill_switch_vetoed"],
        result["legacy_entrypoints_still_exposed"],
        result["structural_source_scan_complete"],
        not result["global_risk_enforced"],
    )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
