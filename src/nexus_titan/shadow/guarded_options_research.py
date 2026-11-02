"""Stage 23: opt-in, BUY-only *offline research* risk/veto admission bridge.

Integrates the existing authoritative risk engine, exact contract risk
limits, Red-Team advisory veto, and default-deny paper permission BEFORE
creating a Stage19 research ledger reservation or simulating a fill.

No actual broker, verified feed, production paper account, live execution,
automatic strategy promotion, or external risk authorization exists here.
Direct Stage19 research APIs remain independent and are not retrofitted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from nexus_titan.core.permissions import Action, Decision, decide
from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import ResearchOptionChainHistory
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.research.adversarial_red_team import (
    RedTeamReport, TradeProposal, challenge_trade,
)
from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from nexus_titan.risk.portfolio_risk import (
    PortfolioRiskConfig, PortfolioRiskManager, PreTradeRiskResult,
)
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.simulation.options_order_reconciliation import (
    ResearchFillEvent, ResearchOptionsOrderStatement,
)
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)


class GuardedPaperResearchError(ValueError):
    """A gate rejected an offline research order or it could not be settled."""


@dataclass(frozen=True, slots=True)
class GuardedPaperResearchResult:
    order_id: str
    paper_permission: Decision
    authoritative_risk: PreTradeRiskResult
    contract_risk: PreTradeRiskResult
    red_team: RedTeamReport
    research_statement: ResearchOptionsOrderStatement
    live_orders_transmitted: int = 0
    approved_for_strategy_promotion: bool = False


def _positive(name: str, value: float, *, allow_zero: bool = False) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or (value < 0 if allow_zero else value <= 0)):
        raise GuardedPaperResearchError(f"{name} must be finite and {'non-negative' if allow_zero else 'positive'}")


def guarded_options_research_buy(
    *,
    ledger: DurableResearchShadowLedger,
    order_id: str,
    event_id: str,
    history: ResearchOptionChainHistory,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    observed_at: datetime,
    strike: float,
    option_type: str,
    lots: int,
    depth: OptionDisplayedDepth,
    stop_price: float,
    max_unit_premium: float,
    expected_edge_bps: float,
    slippage_bps: float,
    fee_buffer: float,
    paper_trading_enabled: bool = False,
    realized_daily_loss_pct: float,
    consecutive_losses: int,
    current_drawdown_pct: float,
    risk_config: PortfolioRiskConfig | None = None,
    costs: IndianCostConfig | None = None,
) -> GuardedPaperResearchResult:
    """Check all permission/risk/veto boundaries before any synthetic ledger write.

    This pilot is single-order and flat-account only. It deliberately refuses
    open reservations, existing inventory, naked shorts and unknown exposure.
    It never claims to model margin or independent exchange risk permission.
    An error *after* reservation triggers a terminal cancel attempt.
    """
    if not isinstance(ledger, DurableResearchShadowLedger):
        raise GuardedPaperResearchError("Stage19 research ledger required")
    if not isinstance(paper_trading_enabled, bool):
        raise GuardedPaperResearchError("paper_trading_enabled must be explicit boolean")
    permission = decide(Action.PAPER_TRADE, paper_trading_enabled=paper_trading_enabled)
    if permission is not Decision.ALLOW:
        raise GuardedPaperResearchError("PAPER_TRADE permission denied by default")
    if not isinstance(order_id, str) or not order_id.strip() or not isinstance(event_id, str) or not event_id.strip():
        raise GuardedPaperResearchError("Nonempty research order_id and event_id required")
    if (not isinstance(observed_at, datetime) or observed_at.tzinfo is None
            or observed_at.utcoffset() is None):
        raise GuardedPaperResearchError("Timezone-aware observation required")
    if not isinstance(contract, PointInTimeContractSpec) or contract.segment != "OPTIONS" or contract.exchange.strip().upper() != "NSE":
        raise GuardedPaperResearchError("NSE OPTIONS contract metadata required")
    if not contract.source_verified or not contract.source_reference:
        raise GuardedPaperResearchError("Reviewed point-in-time contract declaration required")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata" or not calendar.is_open(observed_at):
        raise GuardedPaperResearchError("Observation outside supplied India market calendar")
    if not isinstance(history, ResearchOptionChainHistory) or history.approved_for_strategy_promotion is not False:
        raise GuardedPaperResearchError("Research-only validated option history required")
    if option_type not in ("CE", "PE"):
        raise GuardedPaperResearchError("Only CE or PE BUY research supported")
    if (isinstance(lots, bool) or not isinstance(lots, int) or lots < 1
            or lots > contract.max_lots_per_trade or lots * contract.lot_size > contract.freeze_quantity):
        raise GuardedPaperResearchError("Requested whole lots violate exact contract limits")
    if not isinstance(depth, OptionDisplayedDepth):
        raise GuardedPaperResearchError("Independent displayed-depth declaration required")
    if not depth.source_declared_verified:
        raise GuardedPaperResearchError("Research depth declaration missing")
    if risk_config is not None and not isinstance(risk_config, PortfolioRiskConfig):
        raise GuardedPaperResearchError("Risk configuration invalid")
    if costs is not None and not isinstance(costs, IndianCostConfig):
        raise GuardedPaperResearchError("Cost configuration invalid")
    for name, value, zero in (
        ("strike", strike, False),
        ("stop_price", stop_price, False),
        ("max_unit_premium", max_unit_premium, False),
        ("fee_buffer", fee_buffer, False),
        ("expected_edge_bps", expected_edge_bps, False),
        ("slippage_bps", slippage_bps, True),
        ("realized_daily_loss_pct", realized_daily_loss_pct, True),
        ("current_drawdown_pct", current_drawdown_pct, True),
    ):
        _positive(name, value, allow_zero=zero)
    if isinstance(consecutive_losses, bool) or not isinstance(consecutive_losses, int) or consecutive_losses < 0:
        raise GuardedPaperResearchError("consecutive_losses must be a non-negative integer")
    if max_unit_premium <= stop_price:
        raise GuardedPaperResearchError("BUY protective stop must be below reserved entry ceiling")
    # This is not a broker-admission or portfolio valuation API. Reject any
    # account state for which that absence would disguise risk/exposure.
    state = ledger.status()
    if state.open_order_count or state.reserved_cash or state.option_inventory:
        raise GuardedPaperResearchError("Flat research account with no open reservations required")
    if state.available_cash <= 0:
        raise GuardedPaperResearchError("No available virtual capital")

    matching = (
        snapshot for snapshot in history.snapshots
        if snapshot.observed_at.astimezone(timezone.utc) == observed_at.astimezone(timezone.utc)
    )
    snapshots = tuple(matching)
    if len(snapshots) != 1:
        raise GuardedPaperResearchError("Exactly one source snapshot required at observation")
    quotes = tuple(
        quote for quote in snapshots[0].quotes
        if quote.option_type == option_type and quote.strike == strike
    )
    if len(quotes) != 1:
        raise GuardedPaperResearchError("Exactly one option quote required")
    quote = quotes[0]
    if max_unit_premium < quote.ask:
        raise GuardedPaperResearchError("Reserved maximum premium cannot be below displayed ask")
    if stop_price >= quote.ask:
        raise GuardedPaperResearchError("Protective stop must be below current ask")
    quantity = lots * contract.lot_size
    config = risk_config or PortfolioRiskConfig()

    # Engine used by the existing intelligence pipeline. Its unknown-symbol
    # fallback is insufficient alone, hence the additional exact-contract
    # PortfolioRiskManager veto below. Both must approve every requested unit.
    authoritative = AuthoritativeRiskEngine(config).size_and_validate(
        capital=state.available_cash, entry_price=max_unit_premium,
        stop_price=stop_price, symbol=contract.symbol, lot_size=contract.lot_size,
        tick_size=contract.tick_size, current_exposure=0.0, current_open_positions=0,
        realized_daily_loss_pct=realized_daily_loss_pct,
        consecutive_losses=consecutive_losses,
        current_drawdown_pct=current_drawdown_pct, side="BUY",
    )
    if not authoritative.approved or authoritative.quantity < quantity:
        raise GuardedPaperResearchError("Authoritative risk veto: " + authoritative.reason)

    exact = PortfolioRiskManager(config).evaluate_order(
        capital=state.available_cash, current_exposure=0.0, current_open_positions=0,
        realized_daily_loss_pct=realized_daily_loss_pct,
        consecutive_losses=consecutive_losses,
        entry_price=max_unit_premium, stop_price=stop_price,
        spec=contract.to_instrument_spec(),
        current_drawdown_pct=current_drawdown_pct, side="BUY",
    )
    if not exact.approved or exact.quantity < quantity:
        raise GuardedPaperResearchError("Exact-contract risk veto: " + exact.reason)

    spread_mid = (quote.ask + quote.bid) / 2
    if not math.isfinite(spread_mid) or spread_mid <= 0:
        raise GuardedPaperResearchError("Invalid displayed bid/ask spread")
    observed_spread_bps = (quote.ask - quote.bid) / spread_mid * 10000
    # Never let user reduce the quoted spread to bypass red-team checks.
    red_team = challenge_trade(TradeProposal(
        side="BUY", entry=quote.ask, stop=stop_price, target=None,
        spread_bps=observed_spread_bps, slippage_bps=slippage_bps,
        expected_edge_bps=expected_edge_bps,
        liquidity_available=depth.ask_quantity,
        order_quantity=quantity,
    ))
    if red_team.veto_recommended:
        reasons = "; ".join(f.detail for f in red_team.findings if not f.passed)
        raise GuardedPaperResearchError("Red-Team veto: " + reasons)
    # Verify source quality and freshness BEFORE reserving even research money.
    # Stage17 repeats full history integrity + depth synchronization checks.
    # Use the simulator before mutation, but never settle if any veto occurred.
    simulated = simulate_historical_option_fill(
        history, contract=contract, calendar=calendar, observed_at=observed_at,
        strike=strike, option_type=option_type, side="BUY", lots=lots,
        depth=depth, costs=costs,
    )
    if simulated.approved_for_strategy_promotion or simulated.live_orders_transmitted != 0:
        raise GuardedPaperResearchError("Simulated fill tried to cross a live/approval boundary")

    # The research ledger's own BEGIN IMMEDIATE prevents over-reserving cash.
    # The separate risk and ledger calls are NOT an atomic global admission
    # under cross-process portfolio changes: paper-only and flat-account gate.
    ledger.reserve_buy(
        order_id=order_id, contract=contract, strike=strike,
        option_type=option_type, lots=lots, as_of=observed_at,
        max_unit_premium=max_unit_premium, fee_buffer=fee_buffer,
    )
    try:
        statement = ledger.settle_buy(
            order_id=order_id, contract=contract, strike=strike,
            option_type=option_type, cost_config=costs,
            events=[ResearchFillEvent(
                event_id=event_id, observed_at=observed_at, fragment=simulated,
            )],
        )
    except Exception:
        # Fail closed: do not leave new funds held if simulated settlement
        # rejected the estimate. If cancel also fails, surface both errors.
        try:
            ledger.cancel(order_id)
        except Exception as cancel_exc:
            raise GuardedPaperResearchError(
                "Simulated settlement failed AND reserve cancel failed; manual audit required"
            ) from cancel_exc
        raise
    if statement.live_orders_transmitted != 0 or statement.approved_for_strategy_promotion:
        raise GuardedPaperResearchError("Invalid post-settlement promotion state")
    return GuardedPaperResearchResult(
        order_id=order_id, paper_permission=permission,
        authoritative_risk=authoritative, contract_risk=exact,
        red_team=red_team, research_statement=statement,
    )
