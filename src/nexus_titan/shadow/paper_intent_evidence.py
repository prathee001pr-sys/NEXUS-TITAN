"""Stage35 — deterministic, unsigned evidence of a pending manual paper intent.

This is an integrity/freshness fingerprint, NOT authorization or a signature.
Any party with write-access to the Python process may forge/recompute it.
It cannot authenticate market data, actors, brokers or third-party risk policy.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from nexus_titan.core.permissions import Action,Decision,decide
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import OrderState,TradingMode,VirtualAccount


class PaperEvidenceError(ValueError):
    """Pending manual paper intent evidence is missing, invalid or stale."""


@dataclass(frozen=True,slots=True)
class PaperIntentEvidence:
    account_id: str
    order_id: str
    order_snapshot_sha256: str
    policy_sha256: str
    research_ledger_sha256: str
    evidence_sha256: str
    schema_version: int = 1
    externally_signed: bool = False
    authenticated_identity: bool = False
    live_trading_approved: bool = False


def _fingerprint(payload: dict) -> str:
    blob=json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def capture_pending_paper_intent_evidence(
    virtual: VirtualAccount,
    research: DurableResearchShadowLedger,
    *, order_id: str, paper_trading_enabled: bool = False,
) -> PaperIntentEvidence:
    """Take a read-only snapshot; require default-deny manual paper state."""
    if not isinstance(virtual,VirtualAccount) or not isinstance(research,DurableResearchShadowLedger):
        raise PaperEvidenceError("Both isolated account objects required")
    if not isinstance(paper_trading_enabled,bool) or decide(
        Action.PAPER_TRADE,paper_trading_enabled=paper_trading_enabled,
    ) is not Decision.ALLOW:
        raise PaperEvidenceError("Explicit paper permission denied")
    if virtual.account_id!=research.account_id:
        raise PaperEvidenceError("Research/virtual account identifiers mismatch")
    if virtual.kill_switched or virtual.trading_mode is not TradingMode.MANUAL_APPROVAL:
        raise PaperEvidenceError("Manual paper mode without kill switch required")
    if virtual.require_pretrade_risk_check is not True or not callable(virtual.approval_authorizer):
        raise PaperEvidenceError("Authoritative risk and human callback required")
    order=virtual.orders.get(order_id)
    if order is None or order.state is not OrderState.PENDING_APPROVAL or order.filled_qty!=0:
        raise PaperEvidenceError("Only unfilled, pending manual orders can be snapshotted")
    if not virtual.reconcile().is_reconciled:
        raise PaperEvidenceError("Virtual cash and inventory out of reconciliation")
    if not research.verify_integrity() or not research.guarded_paper_mode:
        raise PaperEvidenceError("Persistent guarded research hash-chain required")
    try:
        with research._transaction() as con:
            research._verify(con)
            ledger_digest=research._state_digest(con)
    except Exception as exc:
        raise PaperEvidenceError("Research ledger digest unavailable") from exc
    policy=_fingerprint({
        "account_id":virtual.account_id,
        "trading_mode":virtual.trading_mode.value,
        "risk_enabled":virtual.require_pretrade_risk_check,
        "risk_per_trade_pct":virtual.risk_per_trade_pct,
        "max_portfolio_exposure_pct":virtual.max_portfolio_exposure_pct,
        "initial_margin_pct":virtual.initial_margin_pct,
        "capital":virtual.current_capital,
        "available_cash":virtual.cash_balance,
        "exposure":virtual.current_exposure,
        "drawdown_pct":virtual.current_drawdown_pct,
        "kill_switched":virtual.kill_switched,
    })
    snap=order.compute_snapshot_hash()
    envelope={
        "schema_version":1,"account_id":virtual.account_id,
        "order_id":order_id,"order_state":order.state.value,
        "order_snapshot":snap,"policy_sha256":policy,
        "research_ledger_sha256":ledger_digest,
    }
    return PaperIntentEvidence(
        virtual.account_id,order_id,snap,policy,ledger_digest,
        _fingerprint(envelope),
    )


def verify_pending_paper_intent_evidence(
    evidence: PaperIntentEvidence,
    virtual: VirtualAccount,
    research: DurableResearchShadowLedger,
    *, paper_trading_enabled: bool = False,
) -> bool:
    """Reject any drift; never approve, sign or fill the pending order."""
    if not isinstance(evidence,PaperIntentEvidence) or evidence.schema_version!=1:
        return False
    if evidence.externally_signed or evidence.authenticated_identity or evidence.live_trading_approved:
        return False
    try:
        fresh=capture_pending_paper_intent_evidence(
            virtual,research,order_id=evidence.order_id,
            paper_trading_enabled=paper_trading_enabled,
        )
    except (PaperEvidenceError, ValueError, TypeError, ArithmeticError):
        return False
    return evidence==fresh
