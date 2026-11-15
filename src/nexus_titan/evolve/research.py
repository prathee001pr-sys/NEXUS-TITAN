"""Governed research and experiment lifecycle; never changes protected controls."""
from dataclasses import dataclass, field
from enum import StrEnum
from datetime import datetime, timezone
from uuid import uuid4


PROTECTED_TARGETS = frozenset({
    "risk_controls",
    "permissions",
    "live_trading",
})


class ExperimentStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ResearchNote:
    title: str
    hypothesis: str
    source: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    note_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.hypothesis.strip() or not self.source.strip():
            raise ValueError("title, hypothesis, and source must not be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Experiment:
    name: str
    hypothesis: str
    target: str
    status: ExperimentStatus = ExperimentStatus.PROPOSED
    experiment_id: str = field(default_factory=lambda: str(uuid4()))
    approval_by: str | None = None
    result: str | None = None


class EvolveResearch:
    """Stores research and requires human approval before experiment execution.

    This foundation does not execute code, deploy strategies, or modify trading
    risk limits, permissions, or live-trading settings.
    """

    def __init__(self) -> None:
        self._notes: list[ResearchNote] = []
        self._experiments: dict[str, Experiment] = {}

    def add_note(self, note: ResearchNote) -> None:
        if any(existing.note_id == note.note_id for existing in self._notes):
            raise ValueError("duplicate research note id")
        self._notes.append(note)

    def notes(self) -> tuple[ResearchNote, ...]:
        return tuple(self._notes)

    @property
    def experiment_count(self) -> int:
        return len(self._experiments)

    def propose(self, *, name: str, hypothesis: str, target: str) -> Experiment:
        if not name.strip() or not hypothesis.strip() or not target.strip():
            raise ValueError("name, hypothesis, and target must not be empty")
        if target in PROTECTED_TARGETS:
            raise ValueError(f"protected target cannot be modified by TITAN EVOLVE: {target}")
        experiment = Experiment(name=name, hypothesis=hypothesis, target=target)
        self._experiments[experiment.experiment_id] = experiment
        return experiment

    def get(self, experiment_id: str) -> Experiment:
        try:
            return self._experiments[experiment_id]
        except KeyError as exc:
            raise KeyError(f"unknown experiment: {experiment_id}") from exc

    def approve(self, experiment_id: str, *, approved_by: str) -> Experiment:
        if not approved_by.strip():
            raise ValueError("human approver identity is required")
        experiment = self.get(experiment_id)
        if experiment.status is not ExperimentStatus.PROPOSED:
            raise ValueError("only proposed experiments can be approved")
        updated = Experiment(
            name=experiment.name, hypothesis=experiment.hypothesis,
            target=experiment.target, status=ExperimentStatus.APPROVED,
            experiment_id=experiment.experiment_id, approval_by=approved_by,
        )
        self._experiments[experiment_id] = updated
        return updated

    def start(self, experiment_id: str) -> Experiment:
        experiment = self.get(experiment_id)
        if experiment.status is not ExperimentStatus.APPROVED:
            raise PermissionError("human approval is required before starting an experiment")
        updated = Experiment(
            name=experiment.name, hypothesis=experiment.hypothesis,
            target=experiment.target, status=ExperimentStatus.RUNNING,
            experiment_id=experiment.experiment_id, approval_by=experiment.approval_by,
        )
        self._experiments[experiment_id] = updated
        return updated

    def complete(self, experiment_id: str, *, result: str) -> Experiment:
        if not result.strip():
            raise ValueError("experiment result must not be empty")
        experiment = self.get(experiment_id)
        if experiment.status is not ExperimentStatus.RUNNING:
            raise ValueError("only running experiments can be completed")
        updated = Experiment(
            name=experiment.name, hypothesis=experiment.hypothesis,
            target=experiment.target, status=ExperimentStatus.COMPLETED,
            experiment_id=experiment.experiment_id, approval_by=experiment.approval_by,
            result=result,
        )
        self._experiments[experiment_id] = updated
        return updated
