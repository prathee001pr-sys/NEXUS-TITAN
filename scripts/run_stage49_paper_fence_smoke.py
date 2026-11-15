"""Stage49 deterministic brokerless one-shot paper admission smoke.

No real market data or broker. A temporary three-book setup demonstrates
that a shared coordinator permanently blocks duplicate local BUY attempts.
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
from nexus_titan.operations.durable_paper_fence import (
    Stage49AdmissionBlocked, Stage49DurablePaperFence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import open_stage48_signed_paper_session
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage49-qa-") as dirname:
        root = Path(dirname)
        config = PaperDeploymentConfig(
            account_id="STAGE49-SYNTHETIC", starting_capital=50000,
            virtual_state_dir=root / "virtual",
            research_db_path=root / "research.sqlite3",
            paper_orders_enabled=True,
        )
        verifier = CryptographicApprovalVerifier(
            secret_key=secrets.token_urlsafe(32),
            db_path=root / "replay.sqlite3",
        )
        session = open_stage48_signed_paper_session(config, verifier=verifier)
        coord_path = root / "entry-fence.sqlite3"
        fence = Stage49DurablePaperFence(session, db_path=coord_path)
        proposal = SyntheticBuyProposal(symbol="QA-XYZ", quantity=1, stop_price=95.0)
        quote = SyntheticQuoteEvidence(
            observed_at=datetime.now(timezone.utc), bid=99.95, ask=100.0,
            displayed_ask_quantity=50, expected_edge_bps=42, slippage_bps=2,
        )
        pending = fence.request_first_synthetic_buy(
            request_id="STAGE49-ONE", proposal=proposal, quote=quote,
        )
        duplicate_denied = False
        try:
            fence.request_first_synthetic_buy(
                request_id="STAGE49-ONE", proposal=proposal, quote=quote,
            )
        except Stage49AdmissionBlocked:
            duplicate_denied = True
        restarted = open_stage48_signed_paper_session(config, verifier=verifier)
        durable_fence = Stage49DurablePaperFence(restarted, db_path=coord_path)
        restart_denied = False
        try:
            durable_fence.request_first_synthetic_buy(
                request_id="STAGE49-RETRY", proposal=proposal, quote=quote,
            )
        except Stage49AdmissionBlocked:
            restart_denied = True
        status = durable_fence.inspect()
        state = {
            "mode": "STAGE49_COOPERATIVE_SYNTHETIC_PAPER_FENCE_ONLY",
            "first_request_pending": pending.status == "PENDING_APPROVAL",
            "duplicate_request_blocked": duplicate_denied,
            "restart_reentry_blocked": restart_denied,
            "coordinator_attempt_count": status.attempt_count,
            "coordinator_last_state": status.latest_attempt_state,
            "virtual_fills": sum(len(x.fills) for x in restarted._deployment.virtual_account.orders.values()),
            "cross_ledger_atomicity_verified": False,
            "one_unified_cash_authority_verified": False,
            "global_legacy_entrypoints_fenced": False,
            "licensed_real_market_data_verified": False,
            "broker_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0 if all((
            state["first_request_pending"], state["duplicate_request_blocked"],
            state["restart_reentry_blocked"], status.attempt_count == 1,
            status.latest_attempt_state == "PENDING", state["virtual_fills"] == 0,
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
