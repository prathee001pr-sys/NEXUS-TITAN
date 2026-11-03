"""Stage53 purely synthetic local-budget persistence smoke, no orders.

Uses ephemeral SQLite, illustrative INR 50,000 (capital is configurable
in the API; NOT a fixed trading capital). Nothing here is broker-capable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.operations.synthetic_capital_authority import (
    Stage53BudgetBlocked, Stage53SyntheticCapitalAuthority,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage53-local-budget-") as directory:
        file = Path(directory) / "capital_authority.sqlite3"
        cap = Stage53SyntheticCapitalAuthority(
            db_path=file, account_id="STAGE53-SYNTHETIC", starting_cents=5_000_000,
        )
        receipt = cap.hold_for_synthetic_research(
            request_id="STAGE53-ONE", amount_cents=100_000,
        )
        denied = False
        try:
            cap.hold_for_synthetic_research(
                request_id="STAGE53-ONE", amount_cents=100_000,
            )
        except Stage53BudgetBlocked:
            denied = True
        # A separate instance with same SQLite path must see durable holds.
        resumed = Stage53SyntheticCapitalAuthority(
            db_path=file, account_id="STAGE53-SYNTHETIC", starting_cents=5_000_000,
        )
        status = resumed.inspect()
        evidence = {
            "mode": "STAGE53_LOCAL_SYNTHETIC_BUDGET_ONLY",
            "duplicate_request_denied": denied,
            "restart_durable_hold_verified": status.local_integrity_verified
            and status.audit_chain_tip == receipt.audit_chain_tip,
            "starting_cents": status.initial_cents,
            "held_cents": status.held_cents,
            "hold_count": status.hold_count,
            "remaining_cents": status.remaining_cents,
            "single_authority_for_existing_books": False,
            "cross_database_atomicity_verified": False,
            "global_legacy_entrypoints_fenced": False,
            "independent_risk_veto_enforced": False,
            "externally_verified_identity": False,
            "broker_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(evidence, indent=2, sort_keys=True))
        return 0 if (
            denied and evidence["restart_durable_hold_verified"]
            and status.held_cents == 100_000
            and status.hold_count == 1
            and status.remaining_cents == 4_900_000
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
