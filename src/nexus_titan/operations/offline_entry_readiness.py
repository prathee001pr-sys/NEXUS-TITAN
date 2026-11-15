"""Stage45: conservative offline-only *new BUY* readiness gate.

This is an additional local facade over Stage43 paper deployment. It refuses
new synthetic BUY intents if either independent ledger is not demonstrably
flat, no-change and balanced. It neither unifies two SQLite books atomically,
authenticates a human, nor blocks legacy APIs outside this wrapper. Never use
this gate as a broker permission or as evidence of market/shadow readiness.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from nexus_titan.operations.paper_deployment import (
    PaperOnlyDeployment, PaperDeploymentBlocked,
)
from nexus_titan.shadow.paper_intent_gateway import PaperIntentResult
from nexus_titan.virtual.order_manager import OrderState


@dataclass(frozen=True, slots=True)
class Stage45OfflineReadiness:
    account_id: str
    blockers: tuple[str, ...]
    can_create_new_synthetic_buy_intent: bool
    virtual_internal_reconciliation_passed: bool
    research_hash_integrity_passed: bool
    flat_separate_books_observed: bool
    exact_starting_cash_match_observed: bool
    # No external validation is supplied by any of these synthetic checks.
    real_market_data_authenticated: bool = False
    externally_authenticated_human_approval: bool = False
    independently_enforced_global_risk_veto: bool = False
    cross_ledger_atomicity_verified: bool = False
    extended_real_shadow_validation_verified: bool = False
    strategy_promotion_allowed: bool = False
    broker_orders_transmitted: int = 0
    production_ready: bool = False


class Stage45EntryBlocked(PermissionError):
    """Fail closed; no new synthetic paper entry was requested."""


def _cents(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Unexpected balance type")
    try:
        exact = Decimal(str(value))
        if not exact.is_finite() or exact < 0:
            raise ValueError("Invalid balance")
        scaled = exact * 100
        if scaled != scaled.to_integral_value():
            raise ValueError("Balance precision exceeds a cent")
        return int(scaled)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError("Non-finite or non-cent-precision balance") from exc


def inspect_stage45_offline_entry(deployment: PaperOnlyDeployment) -> Stage45OfflineReadiness:
    """Read-only snapshot. Any uncertainty blocks new BUY; exits not handled here.

    This is NOT an atomic cross-database transaction. A concurrent writer could
    still race the check; underlying Stage43 CAS/gateway checks remain in force.
    This deliberately requires *virgin, flat* cash and no historical fills:
    otherwise the independent VirtualAccount and research books may diverge
    even if their present cash numbers accidentally match.
    """
    if not isinstance(deployment, PaperOnlyDeployment):
        raise TypeError("Stage45 requires Stage43 PaperOnlyDeployment")
    problems: list[str] = []
    virtual_ok = False
    research_ok = False
    flat = False
    exact_cash = False
    virtual = deployment.virtual_account
    research = deployment.research_ledger

    try:
        s = deployment.status()
        problems.extend(s.blockers)
        virtual_ok = s.virtual_reconciled
        research_ok = s.research_ledger_verified
        if (not s.strict_paper_mode or not s.gateway_only_mode
                or s.account_id != deployment.config.account_id):
            problems.append("Strict Stage43 paper gateway/account identity unavailable")
    except Exception:
        problems.append("Stage43 deployment audit unavailable")

    try:
        # No pending/accepted/partially-filled orders, historical fills,
        # positions, blocked margin or any virtual capital adjustments.
        active = {
            OrderState.NEW, OrderState.PENDING_APPROVAL,
            OrderState.ACCEPTED, OrderState.PARTIALLY_FILLED,
        }
        vflat = (
            not virtual.positions
            and all(order.state not in active for order in virtual.orders.values())
            and all(not order.fills and order.filled_qty == 0
                    for order in virtual.orders.values())
            and _cents(virtual.blocked_margin) == 0
            and _cents(virtual.added_capital) == 0
            and _cents(virtual.withdrawn_capital) == 0
            and _cents(virtual.realized_pnl) == 0
        )
        state = research.status()
        rflat = (
            state.open_order_count == 0
            and _cents(state.reserved_cash) == 0
            and not state.option_inventory
            and state.closed_order_count == 0
        )
        flat = bool(vflat and rflat)
        if not flat:
            problems.append("Separate account histories are not virgin and flat")
        exact_cash = (
            virtual.account_id == state.account_id == deployment.config.account_id
            and _cents(virtual.initial_capital) == _cents(state.starting_capital)
            and _cents(virtual.cash_balance) == _cents(state.cash_balance)
            and _cents(virtual.cash_balance) == _cents(state.available_cash)
            and _cents(virtual.cash_balance) == _cents(virtual.initial_capital)
        )
        if not exact_cash:
            problems.append("Cash or account identity diverges across separate books")
        if state.live_orders_transmitted or state.approved_for_strategy_promotion:
            problems.append("Research ledger reports forbidden authority")
    except Exception:
        problems.append("Separate account balances/position state could not be independently audited")

    if not virtual_ok:
        problems.append("Virtual internal reconciliation not verified")
    if not research_ok:
        problems.append("Research hash-chain integrity not verified")

    # Stable order, avoid repeated blockers from Stage43 and our local checks.
    blockers = tuple(dict.fromkeys(problems))
    return Stage45OfflineReadiness(
        account_id=deployment.config.account_id,
        blockers=blockers,
        can_create_new_synthetic_buy_intent=not blockers,
        virtual_internal_reconciliation_passed=virtual_ok,
        research_hash_integrity_passed=research_ok,
        flat_separate_books_observed=flat,
        exact_starting_cash_match_observed=exact_cash,
    )


class Stage45ConservativePaperEntry:
    """Additional restrictive entry facade. No broker, live order or auto fill.

    This does NOT revoke direct access to Stage43, or create an OS-level
    mandatory security boundary. This supports only NEW BUY paper intents.
    Protective exits must use the pre-existing Stage43 emergency mechanisms.
    """

    def __init__(self, deployment: PaperOnlyDeployment):
        if not isinstance(deployment, PaperOnlyDeployment):
            raise TypeError("Stage43 PaperOnlyDeployment is required")
        self._deployment = deployment

    def status(self) -> Stage45OfflineReadiness:
        return inspect_stage45_offline_entry(self._deployment)

    def request_buy(
        self, *, symbol: str, quantity: int, entry_price: float,
        stop_price: float, lot_size: int = 1,
        instrument_type: str = "EQUITY_DELIVERY",
    ) -> PaperIntentResult:
        check = self.status()
        if not check.can_create_new_synthetic_buy_intent:
            raise Stage45EntryBlocked(
                "Stage45 conservatively blocks new synthetic BUY: "
                + "; ".join(check.blockers)
            )
        try:
            # Stage43 rechecks session config, default-deny permission,
            # risk, strict manual approval, durable CAS and research audit.
            return self._deployment.request_buy(
                symbol=symbol, quantity=quantity, entry_price=entry_price,
                stop_price=stop_price, lot_size=lot_size,
                instrument_type=instrument_type,
            )
        except PaperDeploymentBlocked as exc:
            raise Stage45EntryBlocked("Stage43 underlying gateway rejected BUY") from exc
