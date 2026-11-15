"""Stage50 read-only dashboard smoke: one local synthetic pending order.

This demo never starts a web server or connects to a feed/broker. It prints
the JSON fields a frontend may render under the locked TITAN theme. Human
approval/signing is absent; the one synthetic paper order remains PENDING.
"""
from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.dashboard.paper_read_model import Stage50ReadOnlyPaperDashboard
from nexus_titan.operations.durable_paper_fence import Stage49DurablePaperFence
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import open_stage48_signed_paper_session


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage50-paper-dashboard-") as dirname:
        root = Path(dirname)
        verifier = CryptographicApprovalVerifier(
            secret_key=secrets.token_urlsafe(32),
            db_path=root / "approval-replay.sqlite3",
        )
        session = open_stage48_signed_paper_session(
            PaperDeploymentConfig(
                account_id="STAGE50-SYNTHETIC",
                starting_capital=50000,
                virtual_state_dir=root / "virtual",
                research_db_path=root / "research.sqlite3",
                paper_orders_enabled=True,
            ),
            verifier=verifier,
        )
        fence = Stage49DurablePaperFence(
            session, db_path=root / "coordinator.sqlite3",
        )
        view = Stage50ReadOnlyPaperDashboard(fence)
        before = view.snapshot()
        fence.request_first_synthetic_buy(
            request_id="STAGE50-DEMO-ONE",
            proposal=SyntheticBuyProposal(
                symbol="QA-ABC", quantity=1, stop_price=95,
            ),
            quote=SyntheticQuoteEvidence(
                observed_at=datetime.now(timezone.utc), bid=99.95, ask=100.0,
                displayed_ask_quantity=50, expected_edge_bps=45,
                slippage_bps=2,
            ),
        )
        after = view.snapshot()
        evidence = {"before": before, "after": after}
        print(json.dumps(evidence, allow_nan=False, indent=2, sort_keys=True))
        return 0 if (
            before["status"] == "LOCAL_SYNTHETIC_REVIEW_ONLY"
            and after["status"] == "LOCAL_REVIEW_REQUIRED"
            and before["paper_orders"]["total"] == 0
            and after["paper_orders"]["pending_manual_approval"] == 1
            and after["paper_orders"]["fill_fragments"] == 0
            and after["admission_fence"]["attempt_count"] == 1
            and after["account"]["combined_cash_cents"] is None
            and after["market"]["latest_price"] is None
            and after["safety"]["live_trading_enabled"] is False
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
