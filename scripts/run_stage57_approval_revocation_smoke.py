"""Stage57 isolated synthetic approval revocation / risk-binding smoke.

Creates only disposable local paper/SQLite files and HMAC QA key. A
revocation blocks approval of pending (not filled) synthetic paper BUYs.
No broker, real user identity, market data or production authority.
"""
from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.core.security_gates import CryptographicApprovalVerifier
from nexus_titan.operations.brokerless_risk_veto import (
    Stage56SyntheticIntent, Stage56SyntheticQuote, Stage56SyntheticRiskState,
    inspect_stage56_synthetic_risk,
)
from nexus_titan.operations.local_approval_risk_review import (
    inspect_stage57_local_approval_binding,
)
from nexus_titan.operations.offline_risk_veto import (
    SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import PaperDeploymentConfig
from nexus_titan.operations.signed_paper_approval import (
    open_stage48_signed_paper_session,
)
from nexus_titan.virtual.order_manager import OrderState


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage57-no-broker-") as dirname:
        root = Path(dirname)
        verifier = CryptographicApprovalVerifier(
            secret_key=secrets.token_urlsafe(32),
            db_path=root / "approval-replay.sqlite3",
        )
        session = open_stage48_signed_paper_session(
            PaperDeploymentConfig(
                account_id="STAGE57-QA", starting_capital=50_000,
                virtual_state_dir=root / "virtual",
                research_db_path=root / "research.sqlite3",
                paper_orders_enabled=True,
            ), verifier=verifier,
        )

        def pending(symbol: str):
            order = session.request_synthetic_buy(
                SyntheticBuyProposal(symbol=symbol, quantity=1, stop_price=95),
                SyntheticQuoteEvidence(
                    observed_at=datetime.now(timezone.utc),
                    bid=99.95, ask=100, displayed_ask_quantity=100,
                    expected_edge_bps=45, slippage_bps=2,
                ),
            )
            return order.order_id, session.pending_challenge(order.order_id)

        first_id, first_challenge = pending("ABC")
        first_token = verifier.issue_token(
            token_id="STAGE57-REVOKE-TOKEN", actor="LOCAL-LABEL-OWNER",
            role="PROJECT_OWNER", target_entity_id=first_challenge.target_entity_id,
            snapshot_hash=first_challenge.snapshot_hash, ttl_seconds=30,
        )
        verifier.revoke_token(first_token.token_id)
        token_refused = False
        try:
            session.approve_pending_buy(order_id=first_id, token=first_token)
        except PermissionError:
            token_refused = True

        second_id, second_challenge = pending("DEF")
        second_token = verifier.issue_token(
            token_id="STAGE57-REVOKE-ACTOR", actor="LOCAL-LABEL-HUMAN",
            role="HUMAN_APPROVER", target_entity_id=second_challenge.target_entity_id,
            snapshot_hash=second_challenge.snapshot_hash, ttl_seconds=30,
        )
        verifier.revoke_actor(second_token.actor)
        actor_refused = False
        try:
            session.approve_pending_buy(order_id=second_id, token=second_token)
        except PermissionError:
            actor_refused = True

        # The separate Stage56 screen is re-run on fresh QA quote/account.
        # It is NOT enforced by the Stage48 signer or a broker.
        now = datetime.now(timezone.utc)
        intent = Stage56SyntheticIntent(
            request_id=first_id, symbol="QAABC", quantity=1,
            limit_price_cents=10000, stop_price_cents=9500,
            fee_buffer_cents=100,
        )
        quote = Stage56SyntheticQuote(
            observed_at=now - timedelta(seconds=1),
            bid_cents=9995, ask_cents=10000, ask_depth_units=100,
            expected_slippage_bps=2, expected_edge_bps=45,
        )
        account = Stage56SyntheticRiskState(
            account_id="STAGE57-QA", initial_cents=5_000_000,
            available_cents=5_000_000, already_reserved_cents=0,
            daily_realized_loss_bps=0, current_drawdown_bps=0,
            consecutive_losses=0, kill_switch_active=False,
            risk_module_healthy=True,
        )
        risk = inspect_stage56_synthetic_risk(intent, quote, account, now=now)
        assessment = inspect_stage57_local_approval_binding(
            first_challenge, intent, quote, account,
            expected_risk_policy_sha256=risk.policy_sha256,
            expected_risk_input_sha256=risk.input_sha256,
            now=now,
        )
        all_unfilled = all(
            o.state is OrderState.PENDING_APPROVAL
            and o.filled_qty == 0 and o.approval is None and not o.fills
            for o in session._deployment.virtual_account.orders.values()
        )
        data = {
            "mode": "STAGE57_LOCAL_SIGNER_REVOCATION_QA",
            "token_revocation_denied_paper_approval": token_refused,
            "actor_revocation_denied_paper_approval": actor_refused,
            "risk_binding_local_consistency": assessment.local_consistency_observed,
            "risk_binding_authorizes_order": assessment.order_submission_authorized,
            "stage48_uses_stage57_risk_binding": assessment.stage48_challenge_integrates_stage56_review,
            "no_orders_filled": all_unfilled,
            "local_paper_pending_orders": len(session._deployment.virtual_account.orders),
            "live_orders_transmitted": 0,
            "external_human_identity_verified": False,
            "global_legacy_apis_fenced": False,
            "production_ready": False,
        }
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0 if (
            token_refused and actor_refused and all_unfilled
            and assessment.local_consistency_observed
            and not assessment.order_submission_authorized
            and not assessment.stage48_challenge_integrates_stage56_review
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
