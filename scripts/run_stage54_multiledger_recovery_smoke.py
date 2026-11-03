"""Stage54 offline four-book reconciliation smoke.

Creates only disposable local synthetic SQLite files. No orders or tokens
are issued, and no existing user account/database is opened or modified.
Simulates a durable Stage49 PREPARING marker after a hypothetical crash.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.multi_ledger_recovery_audit import (
    Stage54ReadOnlyMultiLedgerAudit,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    open_stage48_signed_paper_session,
)
from nexus_titan.operations.synthetic_capital_authority import (
    Stage53SyntheticCapitalAuthority,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage54-offline-") as location:
        root = Path(location)
        account = "STAGE54-SYNTHETIC"
        config = PaperDeploymentConfig(
            account_id=account, starting_capital=50000,
            virtual_state_dir=root / "virtual",
            research_db_path=root / "research.sqlite3",
            paper_orders_enabled=False,  # explicit no-new-paper-orders demo
        )
        verifier = CryptographicApprovalVerifier(
            secret_key=secrets.token_urlsafe(32), db_path=root / "replay.sqlite3",
        )
        session = open_stage48_signed_paper_session(config, verifier=verifier)
        coord = root / "coordinator.sqlite3"
        fence = Stage49DurablePaperFence(session, db_path=coord)
        budget = Stage53SyntheticCapitalAuthority(
            db_path=root / "budget.sqlite3", account_id=account,
            starting_cents=5_000_000,
            excluded_ledger_paths=(
                root / "research.sqlite3", root / "replay.sqlite3",
                coord, root / "virtual" / f"{account}_durable.db",
            ),
        )
        audit = Stage54ReadOnlyMultiLedgerAudit(
            paper_fence=fence, synthetic_budget=budget,
        )
        flat = audit.inspect().to_dict()
        with sqlite3.connect(coord) as db:
            db.execute(
                "INSERT INTO admission_attempts VALUES (?,?,?,?,?,?,?,?)",
                ("S54-DEMO-CRASH", account, "PREPARING",
                 10000, "0" * 64, 0, None,
                 datetime.now(timezone.utc).isoformat()),
            )
        crash = audit.inspect().to_dict()
        print(json.dumps({
            "mode": "STAGE54_SYNTHETIC_READ_ONLY_RECOVERY_AUDIT",
            "flat": flat,
            "crash": crash,
        }, indent=2, sort_keys=True, allow_nan=False))
        return 0 if (
            flat["recovery_classification"] == "LOCAL_FLAT_COMPARISON_ONLY"
            and crash["recovery_classification"] == "PREPARING_CRASH_QUARANTINE"
            and crash["manual_recovery_required"] is True
            and crash["cross_database_atomicity_verified"] is False
            and crash["automatic_order_replay_enabled"] is False
            and crash["production_ready"] is False
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
