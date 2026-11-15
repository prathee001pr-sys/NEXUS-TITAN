"""Stage47: conservative synthetic paper-only Risk & Veto boundary.

Adds one opt-in BUY entry path over Stage45/Stage43. Both the active account's
authoritative and *exact synthetic instrument* risk engines must approve,
followed by bounded quote freshness/spread/depth and adversarial Red-Team veto.

No broker, genuine exchange feed, independent security process or durable
cross-ledger risk approval exists. Direct legacy APIs remain reachable. This
module does NOT make Risk & Veto globally mandatory.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math

from nexus_titan.operations.offline_entry_readiness import (
    Stage45ConservativePaperEntry, Stage45EntryBlocked,
)
from nexus_titan.operations.paper_deployment import PaperOnlyDeployment
from nexus_titan.research.adversarial_red_team import TradeProposal, challenge_trade
from nexus_titan.risk.authoritative_risk import AuthoritativeRiskEngine
from nexus_titan.risk.portfolio_risk import InstrumentSpec, PortfolioRiskManager
from nexus_titan.shadow.paper_intent_gateway import PaperIntentResult


class Stage47RiskVetoBlocked(PermissionError):
    """New research BUY blocked; no order should be requested."""


@dataclass(frozen=True, slots=True)
class SyntheticQuoteEvidence:
    """Explicit *untrusted synthetic QA* evidence; not a verified feed."""

    observed_at: datetime
    bid: float
    ask: float
    displayed_ask_quantity: int
    expected_edge_bps: float
    slippage_bps: float
    source_reference: str = "SYNTHETIC/LOCAL_QA"
    realized_daily_loss_pct: float = 0.0
    consecutive_losses: int = 0
    current_drawdown_pct: float = 0.0


@dataclass(frozen=True, slots=True)
class SyntheticBuyProposal:
    symbol: str
    quantity: int
    stop_price: float
    lot_size: int = 1
    instrument_type: str = "EQUITY_DELIVERY"


@dataclass(frozen=True, slots=True)
class Stage47RiskVetoPolicy:
    """Conservative numeric caps for untrusted local research quotes."""

    max_quote_age_seconds: int = 30
    max_spread_bps: float = 60.0
    max_slippage_bps: float = 25.0
    max_lots_per_trade: int = 20
    max_order_units: int = 200


@dataclass(frozen=True, slots=True)
class Stage47RiskVetoDecision:
    account_id: str
    blockers: tuple[str, ...]
    new_synthetic_buy_permitted: bool
    maximum_authoritative_units: int
    maximum_exact_risk_units: int
    observed_spread_bps: float | None
    quote_age_seconds: float | None
    red_team_veto: bool
    stage45_ready: bool
    # All unchanged false: local screening is not secure global admission.
    external_quote_authentication: bool = False
    independent_global_risk_veto_enforced: bool = False
    independent_human_identity_verified: bool = False
    cross_ledger_atomicity_verified: bool = False
    licensed_real_data_verified: bool = False
    automatic_strategy_promotion_allowed: bool = False
    broker_orders_transmitted: int = 0
    production_ready: bool = False


def _number(value: object, *, positive: bool = False) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and (value > 0 if positive else value >= 0)
    )


def _count(value: object, minimum: int = 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def inspect_stage47_risk_veto(
    deployment: PaperOnlyDeployment,
    proposal: SyntheticBuyProposal,
    quote: SyntheticQuoteEvidence,
    *,
    policy: Stage47RiskVetoPolicy = Stage47RiskVetoPolicy(),
    now: datetime | None = None,
) -> Stage47RiskVetoDecision:
    """Fail closed on missing, stale or untrusted inputs. READ ONLY.

    The time clock, quote and declared risk metrics are untrusted caller data.
    For an actual secured market admission, an independently authenticated
    quote and identity source plus a mandatory process boundary is required.
    """
    if not isinstance(deployment, PaperOnlyDeployment):
        raise TypeError("Stage43 paper-only deployment required")
    problems: list[str] = []
    auth_qty = 0
    exact_qty = 0
    age: float | None = None
    spread: float | None = None
    red_veto = True

    stage45 = Stage45ConservativePaperEntry(deployment).status()
    if not stage45.can_create_new_synthetic_buy_intent:
        problems.append("Stage45 paper-entry readiness denied: " + "; ".join(stage45.blockers))

    if not isinstance(policy, Stage47RiskVetoPolicy) or not (
        _count(policy.max_quote_age_seconds)
        and policy.max_quote_age_seconds <= 120
        and _number(policy.max_spread_bps, positive=True)
        and policy.max_spread_bps <= 500
        and _number(policy.max_slippage_bps)
        and policy.max_slippage_bps <= 100
        and _count(policy.max_lots_per_trade)
        and policy.max_lots_per_trade <= 100
        and _count(policy.max_order_units)
        and policy.max_order_units <= 10000
    ):
        problems.append("Stage47 Risk & Veto policy is invalid or exceeds offline bounds")

    proposal_valid = (
        isinstance(proposal, SyntheticBuyProposal)
        and isinstance(proposal.symbol, str)
        and 1 <= len(proposal.symbol.strip()) <= 80
        and _count(proposal.quantity)
        and _count(proposal.lot_size)
        and _number(proposal.stop_price, positive=True)
        and proposal.instrument_type == "EQUITY_DELIVERY"
        and isinstance(policy, Stage47RiskVetoPolicy)
        and _count(policy.max_order_units)
        and proposal.quantity <= policy.max_order_units
        and proposal.quantity % proposal.lot_size == 0
    )
    if not proposal_valid:
        problems.append("Unsupported or invalid synthetic BUY proposal (no F&O permission)")

    quote_valid = (
        isinstance(quote, SyntheticQuoteEvidence)
        and isinstance(quote.source_reference, str)
        and quote.source_reference.startswith("SYNTHETIC/")
        and 11 <= len(quote.source_reference) <= 128
        and _number(quote.bid, positive=True)
        and _number(quote.ask, positive=True)
        and quote.bid <= quote.ask
        and _count(quote.displayed_ask_quantity)
        and _number(quote.expected_edge_bps)
        and _number(quote.slippage_bps)
        and _number(quote.realized_daily_loss_pct)
        and _count(quote.consecutive_losses, minimum=0)
        and _number(quote.current_drawdown_pct)
    )
    if not quote_valid:
        problems.append("Missing/invalid untrusted synthetic quote or risk observations")

    reference_now = datetime.now(timezone.utc) if now is None else now
    if (not isinstance(reference_now, datetime)
            or reference_now.tzinfo is None
            or reference_now.utcoffset() is None):
        problems.append("Current reference time must be timezone-aware")
    if not isinstance(quote, SyntheticQuoteEvidence) or (
        not isinstance(quote.observed_at, datetime)
        or quote.observed_at.tzinfo is None
        or quote.observed_at.utcoffset() is None
    ):
        problems.append("Quote observation time must be timezone-aware")
    elif isinstance(reference_now, datetime) and reference_now.tzinfo and reference_now.utcoffset() is not None:
        age = (reference_now.astimezone(timezone.utc) - quote.observed_at.astimezone(timezone.utc)).total_seconds()
        if (not isinstance(policy, Stage47RiskVetoPolicy)
                or not _count(policy.max_quote_age_seconds)
                or age < 0 or age > policy.max_quote_age_seconds):
            problems.append("Synthetic quote is future-dated or stale")

    if quote_valid:
        mid = (quote.ask + quote.bid) / 2.0
        spread = (quote.ask - quote.bid) / mid * 10000.0 if mid > 0 else None
        if (spread is None or not math.isfinite(spread)
                or not isinstance(policy, Stage47RiskVetoPolicy)
                or not _number(policy.max_spread_bps, positive=True)
                or spread > policy.max_spread_bps):
            problems.append("Quote spread exceeds the conservative policy")
        if (not isinstance(policy, Stage47RiskVetoPolicy)
                or not _number(policy.max_slippage_bps)
                or quote.slippage_bps > policy.max_slippage_bps):
            problems.append("Estimated slippage exceeds the conservative policy")

    if proposal_valid and quote_valid:
        if quote.displayed_ask_quantity < proposal.quantity:
            problems.append("Insufficient displayed synthetic ask liquidity")
        if quote.ask <= proposal.stop_price:
            problems.append("BUY stop must be below synthetic ask")
        if abs(quote.ask - round(quote.ask / 0.05) * 0.05) > 1e-7:
            problems.append("Synthetic ask not aligned to the research tick grid")
        virtual = deployment.virtual_account
        try:
            active = virtual.risk_engine.config
            effective = virtual.risk_engine._portfolio_mgr.config
            if (active != effective
                    or active.max_risk_per_trade_pct != virtual.risk_per_trade_pct
                    or active.max_portfolio_exposure_pct != virtual.max_portfolio_exposure_pct):
                problems.append("Active risk policy or effective portfolio policy drift")
            else:
                combined_daily = max(quote.realized_daily_loss_pct, virtual._daily_loss_pct())
                combined_losses = max(quote.consecutive_losses, virtual._consecutive_losses())
                combined_drawdown = max(quote.current_drawdown_pct, virtual.current_drawdown_pct)
                # Brokerless synthetic equity only. F&O metadata is NOT inferred
                # from DEFAULT_INSTRUMENT_SPECS or operator source labels.
                spec = InstrumentSpec(
                    symbol=proposal.symbol.strip().upper(), lot_size=proposal.lot_size,
                    tick_size=0.05, max_lots_per_trade=policy.max_lots_per_trade,
                    freeze_quantity=policy.max_order_units,
                )
                metrics = dict(
                    capital=virtual.current_capital,
                    current_exposure=virtual.current_exposure,
                    current_open_positions=len(virtual.positions),
                    realized_daily_loss_pct=combined_daily,
                    consecutive_losses=combined_losses,
                    current_drawdown_pct=combined_drawdown,
                    entry_price=quote.ask,
                    stop_price=proposal.stop_price,
                    side="BUY",
                )
                authoritative = AuthoritativeRiskEngine(active).size_and_validate(
                    **metrics, symbol=spec.symbol, lot_size=spec.lot_size,
                    tick_size=spec.tick_size,
                )
                exact = PortfolioRiskManager(active).evaluate_order(**metrics, spec=spec)
                auth_qty = authoritative.quantity if authoritative.approved else 0
                exact_qty = exact.quantity if exact.approved else 0
                if not authoritative.approved or authoritative.quantity < proposal.quantity:
                    problems.append("Authoritative risk veto: " + authoritative.reason)
                if not exact.approved or exact.quantity < proposal.quantity:
                    problems.append("Exact synthetic contract risk veto: " + exact.reason)
                # Conservative explicit cap is never relaxed by unknown-symbol
                # fallback inside the existing authoritative facade.
                if proposal.quantity > policy.max_lots_per_trade * proposal.lot_size:
                    problems.append("Stage47 independent quantity cap breached")
        except Exception:
            problems.append("Authoritative or exact risk evaluation unavailable")
        try:
            red = challenge_trade(TradeProposal(
                side="BUY", entry=quote.ask, stop=proposal.stop_price,
                target=None, spread_bps=spread if spread is not None else 0.0,
                slippage_bps=quote.slippage_bps,
                expected_edge_bps=quote.expected_edge_bps,
                liquidity_available=quote.displayed_ask_quantity,
                order_quantity=proposal.quantity,
            ))
            red_veto = red.veto_recommended
            if red_veto:
                problems.append("Adversarial Red-Team veto: " + "; ".join(
                    finding.scenario for finding in red.findings if not finding.passed
                ))
        except Exception:
            problems.append("Adversarial Red-Team evaluation unavailable")
    else:
        problems.append("No complete Risk & Veto evidence for this proposal")

    blockers = tuple(dict.fromkeys(problems))
    return Stage47RiskVetoDecision(
        account_id=deployment.config.account_id,
        blockers=blockers,
        new_synthetic_buy_permitted=not blockers,
        maximum_authoritative_units=auth_qty,
        maximum_exact_risk_units=exact_qty,
        observed_spread_bps=spread,
        quote_age_seconds=age,
        red_team_veto=red_veto,
        stage45_ready=stage45.can_create_new_synthetic_buy_intent,
    )


class Stage47OfflineRiskVetoEntry:
    """Optional guarded synthetic BUY facade; never approves or executes fills.

    Other direct application methods are NOT disabled and can bypass this
    extra advisory layer. This is NOT a mandatory broker-side order boundary.
    """

    def __init__(self, deployment: PaperOnlyDeployment):
        if not isinstance(deployment, PaperOnlyDeployment):
            raise TypeError("Stage43 paper-only deployment required")
        self._deployment = deployment

    def inspect(
        self, proposal: SyntheticBuyProposal, quote: SyntheticQuoteEvidence,
        *, policy: Stage47RiskVetoPolicy = Stage47RiskVetoPolicy(),
        now: datetime | None = None,
    ) -> Stage47RiskVetoDecision:
        return inspect_stage47_risk_veto(self._deployment, proposal, quote, policy=policy, now=now)

    def request_buy(
        self, proposal: SyntheticBuyProposal, quote: SyntheticQuoteEvidence,
        *, policy: Stage47RiskVetoPolicy = Stage47RiskVetoPolicy(),
        now: datetime | None = None,
    ) -> PaperIntentResult:
        verdict = self.inspect(proposal, quote, policy=policy, now=now)
        if not verdict.new_synthetic_buy_permitted:
            raise Stage47RiskVetoBlocked("Synthetic paper BUY vetoed: " + "; ".join(verdict.blockers))
        # Stage45 and Stage43 recheck flatness/session/CAS/manual/risk.
        # The Red-Team check is NOT atomic with this second order submission.
        try:
            return Stage45ConservativePaperEntry(self._deployment).request_buy(
                symbol=proposal.symbol,
                quantity=proposal.quantity,
                entry_price=quote.ask,
                stop_price=proposal.stop_price,
                lot_size=proposal.lot_size,
                instrument_type=proposal.instrument_type,
            )
        except Stage45EntryBlocked as exc:
            raise Stage47RiskVetoBlocked("Underlying Stage45 paper entry denied") from exc
