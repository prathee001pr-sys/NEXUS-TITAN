"""Strict, read-only Stage97 BTC-USDT synthetic spot research evidence gate.

This is a data/consensus and local-ledger-policy precheck. It is NOT an
independent authorization, live trading route, risk permit issuer or broker.
It never converts the generic whole-lot risk sizing into microcoin quantities.
The Stage97 ledger must separately validate every exact-intent signed test
permit at its own atomic append boundary before any *paper* mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from nexus_titan.intelligence.consensus import ConsensusEngine, Decision
from nexus_titan.intelligence.market_state import MarketState, MarketStateBuilder
from nexus_titan.intelligence.specialist_roles import (
    SpecialistEvidence, adapt_specialist_evidence,
)
from nexus_titan.operations.stage97_crypto_paper import (
    CryptoPaperBook, CryptoPaperIntent,
)


class CryptoSpotResearchBlocked(ValueError):
    """Invalid or untrusted synthetic evidence never creates an order permit."""


@dataclass(frozen=True, slots=True)
class CryptoSpotResearchReceipt:
    status: str
    action: str
    symbol: str
    currency: str
    quantity_microcoin: int
    conservative_notional_cents: int
    estimated_fee_cents: int
    account_id: str
    journal_revision: int
    journal_tip: str
    independent_evidence_roles: tuple[str, ...]
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"
    risk_scope: str = "STAGE97_LOCAL_LIMITS_PRECHECK_NOT_AN_AUTHORIZATION"
    signed_risk_permit_issued: bool = False
    paper_order_submitted: bool = False
    exchange_order_submitted: bool = False
    autonomous_trading_enabled: bool = False
    live_trading_enabled: bool = False
    production_ready: bool = False


def _integer(value: object, *, min_value: int = 0) -> int:
    if type(value) is not int or value < min_value or value > 10**15:
        raise CryptoSpotResearchBlocked("Unbounded or invalid synthetic integer")
    return value


def _integer_cents(value: object) -> int:
    if type(value) not in (int, float, Decimal):
        raise CryptoSpotResearchBlocked("Price must be finite numeric USD")
    try:
        cents = Decimal(str(value)) * Decimal(100)
    except (InvalidOperation, ValueError) as exc:
        raise CryptoSpotResearchBlocked("Invalid decimal price") from exc
    if not cents.is_finite() or cents != cents.to_integral_value() or not 0 < cents <= 10**15:
        raise CryptoSpotResearchBlocked("Unrepresentable synthetic cents price")
    return int(cents)


def assess_synthetic_crypto_spot(
    *, state: MarketState, evidence: tuple[SpecialistEvidence, ...],
    intent: CryptoPaperIntent, book: CryptoPaperBook, now_epoch: int,
) -> CryptoSpotResearchReceipt:
    """Return a research-only receipt, leaving Stage97 as paper risk authority.

    No user approval is inferred from the receipt; no test key is accepted or
    created here. A future actor must separately pass Stage97's signature,
    explicit local approval and atomic policy checks; this is not a live gate.
    """
    now = _integer(now_epoch)
    if not isinstance(state, MarketState) or not isinstance(intent, CryptoPaperIntent) or not isinstance(book, CryptoPaperBook):
        raise CryptoSpotResearchBlocked("Actual typed research state, intent and ledger required")
    if not (state.symbol == intent.symbol == "BTC-USDT"
            and state.exchange == "CRYPTO_SYNTHETIC"
            and intent.source == state.provenance.get("source_id") == "LOCAL_SYNTHETIC_TEST_ONLY"):
        raise CryptoSpotResearchBlocked("Synthetic market and source identities do not match")
    if (state.quality.valid is not True or state.quality.stale is not False
            or state.quality.missing_blocks or state.quality.warnings):
        raise CryptoSpotResearchBlocked("Input quality is not accepted")
    if (not isinstance(state.event_time, datetime) or state.event_time.tzinfo is None
            or state.event_time.utcoffset() is None
            or not isinstance(state.ingest_time, datetime) or state.ingest_time.tzinfo is None
            or state.ingest_time.utcoffset() is None):
        raise CryptoSpotResearchBlocked("Timezone-aware timestamps required")
    observed = _integer(intent.observed_epoch)
    if (not isinstance(book.limits.max_quote_age_seconds, int)
            or isinstance(book.limits.max_quote_age_seconds, bool)):
        raise CryptoSpotResearchBlocked("Invalid snapshot age policy")
    age_limit = book.limits.max_quote_age_seconds
    if (observed > now or now - observed > age_limit
            or abs(state.event_time.timestamp() - observed) > 1
            or state.ingest_time.timestamp() > now):
        raise CryptoSpotResearchBlocked("Out-of-order, future or stale synthetic evidence")
    # Reconstruct from the raw blocks; a caller-forged 'valid' quality bit is not enough.
    rebuilt = MarketStateBuilder(max_age_seconds=age_limit).build(
        exchange=state.exchange, symbol=state.symbol, interval=state.interval,
        event_time=state.event_time, ingest_time=state.ingest_time,
        price_volume=state.price_volume, regime=state.regime,
        options_flow=state.options_flow, context=state.context,
        provenance=state.provenance,
    )
    if rebuilt.quality.valid is not True:
        raise CryptoSpotResearchBlocked("Revalidated market data was rejected")
    candles = state.price_volume
    open_, high, low, close = (
        _integer_cents(candles.get(x)) for x in ("open", "high", "low", "close")
    )
    if not (low <= min(open_, close) <= max(open_, close) <= high):
        raise CryptoSpotResearchBlocked("Inconsistent synthetic OHLC")
    if close != intent.price_cents_per_coin:
        raise CryptoSpotResearchBlocked("Quote and exact-intent price disagree")
    if not isinstance(evidence, tuple) or not 2 <= len(evidence) <= 8 or any(
        not isinstance(e, SpecialistEvidence) for e in evidence
    ):
        raise CryptoSpotResearchBlocked("Two independent typed specialist roles required")
    try:
        proposals = adapt_specialist_evidence(evidence)
    except (ValueError, TypeError) as exc:
        raise CryptoSpotResearchBlocked("Invalid or duplicate specialist evidence") from exc
    consensus = ConsensusEngine().evaluate(state, proposals)
    if (consensus.decision is not Decision.TRADE_CANDIDATE
            or consensus.action != intent.side or len(consensus.supporting_roles) < 2):
        raise CryptoSpotResearchBlocked("Independent research consensus not achieved")
    s = book.snapshot()  # replay checks journal / account policy; never mutate.
    if (s.market != "CRYPTO_PAPER" or s.currency != "USDT"
            or s.account_id != book.account_id
            or s.live_trading_enabled is not False
            or s.exchange_orders_transmitted != 0
            or s.real_market_evidence_verified is not False
            or s.cash_cents + s.remaining_cost_basis_cents != s.initial_cents + s.realized_net_pnl_cents):
        raise CryptoSpotResearchBlocked("Local crypto paper account failed replay checks")
    if book.limits.paper_enabled is not True:
        raise CryptoSpotResearchBlocked("Paper research access disabled")
    if observed < s.last_observed_epoch:
        raise CryptoSpotResearchBlocked("Intent quote predates the ledger head")
    qty, price = _integer(intent.quantity_microcoin, min_value=1), _integer(intent.price_cents_per_coin, min_value=1)
    numerator = qty * price
    if numerator > 10**21:
        raise CryptoSpotResearchBlocked("Conservative notional overflow")
    notional = (numerator + 999_999) // 1_000_000 if intent.side == "BUY" else numerator // 1_000_000
    fee = (notional * book.limits.fee_bps + 9_999) // 10_000
    if notional < 100:
        raise CryptoSpotResearchBlocked("Dust or unrepresentable synthetic trade")
    if intent.side == "BUY":
        if (s.kill_active or s.realized_net_pnl_cents <= -book.limits.max_session_loss_cents
                or notional > book.limits.max_order_cents
                or s.remaining_cost_basis_cents + notional + fee > book.limits.max_exposure_cents
                or s.cash_cents < notional + fee):
            raise CryptoSpotResearchBlocked("Existing Stage97 admission / risk veto denies synthetic entry")
    elif qty > s.position_microcoin or notional <= fee:
        raise CryptoSpotResearchBlocked("Uncovered or invalid protective synthetic exit")
    return CryptoSpotResearchReceipt(
        "SYNTHETIC_RESEARCH_ONLY_NO_EXECUTION", intent.side, "BTC-USDT", "USDT",
        qty, notional, fee, s.account_id, s.journal_revision, s.journal_tip,
        consensus.supporting_roles,
    )
