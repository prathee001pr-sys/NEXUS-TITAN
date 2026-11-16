"""Opt-in, synthetic-only Stage97 reviewed paper route, NEVER a live broker API.

The research and additive risk reviews are informational until the existing
Stage97 CryptoPaperBook independently authenticates a caller-supplied exact-intent
local TEST permit at its atomic ledger boundary. This adapter does not issue
signatures, inspect secrets, enable accounts, or make risk checks mandatory for
other existing book entrypoints. Human booleans are NOT authenticated identity.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexus_titan.intelligence.market_state import MarketState
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence
from nexus_titan.operations.crypto_spot_independent_review import (
    CryptoSpotReviewPolicy, review_synthetic_crypto_spot_risk,
)
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBook, CryptoPaperIntent, CryptoPaperPermit,
)


class CryptoReviewedPaperBlocked(ValueError):
    """Fail closed before test-only paper submission when review is inadequate."""


@dataclass(frozen=True, slots=True)
class CryptoReviewedPaperReceipt:
    status: str
    account_id: str
    action: str
    symbol: str
    currency: str
    operation_id: str
    journal_revision: int
    journal_tip: str
    independent_review_policy_sha256: str
    realized_net_pnl_cents: int
    paper_trade_recorded: bool = True
    local_synthetic_only: bool = True
    exchange_orders_transmitted: int = 0
    test_permit_issued_by_gateway: bool = False
    authenticated_human_identity_verified: bool = False
    globally_mandatory_risk_gateway_verified: bool = False
    live_trading_enabled: bool = False
    production_ready: bool = False


def submit_reviewed_synthetic_paper(
    *, state: MarketState, evidence: tuple[SpecialistEvidence, ...],
    intent: CryptoPaperIntent, book: CryptoPaperBook,
    policy: CryptoSpotReviewPolicy, permit: CryptoPaperPermit,
    now_epoch: int, human_approved: bool = False,
) -> CryptoReviewedPaperReceipt:
    """Apply an *already authorized* local Stage97 test permit after stricter review.

    No signing key, autonomous mode, retry, paper_enable toggle or permission
    override exists in this path. Stage97 itself verifies the permit signature,
    intent binding, permit expiry, human-approved BUY, duplicate fencing and
    immutable account risk limits in its SQLite transaction.
    """
    if (not isinstance(book, CryptoPaperBook)
            or not isinstance(intent, CryptoPaperIntent)
            or not isinstance(permit, CryptoPaperPermit)
            or type(human_approved) is not bool):
        raise CryptoReviewedPaperBlocked("Actual Stage97 book, intent, TEST permit and boolean required")
    if intent.side == "BUY" and human_approved is not True:
        raise CryptoReviewedPaperBlocked("Explicit local approval required for synthetic BUY")
    if (permit.account_id != book.account_id
            or permit.expected_revision < 0
            or not isinstance(permit.expected_tip, str)
            or len(permit.expected_tip) != 64):
        raise CryptoReviewedPaperBlocked("TEST permit account or head is invalid")
    review = review_synthetic_crypto_spot_risk(
        state=state, evidence=evidence, intent=intent, book=book,
        now_epoch=now_epoch, policy=policy,
    )
    if (permit.expected_revision != review.journal_revision
            or permit.expected_tip != review.journal_tip):
        raise CryptoReviewedPaperBlocked("TEST permit must match independently reviewed account head")
    # A journal change after this review is STILL prevented by the existing
    # atomic Stage97 apply head/signature checks, not by this earlier read.
    state_after, replay = book.apply(
        intent, permit, now_epoch=now_epoch,
        human_approved=human_approved, autonomous=False,
    )
    if replay:
        # Stage97 returns idempotent original operation receipts; this wrapper
        # deliberately does not present old attempts as fresh research reviews.
        raise CryptoReviewedPaperBlocked("This route requires a fresh reviewed paper operation")
    return CryptoReviewedPaperReceipt(
        status="SYNTHETIC_REVIEWED_PAPER_ONLY_NO_LIVE_ORDER",
        account_id=state_after.account_id,
        action=intent.side, symbol=intent.symbol, currency=state_after.currency,
        operation_id=intent.operation_id,
        journal_revision=state_after.journal_revision,
        journal_tip=state_after.journal_tip,
        independent_review_policy_sha256=review.policy_sha256,
        realized_net_pnl_cents=state_after.realized_net_pnl_cents,
    )
