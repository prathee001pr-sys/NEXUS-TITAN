"""Stage33: opt-in, brokerless paper-intent gateway for VirtualAccount.

Only prepares order intents; never grants approval, fills an order, sends a
broker request, or synchronizes the independent Stage19 research ledger.
Legacy direct VirtualAccount methods still exist. Not a global admission layer.
"""
from __future__ import annotations

from dataclasses import dataclass

from nexus_titan.core.permissions import Action, Decision, decide
from nexus_titan.shadow.paper_safety_preflight import inspect_paper_safety_preflight
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.virtual.order_manager import (
    OrderSide, OrderState, TradingMode, VirtualAccount, VirtualOrder,
)


class PaperIntentDenied(PermissionError):
    """No account state may change when gateway admission rejects an intent."""


@dataclass(frozen=True, slots=True)
class PaperIntentResult:
    order_id: str
    side: str
    status: str
    requires_manual_approval: bool = True
    simulated_only: bool = True
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


class PaperIntentGateway:
    """Explicit paper-only gateway, separate from raw legacy research APIs."""

    def __init__(self, virtual: VirtualAccount, research: DurableResearchShadowLedger):
        if not isinstance(virtual, VirtualAccount) or not isinstance(research, DurableResearchShadowLedger):
            raise TypeError("VirtualAccount and guarded research ledger are required")
        self.virtual = virtual
        self.research = research

    def _permissions(self, *, paper_trading_enabled: bool) -> None:
        if not isinstance(paper_trading_enabled, bool) or decide(
            Action.PAPER_TRADE, paper_trading_enabled=paper_trading_enabled,
        ) is not Decision.ALLOW:
            raise PaperIntentDenied("Explicit PAPER_TRADE permission required")
        account = self.virtual
        if account.kill_switched:
            raise PaperIntentDenied("Kill switch blocks new gateway paper intents")
        if account.trading_mode is not TradingMode.MANUAL_APPROVAL:
            raise PaperIntentDenied("Gateway requires MANUAL_APPROVAL")
        if account.require_pretrade_risk_check is not True:
            raise PaperIntentDenied("Authoritative pretrade risk cannot be disabled")
        if not callable(account.approval_authorizer):
            raise PaperIntentDenied("Configured identity approval callback required")
        if account.account_id != self.research.account_id:
            raise PaperIntentDenied("Virtual and research account IDs differ")
        try:
            guarded = self.research.guarded_paper_mode
            intact = self.research.verify_integrity()
        except Exception as exc:
            raise PaperIntentDenied("Research ledger integrity unavailable") from exc
        if not guarded or not intact:
            raise PaperIntentDenied("Atomic research risk gate required")
        if not account.reconcile().is_reconciled:
            raise PaperIntentDenied("Virtual account reconciliation failed")

    @staticmethod
    def _as_result(order: VirtualOrder) -> PaperIntentResult:
        if order.state is not OrderState.PENDING_APPROVAL:
            raise PaperIntentDenied("Gateway could not enforce mandatory manual approval")
        return PaperIntentResult(order.order_id,order.side.value,order.state.value)

    def request_buy(
        self, *, symbol: str, quantity: int, entry_price: float,
        stop_price: float, paper_trading_enabled: bool = False,
        lot_size: int = 1, instrument_type: str = "EQUITY_DELIVERY",
    ) -> PaperIntentResult:
        """Create an unfilled BUY intent after a conservative *flat* preflight."""
        self._permissions(paper_trading_enabled=paper_trading_enabled)
        report=inspect_paper_safety_preflight(self.virtual,self.research)
        if not report.flat_research_gate_passed:
            raise PaperIntentDenied("Flat guarded research preflight denied: "+"; ".join(report.blockers))
        order=self.virtual.submit_order(
            symbol,OrderSide.BUY,quantity,entry_price=entry_price,
            stop_price=stop_price,lot_size=lot_size,
            instrument_type=instrument_type,
        )
        return self._as_result(order)

    def request_sell_to_close(
        self, *, symbol: str, quantity: int,
        paper_trading_enabled: bool = False,
    ) -> PaperIntentResult:
        """Manual SELL intent; only already-owned units, no naked short."""
        self._permissions(paper_trading_enabled=paper_trading_enabled)
        if not isinstance(symbol,str) or not symbol.strip():
            raise PaperIntentDenied("Nonempty symbol required")
        if isinstance(quantity,bool) or not isinstance(quantity,int) or quantity<=0:
            raise PaperIntentDenied("Positive whole-unit quantity required")
        key=symbol.strip().upper()
        pos=self.virtual.positions.get(key)
        if pos is None or quantity>pos.quantity or pos.quantity<=0:
            raise PaperIntentDenied("SELL exceeds owned position; naked shorts prohibited")
        if any(o.symbol==key and o.side is OrderSide.SELL and o.state in (
            OrderState.NEW,OrderState.PENDING_APPROVAL,OrderState.ACCEPTED,
            OrderState.PARTIALLY_FILLED,
        ) for o in self.virtual.orders.values()):
            raise PaperIntentDenied("Existing unfinished SELL prevents double-close intent")
        order=self.virtual.submit_order(
            key,OrderSide.SELL,quantity,
            instrument_type=pos.instrument_type,
            lot_size=1,
        )
        return self._as_result(order)
