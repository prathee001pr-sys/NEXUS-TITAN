"""Stage123 isolated fault-injection and recovery acceptance tests."""
from dataclasses import FrozenInstanceError
import pytest
from nexus_titan.operations.stage123_recovery_fault_lab import run_guardian_fault_lab, FaultCase


def test_full_real_process_fault_matrix(tmp_path):
    result = run_guardian_fault_lab(explicit_opt_in=True,parent=tmp_path,timeout_seconds=2.0)
    assert result.all_passed
    assert len(result.cases)==6
    assert all(case.passed for case in result.cases)
    assert {case.name for case in result.cases} == {
        'bounded_normal_worker','hard_process_exit_resume','watchdog_timeout_resume',
        'bounded_quarantine','verified_staged_backup','corrupt_database_fails_closed'}
    assert result.broker_orders_sent==0 and not result.live_trading_enabled
    assert list(tmp_path.iterdir())==[]  # all synthetic fault files cleaned

@pytest.mark.parametrize('bad', [False,None,0,1,{},'yes'])
def test_explicit_opt_in_gate(tmp_path,bad):
    with pytest.raises(PermissionError):run_guardian_fault_lab(explicit_opt_in=bad,parent=tmp_path)


def test_missing_parent_preflight(tmp_path):
    with pytest.raises(ValueError):
        run_guardian_fault_lab(explicit_opt_in=True,parent=tmp_path/'missing')


def test_symlink_parent_rejected(tmp_path):
    linked=tmp_path/'link';linked.symlink_to(tmp_path)
    with pytest.raises(ValueError):run_guardian_fault_lab(explicit_opt_in=True,parent=linked)


def test_fault_case_immutable():
    with pytest.raises(FrozenInstanceError):FaultCase('name',True,'OK').passed=False


def test_invalid_timeout_fails_without_source_change(tmp_path):
    with pytest.raises(ValueError):
        run_guardian_fault_lab(explicit_opt_in=True,parent=tmp_path,timeout_seconds=0)
    assert list(tmp_path.iterdir())==[]
