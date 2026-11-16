"""Additive, independently calculated, read-only synthetic BTC spot risk review.

Deliberately NOT a signed risk permit, an order gateway, production authority,
or a substitute for Stage97 atomic policy validation. This reviewer only tightens
Stage97's existing local limits; it never expands permissions or changes a book.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from nexus_titan.intelligence.market_state import MarketState
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence
from nexus_titan.operations.crypto_spot_research_gate import assess_synthetic_crypto_spot
from nexus_titan.operations.stage97_crypto_paper import CryptoPaperBook, CryptoPaperIntent


class CryptoSpotIndependentReviewBlocked(ValueError):
    """An independent synthetic research policy or observed state is unsafe."""


def _whole(value: object, *, minimum: int = 0, maximum: int = 10**15) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise CryptoSpotIndependentReviewBlocked("Non-integer or unbounded policy field")
    return value


@dataclass(frozen=True, slots=True)
class CryptoSpotReviewPolicy:
    """Additional tighter limits, always checked against the Stage97 account."""

    max_order_cents: int
    max_total_exposure_cents: int
    max_lifetime_realized_loss_cents: int
    max_quote_age_seconds: int
    max_fee_bps: int

    def __post_init__(self) -> None:
        _whole(self.max_order_cents, minimum=1)
        _whole(self.max_total_exposure_cents, minimum=1)
        _whole(self.max_lifetime_realized_loss_cents, minimum=1)
        _whole(self.max_quote_age_seconds, minimum=1, maximum=300)
        _whole(self.max_fee_bps, maximum=1000)
        if self.max_order_cents > self.max_total_exposure_cents:
            raise CryptoSpotIndependentReviewBlocked("Review order cap exceeds review exposure cap")


@dataclass(frozen=True, slots=True)
class CryptoSpotIndependentReviewReceipt:
    status: str
    account_id: str
    action: str
    journal_revision: int
    journal_tip: str
    policy_sha256: str
    conservative_notional_cents: int
    conservative_fee_cents: int
    reviewed_exposure_cents: int
    local_policy_only: bool = True
    signed_risk_permit_issued: bool = False
    paper_order_submitted: bool = False
    exchange_order_submitted: bool = False
    independent_production_risk_engine_verified: bool = False
    live_trading_enabled: bool = False
    production_ready: bool = False


def review_synthetic_crypto_spot_risk(
    *, state: MarketState, evidence: tuple[SpecialistEvidence, ...],
    intent: CryptoPaperIntent, book: CryptoPaperBook, now_epoch: int,
    policy: CryptoSpotReviewPolicy,
) -> CryptoSpotIndependentReviewReceipt:
    """Cross-check actual Stage97 read-only state using a *stricter* risk policy.

    Source/evidence/consensus are independently reconstructed by the Stage97
    research gate, not trusted from a caller-supplied 'green' status. The
    resulting receipt is informational. Paper execution ALWAYS requires a
    separate exact-intent signed TEST permit, current journal head, and local
    admission checks within Stage97.apply's SQLite transaction.
    """
    if type(policy) is not CryptoSpotReviewPolicy:
        raise CryptoSpotIndependentReviewBlocked("Explicit typed review policy required")
    # No caller may raise a review cap beyond the current immutable Stage97
    # account scope, even if the candidate would pass those looser caps.
    limits = getattr(book, "limits", None)
    if not isinstance(book, CryptoPaperBook) or limits is None:
        raise CryptoSpotIndependentReviewBlocked("Actual Stage97 account required")
    if (policy.max_order_cents > limits.max_order_cents
            or policy.max_total_exposure_cents > limits.max_exposure_cents
            or policy.max_lifetime_realized_loss_cents > limits.max_session_loss_cents
            or policy.max_quote_age_seconds > limits.max_quote_age_seconds):
        raise CryptoSpotIndependentReviewBlocked("Review policy cannot relax the immutable Stage97 limits")
    receipt = assess_synthetic_crypto_spot(
        state=state, evidence=evidence, intent=intent, book=book, now_epoch=now_epoch,
    )
    if now_epoch - intent.observed_epoch > policy.max_quote_age_seconds:
        raise CryptoSpotIndependentReviewBlocked("Independent quote freshness veto")
    # Second replay is deliberate; an intervening change blocks the receipt.
    head = book.snapshot()
    if (head.account_id != receipt.account_id
            or head.journal_revision != receipt.journal_revision
            or head.journal_tip != receipt.journal_tip):
        raise CryptoSpotIndependentReviewBlocked("Account head advanced during read-only review")
    # Protective SELL is not blocked by a new-entry cap after a kill. Stage97
    # still checks exact quantity, fees, balance and the separate signed permit.
    if intent.side == "BUY":
        if receipt.conservative_notional_cents > policy.max_order_cents:
            raise CryptoSpotIndependentReviewBlocked("Independent order-notional veto")
        if (head.remaining_cost_basis_cents + receipt.conservative_notional_cents
                + receipt.estimated_fee_cents > policy.max_total_exposure_cents):
            raise CryptoSpotIndependentReviewBlocked("Independent capital-exposure veto")
        if head.realized_net_pnl_cents <= -policy.max_lifetime_realized_loss_cents:
            raise CryptoSpotIndependentReviewBlocked("Independent lifetime-loss veto")
        if limits.fee_bps > policy.max_fee_bps:
            raise CryptoSpotIndependentReviewBlocked("Independent fee-policy veto")
    # No user-controlled risk boolean is accepted as an authorization input.
    # This digest is a local change detector, NOT a signature or provenance proof.
    policy_payload = {field: getattr(policy, field) for field in policy.__dataclass_fields__}
    policy_sha256 = sha256(json.dumps(policy_payload, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
    return CryptoSpotIndependentReviewReceipt(
        status="SYNTHETIC_INDEPENDENT_REVIEW_ONLY_NO_EXECUTION",
        account_id=head.account_id, action=intent.side,
        journal_revision=head.journal_revision, journal_tip=head.journal_tip,
        policy_sha256=policy_sha256,
        conservative_notional_cents=receipt.conservative_notional_cents,
        conservative_fee_cents=receipt.estimated_fee_cents,
        reviewed_exposure_cents=head.remaining_cost_basis_cents
        + (receipt.conservative_notional_cents + receipt.estimated_fee_cents if intent.side == "BUY" else 0),
    )
