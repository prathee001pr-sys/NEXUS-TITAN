import pytest

from nexus_titan.core.requirements import RequirementsRegister, RequirementStatus


def make_register(path):
    register = RequirementsRegister(str(path))
    register.register(
        requirement_id="CORE-001",
        title="Core configuration",
        scope="Runtime settings and safe defaults",
        acceptance_criteria=["Settings validate", "Paper trading defaults off"],
    )
    return register


def test_requirement_progresses_in_order_with_evidence(tmp_path):
    register = make_register(tmp_path / "requirements.sqlite3")
    item = register.get("CORE-001")
    assert item.status is RequirementStatus.DESIGNED
    item = register.advance("CORE-001", RequirementStatus.BUILT)
    assert item.status is RequirementStatus.BUILT
    with pytest.raises(ValueError):
        register.advance("CORE-001", RequirementStatus.VERIFIED, evidence="skip test")
    with pytest.raises(ValueError):
        register.advance("CORE-001", RequirementStatus.TESTED)
    item = register.advance("CORE-001", RequirementStatus.TESTED, evidence="CI run #6")
    assert item.evidence == ("CI run #6",)
    item = register.advance("CORE-001", RequirementStatus.VERIFIED, evidence="review #1")
    assert item.status is RequirementStatus.VERIFIED
    register.close()


def test_register_persists_after_reopen(tmp_path):
    path = tmp_path / "requirements.sqlite3"
    register = make_register(path)
    register.close()
    reopened = RequirementsRegister(str(path))
    assert reopened.get("CORE-001").title == "Core configuration"
    assert len(reopened.list()) == 1
    reopened.close()


def test_duplicate_requirement_and_empty_criteria_are_rejected(tmp_path):
    register = make_register(tmp_path / "requirements.sqlite3")
    with pytest.raises(ValueError):
        register.register(requirement_id="CORE-001", title="Duplicate",
                          scope="scope", acceptance_criteria=["criterion"])
    with pytest.raises(ValueError):
        register.register(requirement_id="CORE-002", title="Empty criteria",
                          scope="scope", acceptance_criteria=[])
    register.close()


def test_unknown_requirement_is_rejected(tmp_path):
    register = RequirementsRegister(str(tmp_path / "requirements.sqlite3"))
    with pytest.raises(KeyError):
        register.get("UNKNOWN")
    register.close()
