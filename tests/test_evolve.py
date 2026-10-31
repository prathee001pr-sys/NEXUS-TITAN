import pytest

from nexus_titan.evolve.research import (
    EvolveResearch, ExperimentStatus, PROTECTED_TARGETS, ResearchNote
)


def test_research_note_is_stored():
    evolve = EvolveResearch()
    note = ResearchNote("Volatility study", "Volatility clusters", "backtest")
    evolve.add_note(note)
    assert evolve.notes() == (note,)


def test_experiment_requires_human_approval_before_start():
    evolve = EvolveResearch()
    experiment = evolve.propose(name="Volatility study", hypothesis="Test regime filter",
                                target="research_sandbox")
    with pytest.raises(PermissionError):
        evolve.start(experiment.experiment_id)
    approved = evolve.approve(experiment.experiment_id, approved_by="human-reviewer")
    assert approved.status is ExperimentStatus.APPROVED
    running = evolve.start(experiment.experiment_id)
    assert running.status is ExperimentStatus.RUNNING
    completed = evolve.complete(experiment.experiment_id, result="No promotion; more data needed")
    assert completed.status is ExperimentStatus.COMPLETED


@pytest.mark.parametrize("target", sorted(PROTECTED_TARGETS))
def test_evolve_cannot_target_protected_controls(target):
    evolve = EvolveResearch()
    with pytest.raises(ValueError, match="protected target"):
        evolve.propose(name="Unsafe", hypothesis="Change protected setting", target=target)


def test_only_proposed_experiments_can_be_approved():
    evolve = EvolveResearch()
    experiment = evolve.propose(name="Study", hypothesis="Test", target="research_sandbox")
    evolve.approve(experiment.experiment_id, approved_by="reviewer")
    with pytest.raises(ValueError):
        evolve.approve(experiment.experiment_id, approved_by="reviewer")


def test_approver_and_result_are_required():
    evolve = EvolveResearch()
    experiment = evolve.propose(name="Study", hypothesis="Test", target="research_sandbox")
    with pytest.raises(ValueError):
        evolve.approve(experiment.experiment_id, approved_by=" ")
    evolve.approve(experiment.experiment_id, approved_by="reviewer")
    evolve.start(experiment.experiment_id)
    with pytest.raises(ValueError):
        evolve.complete(experiment.experiment_id, result=" ")
