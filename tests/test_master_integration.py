from datetime import datetime, timezone

import pytest

from nexus_titan.core.config import Settings
from nexus_titan.core.master_integration import (
    MasterCycleStatus, MasterTradingOrchestrator, register_master_capabilities,
)
from nexus_titan.core.runtime import CoreRuntime
from nexus_titan.intelligence.market_state import MarketStateBuilder
from nexus_titan.intelligence.pipeline import RiskRequest
from nexus_titan.intelligence.consensus import SignalProposal
from nexus_titan.simulation.execution_simulator import ExecutionRequest
from nexus_titan.simulation.digital_twin import StressScenario
from nexus_titan.virtual.order_manager import TradingMode, VirtualAccount


def valid_state():
    now = datetime.now(timezone.utc)
    return MarketStateBuilder().build(
        exchange="NSE", symbol="NIFTY_TEST_FUT", interval="1m",
        event_time=now, ingest_time=now,
        price_volume={"open":100.0,"high":101.0,"low":99.0,"close":100.0,"volume":1000},
        regime={"label":"TEST_REGIME"}, options_flow={"source":"TEST"},
        context={"session":"TEST"}, provenance={"source_id":"fixture:test","dataset":"synthetic_test"},
    )


def proposals():
    return [
        SignalProposal("TREND", "BUY", "Uptrend fixture", "fixture:trend", "Close below 95"),
        SignalProposal("MOMENTUM", "BUY", "Momentum fixture", "fixture:momentum", "Momentum turns negative"),
    ]


def risk_request():
    return RiskRequest(capital=50_000, entry_price=100, stop_price=95,
                       symbol="NIFTY_TEST_FUT", side="BUY", lot_size=1)


def execution_request(*, quantity=1, available=10, latency=0):
    return ExecutionRequest("BUY", quantity, 100, available,
                            spread_bps=2, slippage_bps=1,
                            latency_ms=latency, max_latency_ms=1000)


def test_registry_registers_master_capabilities_lazily_and_idempotently():
    core = CoreRuntime()
    first = register_master_capabilities(core)
    second = register_master_capabilities(core)
    assert "master_trading_orchestrator" in first
    assert second == ()
    assert not core.modules.is_loaded("master_trading_orchestrator")
    orchestrator = core.load_module("master_trading_orchestrator")
    assert isinstance(orchestrator, MasterTradingOrchestrator)
    core.close()


def test_full_cycle_connects_consensus_risk_redteam_and_execution_simulation():
    core = CoreRuntime(settings=Settings(paper_trading_enabled=False))
    orchestrator = MasterTradingOrchestrator(core=core)
    result = orchestrator.run_cycle(
        state=valid_state(), proposals=proposals(), risk_request=risk_request(),
        execution_request=execution_request(), expected_edge_bps=20,
    )
    assert result.status is MasterCycleStatus.SHADOW_FILL_SIMULATED
    assert result.pipeline.risk_approved is True
    assert result.red_team is not None and result.red_team.veto_recommended is False
    assert result.execution is not None and result.execution.status == "FILLED"
    assert result.order_submitted is False and result.live_trading_enabled is False
    assert any(x.action == "master_cycle" for x in core.audit.records())
    core.close()


def test_redteam_veto_blocks_execution():
    orchestrator = MasterTradingOrchestrator()
    result = orchestrator.run_cycle(
        state=valid_state(), proposals=proposals(), risk_request=risk_request(),
        execution_request=ExecutionRequest("BUY", 1, 100, 10, spread_bps=50, slippage_bps=50),
        expected_edge_bps=10,
    )
    assert result.status is MasterCycleStatus.RED_TEAM_VETO
    assert result.execution is None
    orchestrator.close()


def test_conflicting_consensus_fails_closed_before_risk_or_execution():
    opposing = proposals() + [SignalProposal("RISK_OFF", "SELL", "Opposes", "fixture:opposing", "Regime turns bullish")]
    orchestrator = MasterTradingOrchestrator()
    result = orchestrator.run_cycle(
        state=valid_state(), proposals=opposing, risk_request=risk_request(),
        execution_request=execution_request(), expected_edge_bps=20,
    )
    assert result.status is MasterCycleStatus.WAIT_FOR_CONFIRMATION
    assert result.execution is None
    orchestrator.close()


def test_quantity_cannot_exceed_authoritative_risk_result():
    orchestrator = MasterTradingOrchestrator()
    with pytest.raises(ValueError, match="exceeds"):
        orchestrator.run_cycle(
            state=valid_state(), proposals=proposals(), risk_request=risk_request(),
            execution_request=execution_request(quantity=100000), expected_edge_bps=20,
        )
    orchestrator.close()


def test_redteam_blocks_underfunded_liquidity_before_execution_simulation():
    orchestrator = MasterTradingOrchestrator()
    result = orchestrator.run_cycle(
        state=valid_state(), proposals=proposals(), risk_request=risk_request(),
        execution_request=execution_request(quantity=3, available=1), expected_edge_bps=20,
    )
    assert result.status is MasterCycleStatus.RED_TEAM_VETO
    assert result.execution is None
    assert result.virtual_order_id is None
    orchestrator.close()


def test_staging_requires_explicit_permission_and_manual_approval_account():
    core = CoreRuntime(settings=Settings(paper_trading_enabled=False))
    account = VirtualAccount("MASTER-STAGE-BLOCKED", 50_000, trading_mode=TradingMode.MANUAL_APPROVAL)
    orchestrator = MasterTradingOrchestrator(core=core)
    blocked = orchestrator.run_cycle(
        state=valid_state(), proposals=proposals(), risk_request=risk_request(),
        execution_request=execution_request(), expected_edge_bps=20,
        virtual_account=account, stage_virtual_order=True,
    )
    assert blocked.status is MasterCycleStatus.VIRTUAL_ORDER_STAGING_BLOCKED
    assert account.orders == {}
    core.close()


def test_opt_in_staging_creates_pending_approval_only_never_fills():
    core = CoreRuntime(settings=Settings(paper_trading_enabled=True))
    account = VirtualAccount("MASTER-STAGE-MANUAL", 50_000, trading_mode=TradingMode.MANUAL_APPROVAL)
    orchestrator = MasterTradingOrchestrator(core=core)
    result = orchestrator.run_cycle(
        state=valid_state(), proposals=proposals(), risk_request=risk_request(),
        execution_request=execution_request(), expected_edge_bps=20,
        virtual_account=account, stage_virtual_order=True,
    )
    assert result.status is MasterCycleStatus.VIRTUAL_ORDER_PENDING_APPROVAL
    order = account.orders[result.virtual_order_id]
    assert order.state.value == "PENDING_APPROVAL"
    assert order.filled_qty == 0
    assert result.order_submitted is False and result.live_trading_enabled is False
    core.close()


def test_digital_twin_preview_does_not_mutate_source_bars():
    orchestrator = MasterTradingOrchestrator()
    source = [{"open":100,"high":101,"low":99,"close":100,"volume":1000}]
    original = [dict(source[0])]
    stressed = orchestrator.stress_preview(source, StressScenario("test_shock", gap_pct=-1, intrabar_shock_pct=1))
    assert source == original
    assert stressed != source
    orchestrator.close()
