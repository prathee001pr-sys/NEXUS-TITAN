"""Stage48 single-use signed synthetic paper BUY smoke.

Uses an ephemeral *local test signing secret* ONLY inside temporary storage.
The secret is never written into GitHub, logs, stdout or application config.
A generated demo signature is NOT external human identity verification.
No simulated fills, market data, brokers, live trading or network access.
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
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    Stage48ApprovalBlocked, open_stage48_signed_paper_session,
)
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.virtual.order_manager import OrderState


def main() -> int:
    with TemporaryDirectory(prefix="nexus-stage48-offline-qa-") as dirname:
        root = Path(dirname)
        verifier = CryptographicApprovalVerifier(
            secrets.token_urlsafe(32),
            db_path=root / "approval_replay.sqlite3",
        )
        session = open_stage48_signed_paper_session(
            PaperDeploymentConfig(
                account_id="STAGE48-SYNTHETIC",
                starting_capital=50000.0,
                virtual_state_dir=root / "virtual",
                research_db_path=root / "research.sqlite3",
                paper_orders_enabled=True,
            ),
            verifier=verifier,
        )
        intent = session.request_synthetic_buy(
            SyntheticBuyProposal(symbol="TEST-ABC", quantity=1, stop_price=95),
            SyntheticQuoteEvidence(
                observed_at=datetime.now(timezone.utc),
                bid=99.95, ask=100.0, displayed_ask_quantity=50,
                expected_edge_bps=45.0, slippage_bps=2.0,
            ),
        )
        unsigned_denied = False
        try:
            session._deployment.virtual_account.approve_order(intent.order_id, "TEST-OWNER")
        except PermissionError:
            unsigned_denied = True
        c = session.pending_challenge(intent.order_id)
        # Demonstration signer; production must use external authenticated signer.
        signed = verifier.issue_token(
            token_id="STAGE48-DEMO-ONE-TIME", actor="TEST-OWNER",
            role="PROJECT_OWNER", target_entity_id=c.target_entity_id,
            snapshot_hash=c.snapshot_hash, ttl_seconds=30,
        )
        approved = session.approve_pending_buy(order_id=intent.order_id, token=signed)
        durable_replay_denied = False
        try:
            verifier.verify_and_consume(
                signed, expected_target_id=c.target_entity_id,
                expected_snapshot_hash=c.snapshot_hash,
            )
        except PermissionError:
            durable_replay_denied = True
        state = {
            "mode": "STAGE48_SYNTHETIC_PAPER_ONLY",
            "unsigned_manual_approval_denied": unsigned_denied,
            "signed_order_accepted_not_filled": approved.state is OrderState.ACCEPTED,
            "durable_token_replay_denied": durable_replay_denied,
            "virtual_fill_count": sum(len(o.fills) for o in session._deployment.virtual_account.orders.values()),
            "external_human_identity_verified": False,
            "independent_global_risk_veto_enforced": False,
            "two_ledger_atomicity_verified": False,
            "real_market_data_verified": False,
            "live_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(state, indent=2, sort_keys=True))
        return 0 if (
            unsigned_denied and durable_replay_denied
            and state["signed_order_accepted_not_filled"] and state["virtual_fill_count"] == 0
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
