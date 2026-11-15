from datetime import datetime, timezone

import pytest

from nexus_titan.core.audit import AuditLedger
from nexus_titan.core.master_integration import MasterCycleStatus, MasterTradingOrchestrator
from nexus_titan.evolve.governance import GovernedEvolveService
from nexus_titan.evolve.research import ResearchNote
from nexus_titan.intelligence.market_state import MarketStateBuilder
from nexus_titan.intelligence.specialist_roles import (
    SPECIALIST_ROLES, SpecialistEvidence, adapt_specialist_evidence,
)
from nexus_titan.intelligence.pipeline import RiskRequest
from nexus_titan.simulation.execution_simulator import ExecutionRequest


def state():
    now = datetime.now(timezone.utc)
    return MarketStateBuilder().build(
        exchange="NSE", symbol="NIFTY_TEST_FUT", interval="1m",
        event_time=now, ingest_time=now,
        price_volume={"open":100,"high":101,"low":99,"close":100,"volume":1000},
        regime={"label":"fixture"}, options_flow={"source":"fixture"},
        context={"session":"fixture"}, provenance={"source_id":"fixture:stage13","dataset":"synthetic"},
    )


def evidence(*, only_one=False):
    rows = [
        SpecialistEvidence("TREND_REGIME", "BUY", "Trend supports direction", "fixture:trend", "Trend breaks"),
        SpecialistEvidence("MOMENTUM", "BUY", "Momentum confirms", "fixture:momentum", "Momentum reverses"),
    ]
    return rows[:1] if only_one else rows


def test_eight_role_contract_is_explicit_and_missing_roles_are_not_fabricated():
    assert len(SPECIALIST_ROLES) == 8
    proposals = adapt_specialist_evidence(evidence())
    assert len(proposals) == 2
    assert {p.specialist_id for p in proposals} == {"TREND_REGIME", "MOMENTUM"}


def test_single_directional_role_is_held_for_independent_confirmation():
    proposals = adapt_specialist_evidence(evidence(only_one=True))
    assert proposals[-1].action == "HOLD"
    assert proposals[-1].specialist_id == "INDEPENDENT_CONFIRMATION_REQUIRED"


def test_duplicate_or_unknown_roles_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        adapt_specialist_evidence(evidence() + [evidence()[0]])
    with pytest.raises(ValueError, match="unknown"):
        SpecialistEvidence("MADE_UP", "BUY", "reason", "ref", "invalid")


def test_master_orchestrator_accepts_evidence_adapter_without_inventing_signals():
    orchestrator = MasterTradingOrchestrator()
    result = orchestrator.run_cycle_from_evidence(
        state=state(), specialist_evidence=evidence(),
        risk_request=RiskRequest(50_000, 100, 95, "NIFTY_TEST_FUT", "BUY", 1),
        execution_request=ExecutionRequest("BUY", 1, 100, 10, spread_bps=2, slippage_bps=1),
        expected_edge_bps=20,
    )
    assert result.status is MasterCycleStatus.SHADOW_FILL_SIMULATED
    assert result.order_submitted is False and result.live_trading_enabled is False
    orchestrator.close()


def test_evolve_governance_audits_human_approval_and_keeps_protected_controls_disabled():
    audit = AuditLedger()
    service = GovernedEvolveService(audit=audit)
    service.add_note(ResearchNote("Test", "Test a hypothesis", "fixture:research"))
    experiment = service.propose(name="Indicator study", hypothesis="Compare two indicators", target="research_strategy")
    with pytest.raises(PermissionError):
        service.start(experiment.experiment_id)
    approved = service.approve(experiment.experiment_id, approved_by="human-reviewer")
    assert approved.approval_by == "human-reviewer"
    service.start(experiment.experiment_id)
    service.complete(experiment.experiment_id, result="No promotion; research only")
    snapshot = service.snapshot()
    assert snapshot.notes_count == 1 and snapshot.experiment_count == 1
    assert snapshot.code_execution_enabled is False
    assert snapshot.strategy_promotion_enabled is False
    assert snapshot.live_trading_enabled is False
    assert audit.verify()
    assert len(audit.records()) == 5


def test_directional_specialists_cannot_double_count_same_evidence_source():
    duplicated_source = [
        SpecialistEvidence("TREND_REGIME", "BUY", "Trend supports", "same:source", "Trend breaks"),
        SpecialistEvidence("MOMENTUM", "BUY", "Momentum supports", "same:source", "Momentum reverses"),
    ]
    with pytest.raises(ValueError, match="independent evidence"):
        adapt_specialist_evidence(duplicated_source)
