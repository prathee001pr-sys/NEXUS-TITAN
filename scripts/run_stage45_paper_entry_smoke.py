"""Stage45 brokerless read-only/synthetic paper entry smoke.

Run from repository root:
    python scripts/run_stage45_paper_entry_smoke.py

Creates temporary SQLite accounts only; no vendor CSV/ZIP, broker credentials,
live orders, external approval or cloud network traffic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.paper_deployment import (
    PaperDeploymentConfig, open_paper_only_deployment,
)
from nexus_titan.operations.offline_entry_readiness import (
    Stage45ConservativePaperEntry, Stage45EntryBlocked,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-s45-synthetic-") as temp:
        root = Path(temp)
        common = {
            "account_id": "S45-CLI-SYNTHETIC",
            "starting_capital": 50000.0,
            "virtual_state_dir": root / "virtual",
            "research_db_path": root / "research.sqlite3",
        }
        manual = lambda actor, target: actor == "SYNTHETIC_OPERATOR"
        closed = Stage45ConservativePaperEntry(open_paper_only_deployment(
            PaperDeploymentConfig(**common), approval_authorizer=manual,
        ))
        default_denied = not closed.status().can_create_new_synthetic_buy_intent
        opted_in = Stage45ConservativePaperEntry(open_paper_only_deployment(
            PaperDeploymentConfig(**common, paper_orders_enabled=True),
            approval_authorizer=manual,
        ))
        before = opted_in.status()
        first = opted_in.request_buy(
            symbol="TEST-SYNTHETIC", quantity=1,
            entry_price=100.0, stop_price=95.0,
        )
        parallel_denied = False
        try:
            opted_in.request_buy(
                symbol="TEST-OTHER", quantity=1,
                entry_price=100.0, stop_price=95.0,
            )
        except Stage45EntryBlocked:
            parallel_denied = True
        v = opted_in._deployment.virtual_account
        result = {
            "mode": "SYNTHETIC_OFFLINE_RESEARCH_ONLY",
            "default_denied": default_denied,
            "fresh_flat_opt_in_passed": before.can_create_new_synthetic_buy_intent,
            "first_intent_pending_manual_approval": first.status == "PENDING_APPROVAL",
            "second_parallel_intent_blocked": parallel_denied,
            "no_paper_fills": not any(order.fills for order in v.orders.values()),
            "externally_authenticated_human_approval": False,
            "cross_ledger_atomicity_verified": False,
            "global_risk_veto_independently_enforced": False,
            "real_market_data_authenticated": False,
            "extended_real_shadow_validation_verified": False,
            "strategy_promotion_allowed": False,
            "production_ready": False,
            "live_orders_transmitted": 0,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if all((
            default_denied, before.can_create_new_synthetic_buy_intent,
            first.status == "PENDING_APPROVAL", parallel_denied,
            result["no_paper_fills"],
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
