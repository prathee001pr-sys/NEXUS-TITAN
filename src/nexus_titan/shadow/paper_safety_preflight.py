"""Stage32: read-only, conservative safety preflight for TWO isolated paper ledgers.

This is NOT a unified execution router, independent identity attestation,
market data verification, signed risk approval or production readiness check.
All inputs in this process can be untrusted; green only means bounded
software assertions passed in a synthetic/research configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)
from nexus_titan.virtual.order_manager import (
    OrderState, TradingMode, VirtualAccount,
)


@dataclass(frozen=True, slots=True)
class PaperSafetyPreflight:
    account_id: str
    flat_research_gate_passed: bool
    blockers: tuple[str, ...]
    virtual_mode: str
    virtual_reconciled: bool
    guarded_ledger_verified: bool
    virtual_cash: float
    research_cash: float | None
    account_id_match: bool
    verified_market_data: bool = False
    external_identity_verified: bool = False
    global_order_router_verified: bool = False
    approved_for_strategy_promotion: bool = False
    live_orders_transmitted: int = 0
    production_ready: bool = False


def inspect_paper_safety_preflight(
    virtual: VirtualAccount,
    guarded_ledger: DurableResearchShadowLedger,
) -> PaperSafetyPreflight:
    """Return immutable evidence; never place an order or mutate either account.

    Requires both accounts to be flat and protected. This intentionally
    rejects active sessions: it is an admission CONFIGURATION preflight,
    not a portfolio P&L, options-depth or broker reconciliation engine.
    """
    if not isinstance(virtual, VirtualAccount):
        raise TypeError("VirtualAccount required")
    if not isinstance(guarded_ledger, DurableResearchShadowLedger):
        raise TypeError("DurableResearchShadowLedger required")

    blockers: list[str] = []
    same_id = virtual.account_id == guarded_ledger.account_id
    if not same_id:
        blockers.append("Independent account IDs differ; no shared admission identity")
    if virtual.require_pretrade_risk_check is not True:
        blockers.append("Virtual pretrade Risk & Veto check is disabled")
    if virtual.trading_mode != TradingMode.MANUAL_APPROVAL:
        blockers.append("Virtual paper account is not in MANUAL_APPROVAL mode")
    if not callable(virtual.approval_authorizer):
        blockers.append("Authenticated approval callback is not configured")
    if virtual.kill_switched:
        blockers.append("Virtual emergency kill switch active; no new order admission")
    active = {
        OrderState.NEW, OrderState.PENDING_APPROVAL,
        OrderState.ACCEPTED, OrderState.PARTIALLY_FILLED,
    }
    if any(order.state in active for order in virtual.orders.values()):
        blockers.append("Virtual account contains unfinished orders")
    if virtual.positions:
        blockers.append("Virtual account is not flat; external valuation missing")
    try:
        virtual_report = virtual.reconcile()
        reconciled = bool(virtual_report.is_reconciled)
        if not reconciled:
            blockers.append("Virtual account cash/positions reconciliation failed")
    except (TypeError, ValueError, ArithmeticError, KeyError):
        reconciled = False
        blockers.append("Virtual account reconciliation could not be completed")

    ledger_verified = False
    research_cash = None
    try:
        ledger_verified = guarded_ledger.verify_integrity() is True
        status = guarded_ledger.status()
        research_cash = status.cash_balance
        if not guarded_ledger.guarded_paper_mode:
            blockers.append("Research ledger is legacy: atomic paper risk gate disabled")
        if status.open_order_count or status.reserved_cash:
            blockers.append("Research ledger has open reservations")
        if status.option_inventory:
            blockers.append("Research ledger has outstanding unvalued option inventory")
        if status.live_orders_transmitted != 0 or status.approved_for_strategy_promotion:
            blockers.append("Research ledger claims prohibited live/promotion authority")
    except (ResearchLedgerError, sqlite3.DatabaseError, ValueError, TypeError):
        blockers.append("Research ledger integrity/availability check failed")
    if not ledger_verified:
        blockers.append("Research ledger has no verified hash-chain integrity")

    return PaperSafetyPreflight(
        account_id=virtual.account_id,
        flat_research_gate_passed=not blockers,
        blockers=tuple(blockers),
        virtual_mode=virtual.trading_mode.value,
        virtual_reconciled=reconciled,
        guarded_ledger_verified=ledger_verified,
        virtual_cash=virtual.cash_balance,
        research_cash=research_cash,
        account_id_match=same_id,
    )
