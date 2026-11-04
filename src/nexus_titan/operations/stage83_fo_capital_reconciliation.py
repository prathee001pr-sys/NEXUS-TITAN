"""Stage83: one-file synthetic F&O account/portfolio capital reconciliation.

Compares Stage76 operator-declared scenario budget with a coherent Stage55
transactional SQLite snapshot. Read-only; not independently authenticated
and not an authoritative F&O position or global virtual capital ledger.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from nexus_titan.operations.isolated_atomic_execution_book import (
    Stage55IsolatedSyntheticExecutionBook,
    Stage55SyntheticBookBlocked,
)
from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOPortfolioRiskReview, Stage76UnderlyingExposure,
)

_KNOWN = {"NIFTY": "NIFTYOPT", "BANKNIFTY": "BANKNIFTYOPT"}


class Stage83LedgerMismatch(ValueError):
    """Untrusted synthetic capital/position evidence cannot reconcile."""


@dataclass(frozen=True, slots=True)
class Stage83MarketHold:
    underlying: str
    known_open_order_count: int
    reserved_cents: int
    stage76_hypothetical_debit_limit_cents: int


@dataclass(frozen=True, slots=True)
class Stage83OneFileFOReconciliation:
    account_id: str
    virtual_starting_cents: int
    journal_revision: int
    journal_sha256: str
    local_risk_revision: int
    local_kill_switch_active: bool
    simulated_cash_cents: int
    simulated_fees_paid_cents: int
    simulated_notional_paid_cents: int
    simulated_reserved_cents: int
    simulated_available_cents: int
    simulated_committed_cents: int
    planned_hypothetical_debit_cents: int
    markets: tuple[Stage83MarketHold, ...]
    local_single_book_reconciliation_consistent: bool
    local_budget_screen_passed: bool
    research_digest_sha256: str
    blockers: tuple[str, ...]
    # ALWAYS false: local single-file math does not prove global authority.
    independently_verified_real_FO_positions: bool = False
    global_single_atomic_capital_authority: bool = False
    all_legacy_execution_paths_fenced: bool = False
    authenticated_owner_and_risk_telemetry: bool = False
    live_fill_reconciliation_verified: bool = False
    paper_order_authorized: bool = False
    strategy_promotion_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE83_SINGLE_SQLITE_FO_ACCOUNT_RESEARCH_NO_GO"


def inspect_stage83_fo_account_reconciliation(
    book: Stage55IsolatedSyntheticExecutionBook,
    research: Stage76FOPortfolioRiskReview,
) -> Stage83OneFileFOReconciliation:
    if not isinstance(book, Stage55IsolatedSyntheticExecutionBook) or not isinstance(
        research, Stage76FOPortfolioRiskReview
    ):
        raise Stage83LedgerMismatch("Typed book and research budget required")
    if (research.verdict != "STAGE76_OFFLINE_FO_PORTFOLIO_RISK_REVIEW_NO_GO"
            or research.order_submission_authorized is not False
            or research.paper_order_authorized is not False
            or research.live_trading_enabled is not False
            or research.global_mandatory_fo_risk_veto_enforced is not False
            or research.broker_orders_transmitted != 0):
        raise Stage83LedgerMismatch("Stage76 research-only boundary violated")
    if (research.account_id != book.account_id
            or type(research.virtual_capital_cents) is not int
            or research.virtual_capital_cents != book.starting_cents):
        raise Stage83LedgerMismatch("Different account or virtual capital scopes")
    if (not isinstance(research.underlying_exposures, tuple)
            or not 1 <= len(research.underlying_exposures) <= 2
            or type(research.total_hypothetical_debit_cents) is not int
            or not 1 <= research.total_hypothetical_debit_cents <= book.starting_cents):
        raise Stage83LedgerMismatch("Invalid Stage76 planned premium budget")
    limits: dict[str, int] = {}
    for e in research.underlying_exposures:
        if (not isinstance(e, Stage76UnderlyingExposure)
                or e.underlying not in _KNOWN or e.underlying in limits
                or type(e.hypothetical_debit_cents) is not int
                or not 1 <= e.hypothetical_debit_cents <= book.starting_cents):
            raise Stage83LedgerMismatch("Unsupported/duplicate underlying risk allocation")
        limits[e.underlying] = e.hypothetical_debit_cents
    if sum(limits.values()) != research.total_hypothetical_debit_cents:
        raise Stage83LedgerMismatch("Stage76 planned market debit sum mismatch")
    try:
        snap = book.snapshot_local_synthetic_portfolio()
    except Stage55SyntheticBookBlocked as exc:
        raise Stage83LedgerMismatch("Single-SQLite replay or local kill-state unreadable") from exc
    if (not snap.local_integrity_verified
            or snap.initial_cents != research.virtual_capital_cents
            or snap.account_id != research.account_id
            or snap.cross_ledger_authority_verified is not False
            or snap.live_trading_enabled is not False
            or snap.broker_orders_transmitted != 0):
        raise Stage83LedgerMismatch("Unverified local synthetic snapshot")
    groups = {k: [0, 0] for k in limits}
    for order in snap.orders:
        underlyings = [k for k, symbol in _KNOWN.items() if order.symbol == symbol]
        if len(underlyings) != 1 or underlyings[0] not in groups:
            raise Stage83LedgerMismatch("Unplanned instrument in local F&O synthetic book")
        g = groups[underlyings[0]]
        if (type(order.open_hold_cents) is not int or order.open_hold_cents < 0
                or type(order.quantity) is not int or order.quantity < 1
                or type(order.filled_quantity) is not int
                or not 0 <= order.filled_quantity <= order.quantity):
            raise Stage83LedgerMismatch("Invalid local synthetic order economics")
        g[0] += int(order.open_hold_cents > 0)
        g[1] += order.open_hold_cents
    markets = tuple(Stage83MarketHold(
        underlying=k, known_open_order_count=groups[k][0],
        reserved_cents=groups[k][1],
        stage76_hypothetical_debit_limit_cents=limits[k],
    ) for k in sorted(limits))
    if sum(x.reserved_cents for x in markets) != snap.reserved_cents:
        raise Stage83LedgerMismatch("Per-market holds disagree with SQLite head")
    committed = snap.initial_cents - snap.cash_cents + snap.reserved_cents
    if (snap.initial_cents != snap.cash_cents+snap.paid_notional_cents+snap.paid_fees_cents
            or not 0 <= snap.reserved_cents <= snap.cash_cents
            or snap.available_cents != snap.cash_cents-snap.reserved_cents):
        raise Stage83LedgerMismatch("Ledger cash conservation mismatch")
    local_budget = (
        research.local_research_fence_passed is True
        and not snap.kill_switch_active
        and committed <= research.total_hypothetical_debit_cents
        and all(m.reserved_cents <= m.stage76_hypothetical_debit_limit_cents
                for m in markets)
    )
    payload = json.dumps([
        snap.account_id, snap.journal_revision, snap.journal_tip,
        snap.risk_revision, snap.kill_switch_active, committed,
        research.local_research_audit_sha256,
    ], separators=(",", ":"), allow_nan=False).encode("utf-8")
    return Stage83OneFileFOReconciliation(
        account_id=snap.account_id, virtual_starting_cents=snap.initial_cents,
        journal_revision=snap.journal_revision, journal_sha256=snap.journal_tip,
        local_risk_revision=snap.risk_revision,
        local_kill_switch_active=snap.kill_switch_active,
        simulated_cash_cents=snap.cash_cents,
        simulated_fees_paid_cents=snap.paid_fees_cents,
        simulated_notional_paid_cents=snap.paid_notional_cents,
        simulated_reserved_cents=snap.reserved_cents,
        simulated_available_cents=snap.available_cents,
        simulated_committed_cents=committed,
        planned_hypothetical_debit_cents=research.total_hypothetical_debit_cents,
        markets=markets,
        local_single_book_reconciliation_consistent=True,
        local_budget_screen_passed=local_budget,
        research_digest_sha256=hashlib.sha256(payload).hexdigest(),
        blockers=(
            "EXISTING_DIRECT_LEGACY_ORDER_FILL_APIS_NOT_FENCED",
            "STAGE76_RESEARCH_BUDGET_NOT_AUTHENTICATED_AT_ORDER_TIME",
            "MULTI_DATABASE_AND_CRYPTO_CAPITAL_STILL_SEPARATE",
            "NO_REAL_FO_POSITIONS_MTM_SETTLEMENT_MARGIN_OR_EXECUTION",
            "NO_AUTHENTICATED_GLOBAL_RISK_OR_OWNER_AUTHORIZATION",
        ) + (() if local_budget else ("LOCAL_BUDGET_OR_KILL_SWITCH_SCREEN_BLOCKED",)),
    )
