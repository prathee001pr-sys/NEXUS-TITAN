"""Stage77: isolated brokerless F&O synthetic gateway foundation (NO-LIVE).

A cooperative local prototype only: rechecks Stage76 research policy/pulse
then reuses Stage55's single-SQLite synthetic BUY hold/fill/cancel book.
NO direct VirtualAccount/PaperIntentGateway/crypto integration, network or
broker. Caller-supplied packets and telemetry are NOT authenticated.
Checks and DB writes are not one atomic global risk/capital transaction.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook, Stage55SyntheticBookBlocked,
    Stage55SyntheticReceipt,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOResearchPolicy, Stage76FOPortfolioRiskReview,
    Stage76RiskBlocked, Stage76UntrustedRiskTelemetry,
    inspect_stage76_fo_portfolio_risk,
)
from nexus_titan.shadow.stage75_fo_shadow_readiness import Stage75FOShadowReadinessPacket

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9._-]{0,29}\Z", re.ASCII)
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z", re.ASCII)


class Stage77SyntheticGatewayBlocked(PermissionError):
    """No synthetic gateway mutation allowed; not a broker/risk authorization."""


@dataclass(frozen=True, slots=True)
class Stage77GatewayResearchReceipt:
    action: str
    account_id: str
    request_id: str
    selected_stage75_digest_sha256: str
    recomputed_stage76_digest_sha256: str
    event_revision: int
    order_state: str
    reserved_cents_after: int
    available_cents_after: int
    journal_sha256: str
    synthetic_only: bool = True
    risk_telemetry_independently_authenticated: bool = False
    global_legacy_entrypoints_fenced: bool = False
    real_exchange_data_authenticated: bool = False
    single_global_atomic_capital_authority_verified: bool = False
    owner_identity_authenticated: bool = False
    paper_order_authorized: bool = False
    strategy_promotion_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE77_LOCAL_SYNTHETIC_LEDGER_ONLY_NO_GO"


class Stage77BrokerlessFOSyntheticGateway:
    """In-process research adapter. Never export this as a production gateway.

    Opening requires an *empty* Stage55 book; on process restart the existing
    nonempty journal must be handled by a separately reviewed recovery flow.
    Unknown pending orders are not silently adopted or filled.
    """

    def __init__(
        self, *,
        book: Stage55IsolatedSyntheticExecutionBook,
        research_packets: tuple[Stage75FOShadowReadinessPacket, ...],
        policy: Stage76FOResearchPolicy,
    ) -> None:
        if (not isinstance(book, Stage55IsolatedSyntheticExecutionBook)
                or not isinstance(policy, Stage76FOResearchPolicy)
                or not isinstance(research_packets, tuple)
                or not research_packets):
            raise Stage77SyntheticGatewayBlocked("Typed isolated book, policy and research packets required")
        self._book = book
        self._policy = policy
        self._packets = research_packets
        self._active: dict[str, tuple[str, str, int, int, str]] = {}
        status = self._book.inspect()
        if (not status.local_integrity_verified or status.revision != 0
                or status.total_orders != 0 or status.open_reserved_cents != 0):
            raise Stage77SyntheticGatewayBlocked(
                "Nonempty or damaged book needs separate manual recovery, not automatic adoption"
            )
        if (book.policy.max_single_reserve_bps > policy.max_single_debit_bps
                or book.policy.max_open_reserve_bps > policy.max_portfolio_debit_bps):
            raise Stage77SyntheticGatewayBlocked("SQLite reserve caps cannot exceed Stage76 research policy")
        accounts = {p.account_id for p in research_packets
                    if isinstance(p, Stage75FOShadowReadinessPacket)}
        if len(accounts) != 1 or accounts != {book.account_id}:
            raise Stage77SyntheticGatewayBlocked("Account scope mismatch")
        if any(p.virtual_capital_cents != book.starting_cents for p in research_packets):
            raise Stage77SyntheticGatewayBlocked("SQLite opening capital differs from Stage75 research assumption")

    def _book_status(self):
        status = self._book.inspect()
        if (status.local_integrity_verified is not True or status.blockers
                or status.synthetic_only is not True
                or status.unbypassable_global_entry is not False
                or status.independently_enforced_risk_veto is not False
                or status.live_trading_enabled is not False
                or status.broker_orders_transmitted != 0
                or type(status.open_reserved_cents) is not int
                or type(status.available_cents) is not int):
            raise Stage77SyntheticGatewayBlocked("Local SQLite journal or no-authority boundary unavailable")
        return status

    def _review(self, telemetry: Stage76UntrustedRiskTelemetry) -> Stage76FOPortfolioRiskReview:
        if not isinstance(telemetry, Stage76UntrustedRiskTelemetry):
            raise Stage77SyntheticGatewayBlocked("Fresh typed synthetic telemetry required")
        try:
            review = inspect_stage76_fo_portfolio_risk(
                packets=self._packets, policy=self._policy, telemetry=telemetry,
            )
        except (Stage76RiskBlocked, ValueError, TypeError) as exc:
            raise Stage77SyntheticGatewayBlocked("Stage76 synthetic risk research recheck failed") from exc
        if (review.local_research_fence_passed is not True
                or review.local_portfolio_budget_checks_passed is not True
                or review.local_untrusted_risk_telemetry_checks_passed is not True
                or review.verdict != "STAGE76_OFFLINE_FO_PORTFOLIO_RISK_REVIEW_NO_GO"
                or review.global_mandatory_fo_risk_veto_enforced is not False
                or review.authoritative_capital_or_reservation_performed is not False
                or review.order_submission_authorized is not False
                or review.live_trading_enabled is not False
                or review.broker_orders_transmitted != 0):
            raise Stage77SyntheticGatewayBlocked("Risk gate denies even local synthetic research mutation")
        self._book_status()
        return review

    def _selected(self, digest: str) -> Stage75FOShadowReadinessPacket:
        if not isinstance(digest, str) or _SHA.fullmatch(digest) is None:
            raise Stage77SyntheticGatewayBlocked("Exact bounded research packet hash required")
        hits = [p for p in self._packets if p.research_packet_sha256 == digest]
        if len(hits) != 1:
            raise Stage77SyntheticGatewayBlocked("Research scenario is not uniquely selected")
        return hits[0]

    @staticmethod
    def _receipt(action: str, digest: str, review: Stage76FOPortfolioRiskReview,
                 receipt: Stage55SyntheticReceipt) -> Stage77GatewayResearchReceipt:
        if (receipt.trading_authority is not False or receipt.synthetic_only is not True
                or receipt.live_orders_transmitted != 0
                or not isinstance(receipt.journal_tip, str)
                or _SHA.fullmatch(receipt.journal_tip) is None):
            raise Stage77SyntheticGatewayBlocked("Stage55 receipt falsely claims external trading authority")
        return Stage77GatewayResearchReceipt(
            action=action, account_id=receipt.account_id,
            request_id=receipt.order_id,
            selected_stage75_digest_sha256=digest,
            recomputed_stage76_digest_sha256=review.local_research_audit_sha256,
            event_revision=receipt.revision, order_state=receipt.order_state,
            reserved_cents_after=receipt.open_reserved_cents,
            available_cents_after=receipt.available_cents,
            journal_sha256=receipt.journal_tip,
        )

    def reserve_synthetic_long_option(
        self, *, research_packet_sha256: str, request_id: str, symbol: str,
        lots: int, lot_size: int, limit_price_cents: int, fee_buffer_cents: int,
        telemetry: Stage76UntrustedRiskTelemetry,
    ) -> Stage77GatewayResearchReceipt:
        """Reserve only a simulated BUY at the declared research debit; no fills."""
        review = self._review(telemetry)
        packet = self._selected(research_packet_sha256)
        if (not isinstance(request_id, str) or _ID.fullmatch(request_id) is None
                or request_id in self._active
                or not isinstance(symbol, str) or _SYMBOL.fullmatch(symbol) is None
                or symbol != packet.option_symbol
                or packet.selected_option_type not in ("CE", "PE")
                or type(lots) is not int or not 1 <= lots <= 30
                or type(lot_size) is not int or not 1 <= lot_size <= 500
                or type(limit_price_cents) is not int or not 1 <= limit_price_cents <= 10**10
                or type(fee_buffer_cents) is not int or not 0 <= fee_buffer_cents <= 10**10):
            raise Stage77SyntheticGatewayBlocked("Invalid synthetic long-option declaration or duplicate request")
        quantity = lots * lot_size
        if (quantity > 10000
                or quantity * limit_price_cents + fee_buffer_cents
                   != packet.long_option_entry_debit_cents):
            raise Stage77SyntheticGatewayBlocked("Declared long-option quantity/fee debit mismatch")
        try:
            booked = self._book.reserve_synthetic_buy(
                request_id=request_id, symbol=symbol, quantity=quantity,
                limit_price_cents=limit_price_cents,
                fee_buffer_cents=fee_buffer_cents,
            )
        except Stage55SyntheticBookBlocked as exc:
            raise Stage77SyntheticGatewayBlocked("Single-DB synthetic capital reserve rejected") from exc
        self._active[request_id] = (
            research_packet_sha256, symbol, quantity, limit_price_cents,
            review.account_id,
        )
        return self._receipt("SYNTHETIC_RESERVE_ONLY", research_packet_sha256, review, booked)

    def record_synthetic_fill(
        self, *, request_id: str, fill_id: str, quantity: int,
        price_cents: int, fee_cents: int,
        telemetry: Stage76UntrustedRiskTelemetry,
    ) -> Stage77GatewayResearchReceipt:
        """No broker or quote: recheck local risk before hypothetical fill."""
        review = self._review(telemetry)
        state = self._active.get(request_id)
        if state is None or state[-1] != review.account_id:
            raise Stage77SyntheticGatewayBlocked("Unknown or restarted fill intent denied")
        if (not isinstance(fill_id, str) or _ID.fullmatch(fill_id) is None
                or type(quantity) is not int or not 1 <= quantity <= state[2]
                or type(price_cents) is not int or not 1 <= price_cents <= state[3]
                or type(fee_cents) is not int or not 0 <= fee_cents <= 10**10):
            raise Stage77SyntheticGatewayBlocked("Invalid synthetic fill declaration")
        try:
            receipt = self._book.record_simulated_fill(
                order_id=request_id, fill_id=fill_id, quantity=quantity,
                price_cents=price_cents, fee_cents=fee_cents,
                evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
            )
        except Stage55SyntheticBookBlocked as exc:
            raise Stage77SyntheticGatewayBlocked("Single-DB simulated fill failed") from exc
        if receipt.order_state == "FILLED_SYNTHETIC":
            del self._active[request_id]
        return self._receipt("SYNTHETIC_FILL_ONLY", state[0], review, receipt)

    def cancel_synthetic_remaining(
        self, *, request_id: str, cancel_id: str,
    ) -> Stage77GatewayResearchReceipt:
        """Allow local hold cancellation even when risk telemetry is unhealthy.

        Book integrity and current in-process request identity remain required.
        """
        state = self._active.get(request_id)
        if state is None or not isinstance(cancel_id, str) or _ID.fullmatch(cancel_id) is None:
            raise Stage77SyntheticGatewayBlocked("Unknown synthetic cancellation ID")
        self._book_status()
        try:
            receipt = self._book.cancel_unfilled(
                order_id=request_id, cancel_id=cancel_id,
                evidence_source="LOCAL_SYNTHETIC_TEST_ONLY",
            )
        except Stage55SyntheticBookBlocked as exc:
            raise Stage77SyntheticGatewayBlocked("Synthetic cancellation failed") from exc
        del self._active[request_id]
        # Cancellation is intentionally not a positive fresh-risk authorization.
        return Stage77GatewayResearchReceipt(
            action="SYNTHETIC_CANCEL_ONLY", account_id=receipt.account_id,
            request_id=request_id, selected_stage75_digest_sha256=state[0],
            recomputed_stage76_digest_sha256="0" * 64,
            event_revision=receipt.revision, order_state=receipt.order_state,
            reserved_cents_after=receipt.open_reserved_cents,
            available_cents_after=receipt.available_cents,
            journal_sha256=receipt.journal_tip,
        )
