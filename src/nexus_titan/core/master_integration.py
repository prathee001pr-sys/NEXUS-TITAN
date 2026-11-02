"""Master orchestration boundary for governed NEXUS TITAN research/shadow cycles.

This composition layer connects existing deterministic components. It does not
connect to a broker, create live orders, execute generated code, or mutate risk
and permission policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Iterable

from nexus_titan.core.events import Event
from nexus_titan.core.runtime import CoreRuntime
from nexus_titan.intelligence.consensus import SignalProposal
from nexus_titan.intelligence.market_state import MarketState
from nexus_titan.intelligence.specialist_roles import SpecialistEvidence, adapt_specialist_evidence
from nexus_titan.intelligence.evidence_integrity import EvidenceEnvelope, verify_evidence_envelope
from nexus_titan.intelligence.pipeline import (
    PipelineResult,
    PipelineStatus,
    RiskRequest,
    TradingIntelligencePipeline,
)
from nexus_titan.operations.health import HealthMonitor, HealthReport
from nexus_titan.research.adversarial_red_team import (
    RedTeamReport,
    TradeProposal,
    challenge_trade,
)
from nexus_titan.simulation.digital_twin import StressScenario, apply_stress
from nexus_titan.simulation.execution_simulator import (
    ExecutionRequest,
    ExecutionResult,
    simulate_execution,
)
from nexus_titan.virtual.order_manager import (
    OrderState,
    TradingMode,
    VirtualAccount,
)
from nexus_titan.core.permissions import Action, Decision


class MasterCycleStatus(StrEnum):
    DATA_INVALID = "DATA_INVALID"
    NO_TRADE = "NO_TRADE"
    WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
    RISK_CHECK_REQUIRED = "RISK_CHECK_REQUIRED"
    RISK_REJECTED = "RISK_REJECTED"
    RED_TEAM_VETO = "RED_TEAM_VETO"
    EXECUTION_REJECTED = "EXECUTION_REJECTED"
    EXECUTION_UNFILLED = "EXECUTION_UNFILLED"
    EXECUTION_PARTIAL = "EXECUTION_PARTIAL"
    SHADOW_FILL_SIMULATED = "SHADOW_FILL_SIMULATED"
    VIRTUAL_ORDER_PENDING_APPROVAL = "VIRTUAL_ORDER_PENDING_APPROVAL"
    VIRTUAL_ORDER_STAGING_BLOCKED = "VIRTUAL_ORDER_STAGING_BLOCKED"


@dataclass(frozen=True, slots=True)
class MasterCycleResult:
    status: MasterCycleStatus
    symbol: str
    pipeline: PipelineResult
    red_team: RedTeamReport | None
    execution: ExecutionResult | None
    virtual_order_id: str | None
    virtual_order_state: str | None
    health: HealthReport
    reasons: tuple[str, ...]
    order_submitted: bool = False
    live_trading_enabled: bool = False


class MasterTradingOrchestrator:
    """Connect state -> consensus -> risk -> red-team -> fill simulation.

    Virtual order staging is a separate, opt-in last step. It requires the core
    paper-trade permission to be enabled and an injected MANUAL_APPROVAL account.
    A staged order remains PENDING_APPROVAL; this orchestrator never approves or
    fills it. Live trading remains outside this architecture.
    """

    def __init__(
        self,
        *,
        core: CoreRuntime | None = None,
        pipeline: TradingIntelligencePipeline | None = None,
        health: HealthMonitor | None = None,
    ) -> None:
        self.core = core if core is not None else CoreRuntime()
        self.pipeline = pipeline if pipeline is not None else TradingIntelligencePipeline()
        self.health = health if health is not None else HealthMonitor()
        self._owns_core = core is None

    def run_cycle_from_verified_evidence(
        self, *, state: MarketState, evidence_envelopes: Iterable[EvidenceEnvelope],
        risk_request: RiskRequest | None, execution_request: ExecutionRequest | None,
        expected_edge_bps: float, target_price: float | None = None,
        virtual_account: VirtualAccount | None = None, stage_virtual_order: bool = False,
        instrument_type: str = "FUTURES", max_evidence_age_seconds: int = 300,
    ) -> MasterCycleResult:
        """Verify payload integrity/freshness before adapting specialist evidence.

        This checks byte integrity and timestamps only; source authenticity and
        independent-source claims remain external verification requirements.
        """
        verified: list[SpecialistEvidence] = []
        source_ids: set[str] = set()
        evidence_ids: set[str] = set()
        for envelope in evidence_envelopes:
            ok, issues = verify_evidence_envelope(
                envelope, max_age_seconds=max_evidence_age_seconds
            )
            if not ok:
                raise ValueError("specialist evidence rejected: " + ", ".join(issues))
            if envelope.evidence_id in evidence_ids:
                raise ValueError("duplicate evidence_id in specialist evidence batch")
            evidence_ids.add(envelope.evidence_id)
            payload = envelope.payload
            required = ("role", "action", "reason", "invalidation")
            if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required):
                raise ValueError("specialist evidence payload is missing required text fields")
            if payload["action"] in {"BUY", "SELL"}:
                if envelope.source_id in source_ids:
                    raise ValueError("directional specialist roles must use independent source IDs")
                source_ids.add(envelope.source_id)
            verified.append(SpecialistEvidence(
                role=payload["role"], action=payload["action"],
                reason=payload["reason"], evidence_ref=f"sha256:{envelope.sha256}",
                invalidation=payload["invalidation"],
            ))
        return self.run_cycle_from_evidence(
            state=state, specialist_evidence=verified, risk_request=risk_request,
            execution_request=execution_request, expected_edge_bps=expected_edge_bps,
            target_price=target_price, virtual_account=virtual_account,
            stage_virtual_order=stage_virtual_order, instrument_type=instrument_type,
        )

    def run_cycle_from_evidence(
        self, *, state: MarketState, specialist_evidence: Iterable[SpecialistEvidence],
        risk_request: RiskRequest | None, execution_request: ExecutionRequest | None,
        expected_edge_bps: float, target_price: float | None = None,
        virtual_account: VirtualAccount | None = None, stage_virtual_order: bool = False,
        instrument_type: str = "FUTURES",
    ) -> MasterCycleResult:
        """Run the master cycle from validated role evidence, never inferred signals."""
        proposals = adapt_specialist_evidence(specialist_evidence)
        return self.run_cycle(
            state=state, proposals=proposals, risk_request=risk_request,
            execution_request=execution_request, expected_edge_bps=expected_edge_bps,
            target_price=target_price, virtual_account=virtual_account,
            stage_virtual_order=stage_virtual_order, instrument_type=instrument_type,
        )

    def run_cycle(
        self,
        *,
        state: MarketState,
        proposals: Iterable[SignalProposal],
        risk_request: RiskRequest | None,
        execution_request: ExecutionRequest | None,
        expected_edge_bps: float,
        target_price: float | None = None,
        virtual_account: VirtualAccount | None = None,
        stage_virtual_order: bool = False,
        instrument_type: str = "FUTURES",
    ) -> MasterCycleResult:
        """Evaluate one complete deterministic cycle without transmitting orders."""
        if isinstance(expected_edge_bps, bool) or not isinstance(expected_edge_bps, (int, float)) or not math.isfinite(expected_edge_bps):
            raise ValueError("expected_edge_bps must be finite numeric input")
        if target_price is not None and (isinstance(target_price, bool) or not isinstance(target_price, (int, float)) or not math.isfinite(target_price) or target_price <= 0):
            raise ValueError("target_price must be a finite positive number")
        if stage_virtual_order and virtual_account is None:
            raise ValueError("virtual_account is required when stage_virtual_order is enabled")

        symbol = state.symbol
        self.core.publish(Event("master.cycle.started", {"symbol": symbol}))
        try:
            pipeline_result = self.pipeline.evaluate(state, proposals, risk_request)
            self.health.heartbeat("market_state_and_consensus")
            self.health.heartbeat("authoritative_risk")

            mapped = {
                PipelineStatus.DATA_INVALID: MasterCycleStatus.DATA_INVALID,
                PipelineStatus.NO_TRADE: MasterCycleStatus.NO_TRADE,
                PipelineStatus.WAIT_FOR_CONFIRMATION: MasterCycleStatus.WAIT_FOR_CONFIRMATION,
                PipelineStatus.RISK_CHECK_REQUIRED: MasterCycleStatus.RISK_CHECK_REQUIRED,
                PipelineStatus.RISK_REJECTED: MasterCycleStatus.RISK_REJECTED,
            }
            if pipeline_result.status is not PipelineStatus.SHADOW_CANDIDATE:
                return self._finish(
                    symbol=symbol, status=mapped[pipeline_result.status], pipeline=pipeline_result,
                    red_team=None, execution=None, virtual_order_id=None,
                    virtual_order_state=None, reasons=(pipeline_result.risk_reason,),
                )

            if risk_request is None or execution_request is None:
                return self._finish(
                    symbol=symbol, status=MasterCycleStatus.RISK_CHECK_REQUIRED, pipeline=pipeline_result,
                    red_team=None, execution=None, virtual_order_id=None, virtual_order_state=None,
                    reasons=("Explicit execution simulation inputs are required after risk approval.",),
                )

            self._validate_execution_alignment(risk_request, execution_request, pipeline_result)
            proposal = TradeProposal(
                side=risk_request.side.upper(),
                entry=float(risk_request.entry_price),
                stop=float(risk_request.stop_price),
                target=float(target_price) if target_price is not None else None,
                spread_bps=float(execution_request.spread_bps),
                slippage_bps=float(execution_request.slippage_bps),
                expected_edge_bps=float(expected_edge_bps),
                liquidity_available=float(execution_request.available_quantity),
                order_quantity=float(execution_request.quantity),
            )
            red_team = challenge_trade(proposal)
            self.health.heartbeat("red_team")
            if red_team.veto_recommended:
                return self._finish(
                    symbol=symbol, status=MasterCycleStatus.RED_TEAM_VETO, pipeline=pipeline_result,
                    red_team=red_team, execution=None, virtual_order_id=None,
                    virtual_order_state=None,
                    reasons=tuple(f.detail for f in red_team.findings if not f.passed),
                )

            execution = simulate_execution(execution_request)
            self.health.heartbeat("execution_simulator")
            if execution.status == "REJECTED":
                return self._finish(symbol, MasterCycleStatus.EXECUTION_REJECTED, pipeline_result,
                                    red_team, execution, None, None, (execution.reason,))
            if execution.status == "UNFILLED":
                return self._finish(symbol, MasterCycleStatus.EXECUTION_UNFILLED, pipeline_result,
                                    red_team, execution, None, None, (execution.reason,))
            if execution.status == "PARTIAL":
                return self._finish(symbol, MasterCycleStatus.EXECUTION_PARTIAL, pipeline_result,
                                    red_team, execution, None, None,
                                    ("Partial fill is a simulator result only; no account mutation occurred.",))

            if stage_virtual_order:
                return self._stage_manual_virtual_order(
                    symbol=symbol, pipeline=pipeline_result, red_team=red_team,
                    execution=execution, risk_request=risk_request,
                    account=virtual_account, instrument_type=instrument_type, target_price=target_price,
                )

            return self._finish(
                symbol, MasterCycleStatus.SHADOW_FILL_SIMULATED, pipeline_result,
                red_team, execution, None, None,
                ("Full fill simulated. No virtual-account ledger was changed and no order was submitted.",),
            )
        except Exception as exc:
            self.health.record_failure("master_cycle", type(exc).__name__)
            self.core.audit.append(
                actor="master_orchestrator", action="master_cycle", outcome="error",
                details={"symbol": symbol, "error_type": type(exc).__name__},
            )
            raise

    @staticmethod
    def _validate_execution_alignment(
        risk: RiskRequest, execution: ExecutionRequest, pipeline: PipelineResult,
    ) -> None:
        if execution.side != risk.side.upper():
            raise ValueError("execution side must match consensus/risk direction")
        if not math.isclose(execution.reference_price, risk.entry_price, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError("execution reference price must match the risk-checked entry price")
        if execution.quantity > pipeline.risk_quantity:
            raise ValueError("execution quantity exceeds authoritative risk-approved quantity")
        if risk.lot_size < 1 or execution.quantity % risk.lot_size:
            raise ValueError("execution quantity must be a whole multiple of the approved lot size")

    def _stage_manual_virtual_order(
        self, *, symbol: str, pipeline: PipelineResult, red_team: RedTeamReport,
        execution: ExecutionResult, risk_request: RiskRequest,
        account: VirtualAccount | None, instrument_type: str, target_price: float | None,
    ) -> MasterCycleResult:
        assert account is not None
        permission = self.core.authorize(Action.PAPER_TRADE)
        if permission is not Decision.ALLOW:
            return self._finish(
                symbol, MasterCycleStatus.VIRTUAL_ORDER_STAGING_BLOCKED, pipeline,
                red_team, execution, None, None,
                (f"Core paper-trade permission is {permission.value}; enable it explicitly first.",),
            )
        if account.trading_mode is not TradingMode.MANUAL_APPROVAL:
            return self._finish(
                symbol, MasterCycleStatus.VIRTUAL_ORDER_STAGING_BLOCKED, pipeline,
                red_team, execution, None, None,
                ("Virtual order staging requires an account in MANUAL_APPROVAL mode.",),
            )
        if account.kill_switched:
            return self._finish(
                symbol, MasterCycleStatus.VIRTUAL_ORDER_STAGING_BLOCKED, pipeline,
                red_team, execution, None, None,
                ("Virtual account kill switch is active.",),
            )
        if instrument_type not in {"EQUITY_DELIVERY", "EQUITY_INTRADAY", "FUTURES", "OPTIONS"}:
            raise ValueError("unsupported virtual instrument_type")
        order = account.submit_order(
            symbol=symbol,
            side=risk_request.side,
            quantity=execution.filled_quantity,
            order_type="MARKET",
            entry_price=risk_request.entry_price,
            stop_price=risk_request.stop_price,
            target_price=target_price,
            instrument_type=instrument_type,
            lot_size=risk_request.lot_size,
        )
        if order.state is not OrderState.PENDING_APPROVAL:
            return self._finish(
                symbol, MasterCycleStatus.VIRTUAL_ORDER_STAGING_BLOCKED, pipeline,
                red_team, execution, order.order_id, order.state.value,
                (f"Account returned unexpected order state: {order.state.value}.",),
            )
        return self._finish(
            symbol, MasterCycleStatus.VIRTUAL_ORDER_PENDING_APPROVAL, pipeline,
            red_team, execution, order.order_id, order.state.value,
            ("Virtual order staged for human approval only. It has not been approved or filled.",),
        )

    def stress_preview(self, candles: Iterable[dict], scenario: StressScenario) -> list[dict]:
        """Run a copied deterministic stress path; the input bars are never mutated."""
        stressed = apply_stress(candles, scenario)
        self.core.audit.append(
            actor="master_orchestrator", action="digital_twin_stress_preview", outcome="success",
            details={"scenario": scenario.name, "input_bars": len(stressed)},
        )
        self.health.heartbeat("digital_twin")
        return stressed

    def health_report(self) -> HealthReport:
        return self.health.evaluate(components=[
            "market_state_and_consensus", "authoritative_risk", "red_team",
            "execution_simulator", "digital_twin", "master_cycle",
        ])

    def _finish(
        self, symbol: str, status: MasterCycleStatus, pipeline: PipelineResult,
        red_team: RedTeamReport | None, execution: ExecutionResult | None,
        virtual_order_id: str | None, virtual_order_state: str | None,
        reasons: tuple[str, ...],
    ) -> MasterCycleResult:
        health = self.health_report()
        self.core.audit.append(
            actor="master_orchestrator", action="master_cycle", outcome=status.value,
            details={
                "symbol": symbol,
                "pipeline_status": pipeline.status.value,
                "red_team_veto": red_team.veto_recommended if red_team else None,
                "execution_status": execution.status if execution else None,
                "virtual_order_id": virtual_order_id,
                "order_submitted": False,
                "live_trading_enabled": False,
            },
        )
        self.core.publish(Event("master.cycle.completed", {
            "symbol": symbol, "status": status.value,
            "order_submitted": False, "live_trading_enabled": False,
        }))
        return MasterCycleResult(
            status, symbol, pipeline, red_team, execution, virtual_order_id,
            virtual_order_state, health, reasons, False, False,
        )

    def close(self) -> None:
        if self._owns_core:
            self.core.close()


def register_master_capabilities(core: CoreRuntime) -> tuple[str, ...]:
    """Register lightweight, lazy-loaded master capabilities on a CoreRuntime."""
    existing = {item.name for item in core.modules.list_modules()}
    factories = {
        "market_state_builder": (lambda: __import__(
            "nexus_titan.intelligence.market_state", fromlist=["MarketStateBuilder"]
        ).MarketStateBuilder(), "Validated immutable market-state builder"),
        "trading_intelligence_pipeline": (lambda: TradingIntelligencePipeline(), "Consensus and authoritative risk pipeline"),
        "red_team": (lambda: challenge_trade, "Deterministic adversarial proposal checks"),
        "digital_twin": (lambda: apply_stress, "Deterministic OHLCV stress simulation"),
        "execution_simulator": (lambda: simulate_execution, "Bounded virtual fill simulator"),
        "health_monitor": (lambda: HealthMonitor(), "Component heartbeat and health assessment"),
        "master_trading_orchestrator": (lambda: MasterTradingOrchestrator(core=core), "Governed end-to-end research/shadow cycle"),
    }
    registered: list[str] = []
    for name, (factory, description) in factories.items():
        if name not in existing:
            core.modules.register(name, factory, description=description)
            registered.append(name)
    return tuple(registered)
