"""Audited wrapper for human-governed TITAN EVOLVE research experiments."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus_titan.core.audit import AuditLedger
from nexus_titan.evolve.research import EvolveResearch, Experiment, ResearchNote


@dataclass(frozen=True, slots=True)
class GovernanceSnapshot:
    notes_count: int
    experiment_count: int
    protected_targets: tuple[str, ...]
    code_execution_enabled: bool = False
    strategy_promotion_enabled: bool = False
    live_trading_enabled: bool = False


class GovernedEvolveService:
    """Adds audit traceability; deliberately does not execute code or promote strategies."""

    def __init__(self, research: EvolveResearch | None = None, audit: AuditLedger | None = None) -> None:
        self.research = research or EvolveResearch()
        self.audit = audit or AuditLedger()

    def add_note(self, note: ResearchNote) -> None:
        self.research.add_note(note)
        self.audit.append(actor="titan_evolve", action="research_note_added", outcome="recorded",
                          details={"note_id": note.note_id, "source": note.source})

    def propose(self, *, name: str, hypothesis: str, target: str) -> Experiment:
        experiment = self.research.propose(name=name, hypothesis=hypothesis, target=target)
        self.audit.append(actor="titan_evolve", action="experiment_proposed", outcome="pending_human_approval",
                          details={"experiment_id": experiment.experiment_id, "target": target})
        return experiment

    def approve(self, experiment_id: str, *, approved_by: str) -> Experiment:
        experiment = self.research.approve(experiment_id, approved_by=approved_by)
        self.audit.append(actor=approved_by, action="evolve_experiment_approved", outcome="approved",
                          details={"experiment_id": experiment_id, "target": experiment.target})
        return experiment

    def start(self, experiment_id: str) -> Experiment:
        experiment = self.research.start(experiment_id)
        self.audit.append(actor="titan_evolve", action="evolve_experiment_started", outcome="running",
                          details={"experiment_id": experiment_id, "target": experiment.target})
        return experiment

    def complete(self, experiment_id: str, *, result: str) -> Experiment:
        experiment = self.research.complete(experiment_id, result=result)
        self.audit.append(actor="titan_evolve", action="evolve_experiment_completed", outcome="recorded",
                          details={"experiment_id": experiment_id, "target": experiment.target})
        return experiment

    def snapshot(self) -> GovernanceSnapshot:
        return GovernanceSnapshot(
            notes_count=len(self.research.notes()),
            experiment_count=self.research.experiment_count,
            protected_targets=("risk_controls", "permissions", "live_trading"),
        )
