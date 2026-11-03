"""Stage48: one-use signed approval for NEW SYNTHETIC paper BUY orders.

This opt-in local adapter wires core.security_gates.CryptographicApprovalVerifier
into Stage43's VirtualAccount.approval_authorizer, and requires Stage47 synthetic
Risk & Veto entry provenance for each challenged BUY in the current session.

A signature proves possession of a signing key, NOT human authentication.
The signer/key holder is outside this module. This is NOT a mandatory security
service or a global barrier for legacy Python APIs. NO LIVE/BROKER operations.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from nexus_titan.core.security_gates import (
    CryptographicApprovalVerifier, SignedApprovalToken,
)
from nexus_titan.operations.offline_risk_veto import (
    Stage47OfflineRiskVetoEntry, Stage47RiskVetoBlocked,
    Stage47RiskVetoPolicy, SyntheticBuyProposal, SyntheticQuoteEvidence,
)
from nexus_titan.operations.paper_deployment import (
    PaperDeploymentConfig, PaperOnlyDeployment, open_paper_only_deployment,
)
from nexus_titan.shadow.paper_intent_gateway import PaperIntentResult
from nexus_titan.virtual.order_manager import OrderSide, OrderState, VirtualOrder


class Stage48ApprovalBlocked(PermissionError):
    """Approval was refused and cannot be treated as order/fill authority."""


@dataclass(frozen=True, slots=True)
class Stage48ApprovalChallenge:
    """Immutable pending-order signing instructions; not an approval token."""

    account_id: str
    order_id: str
    target_entity_id: str
    snapshot_hash: str
    order_state: str = "PENDING_APPROVAL"
    simulated_only: bool = True
    external_identity_verified: bool = False
    independently_enforced_authority: bool = False
    live_orders_transmitted: int = 0


@dataclass(frozen=True, slots=True)
class Stage48ApprovalStatus:
    account_id: str
    session_paper_orders_enabled: bool
    session_strict_gateway_only: bool
    signed_approval_adapter_installed: bool
    approved_for_live_trading: bool = False
    independently_authenticated_human_identity: bool = False
    signer_key_isolated_in_external_service: bool = False
    globally_mandatory_legacy_api_enforcement: bool = False
    cross_ledger_atomicity_verified: bool = False
    market_data_authenticity_verified: bool = False
    production_ready: bool = False


_ALLOWED_PAPER_ROLES = frozenset(("PROJECT_OWNER", "HUMAN_APPROVER"))


def _challenge_for(
    deployment: PaperOnlyDeployment, order_id: str,
) -> Stage48ApprovalChallenge:
    v = deployment.virtual_account
    if not isinstance(order_id, str) or not order_id or len(order_id) > 128:
        raise Stage48ApprovalBlocked("Valid paper order ID required")
    state = deployment.status()
    if not state.paper_intents_enabled or not state.strict_paper_mode or not state.gateway_only_mode:
        raise Stage48ApprovalBlocked("Stage43 manual paper account readiness is unavailable")
    order = v.orders.get(order_id)
    if (
        order is None or order.state is not OrderState.PENDING_APPROVAL
        or order.approval is not None or order.side is not OrderSide.BUY
        or order.is_emergency or order.filled_qty != 0 or order.fills
        or order.instrument_type != "EQUITY_DELIVERY"
        or not isinstance(order.risk_policy_fingerprint, str)
        or not order.risk_policy_fingerprint
    ):
        raise Stage48ApprovalBlocked("Only untouched Stage47 synthetic pending BUY is supported")
    try:
        v._assert_buy_policy_evidence(order)
        revision = v._snapshot_revision
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise Stage48ApprovalBlocked("Durable virtual account revision missing")
        policy_sha = v._risk_policy_fingerprint()
        # Stable exact canonical binding of account, versioned policy, order
        # fields and durable snapshot revision. Any change requires NEW signing.
        encoded = json.dumps(
            ["STAGE48_SYNTHETIC_PAPER_APPROVAL_V1", v.account_id, revision,
             policy_sha, order_id, order.compute_snapshot_hash(),
             order.state.value, order.quantity, order.filled_qty],
            ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        ).encode("utf-8")
        bound_hash = hashlib.sha256(encoded).hexdigest()
    except (ValueError, TypeError, OverflowError, PermissionError) as exc:
        raise Stage48ApprovalBlocked("Order risk policy or signing snapshot changed") from exc
    return Stage48ApprovalChallenge(
        account_id=v.account_id,
        order_id=order_id,
        target_entity_id="STAGE48:PAPER:" + v.account_id + ":" + order_id,
        snapshot_hash=bound_hash,
    )


class _OneShotPaperApprovalCallback:
    """Fail closed unless called in the same thread during signed approval.

    Token is consumed inside the VirtualAccount callback *before* its
    order approval is saved. If the subsequent account write fails, the token
    stays spent: this is deliberate safety, NOT cross-ledger atomicity.
    """

    def __init__(self, verifier: CryptographicApprovalVerifier):
        self._verifier = verifier
        self._deployment: PaperOnlyDeployment | None = None
        self._token: SignedApprovalToken | None = None
        self._order_id: str | None = None
        self._challenge: Stage48ApprovalChallenge | None = None
        self._thread: int | None = None
        self._used = False
        self._lock = threading.RLock()

    def attach(self, deployment: PaperOnlyDeployment) -> None:
        with self._lock:
            if self._deployment is not None:
                raise Stage48ApprovalBlocked("Approval callback cannot be rebound")
            self._deployment = deployment

    def __call__(self, actor: str, order_id: str) -> bool:
        with self._lock:
            if (
                self._token is None or self._used or self._deployment is None
                or self._order_id != order_id or self._thread != threading.get_ident()
                or self._challenge is None
                or actor != self._token.actor
                or self._token.role not in _ALLOWED_PAPER_ROLES
            ):
                return False
            # Invalidate the in-memory approval window before *any* verification.
            self._used = True
            current = _challenge_for(self._deployment, order_id)
            if current != self._challenge:
                raise Stage48ApprovalBlocked("Order, account revision or risk policy changed")
            # Signature, role, target and SHA are verified, with a durable
            # SQLite BEGIN IMMEDIATE, one-use nonce commit.
            return self._verifier.verify_and_consume(
                self._token,
                expected_target_id=current.target_entity_id,
                expected_snapshot_hash=current.snapshot_hash,
            )

    def approve(
        self, deployment: PaperOnlyDeployment,
        order_id: str, token: SignedApprovalToken,
    ) -> VirtualOrder:
        with self._lock:
            if self._deployment is not deployment:
                raise Stage48ApprovalBlocked("Wrong deployment for signed approval callback")
            if self._token is not None:
                raise Stage48ApprovalBlocked("Nested signed approval session refused")
            if not isinstance(token, SignedApprovalToken):
                raise Stage48ApprovalBlocked("SignedApprovalToken is required")
            if token.role not in _ALLOWED_PAPER_ROLES:
                raise Stage48ApprovalBlocked("Role is not authorized to approve paper BUY")
            if not isinstance(token.actor, str) or not token.actor.strip():
                raise Stage48ApprovalBlocked("Signed actor ID missing")
            current = _challenge_for(deployment, order_id)
            if (token.target_entity_id != current.target_entity_id
                    or token.snapshot_hash != current.snapshot_hash):
                raise Stage48ApprovalBlocked("Signed token is bound to a different order or snapshot")
            self._token, self._order_id, self._challenge = token, order_id, current
            self._thread, self._used = threading.get_ident(), False
            try:
                return deployment.virtual_account.approve_order(order_id, actor=token.actor)
            finally:
                self._token = None
                self._order_id = None
                self._challenge = None
                self._thread = None
                self._used = False


class Stage48SignedPaperSession:
    """Only Stage47-issued pending BUYs may obtain local signed approval.

    After crash/restart, in-memory provenance is lost and old pending BUYs
    fail closed. Manual review/recovery is required; do not auto-approve.
    """

    def __init__(
        self,
        deployment: PaperOnlyDeployment,
        verifier: CryptographicApprovalVerifier,
        callback: _OneShotPaperApprovalCallback,
    ) -> None:
        if not isinstance(deployment, PaperOnlyDeployment):
            raise TypeError("Stage43 paper deployment required")
        if not isinstance(verifier, CryptographicApprovalVerifier):
            raise TypeError("CryptographicApprovalVerifier required")
        if callback._deployment is not deployment or deployment.virtual_account.approval_authorizer is not callback:
            raise Stage48ApprovalBlocked("Signing callback is not the account's configured approval gate")
        self._deployment = deployment
        self._verifier = verifier
        self._callback = callback
        self._issued_ids: set[str] = set()
        self._entry = Stage47OfflineRiskVetoEntry(deployment)

    def status(self) -> Stage48ApprovalStatus:
        s = self._deployment.status()
        return Stage48ApprovalStatus(
            account_id=self._deployment.config.account_id,
            session_paper_orders_enabled=s.paper_intents_enabled,
            session_strict_gateway_only=s.strict_paper_mode and s.gateway_only_mode,
            signed_approval_adapter_installed=(
                self._deployment.virtual_account.approval_authorizer is self._callback
            ),
        )

    def request_synthetic_buy(
        self, proposal: SyntheticBuyProposal, quote: SyntheticQuoteEvidence,
        *, policy: Stage47RiskVetoPolicy = Stage47RiskVetoPolicy(),
    ) -> PaperIntentResult:
        result = self._entry.request_buy(proposal, quote, policy=policy)
        if result.status != "PENDING_APPROVAL":
            raise Stage48ApprovalBlocked("Stage47 failed to create a pending manual intent")
        self._issued_ids.add(result.order_id)
        return result

    def pending_challenge(self, order_id: str) -> Stage48ApprovalChallenge:
        if order_id not in self._issued_ids:
            raise Stage48ApprovalBlocked("Order did not originate in this Stage48 signed session")
        return _challenge_for(self._deployment, order_id)

    def approve_pending_buy(
        self, *, order_id: str, token: SignedApprovalToken,
    ) -> VirtualOrder:
        if order_id not in self._issued_ids:
            raise Stage48ApprovalBlocked("Cannot sign untrusted or restored pending order provenance")
        if self._deployment.virtual_account.approval_authorizer is not self._callback:
            raise Stage48ApprovalBlocked("Account approval callback was replaced")
        approved = self._callback.approve(self._deployment, order_id, token)
        if approved.state is not OrderState.ACCEPTED:
            raise Stage48ApprovalBlocked("Manual BUY approval did not reach ACCEPTED")
        self._issued_ids.discard(order_id)
        # Does not execute or authorize a simulated fill. Any later fill
        # still uses Stage43 strict order approval / risk / kill-switch guards.
        return approved


def open_stage48_signed_paper_session(
    config: PaperDeploymentConfig,
    *,
    verifier: CryptographicApprovalVerifier,
) -> Stage48SignedPaperSession:
    """Opt-in startup with a default-deny callback, never a bypassing lambda.

    Verifier must be configured with secret from outside source and its
    persistent replay DB on separate protected storage. This module NEVER
    generates signing credentials or mints a token.
    """
    if not isinstance(config, PaperDeploymentConfig):
        raise TypeError("PaperDeploymentConfig required")
    if not isinstance(verifier, CryptographicApprovalVerifier):
        raise TypeError("CryptographicApprovalVerifier required")
    try:
        replay_db = Path(verifier.db_path)
        durable_db = config.virtual_state_dir / f"{config.account_id}_durable.db"
        if (replay_db.is_symlink()
                or replay_db.resolve() in (
                    durable_db.resolve(), config.research_db_path.resolve()
                )):
            raise Stage48ApprovalBlocked("Approval replay DB must be separate and not symlinked")
    except Stage48ApprovalBlocked:
        # PermissionError inherits OSError: preserve deliberate policy denials.
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise Stage48ApprovalBlocked("Approval replay DB path is invalid") from exc

    callback = _OneShotPaperApprovalCallback(verifier)
    deployment = open_paper_only_deployment(config, approval_authorizer=callback)
    callback.attach(deployment)
    return Stage48SignedPaperSession(deployment, verifier, callback)
