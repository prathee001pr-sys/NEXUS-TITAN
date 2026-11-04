"""Dependency and actual import compatibility of the selected integrated tree."""
from pathlib import Path
import importlib

from nexus_titan.operations.integration_candidate_audit import inspect_package_dependencies
from nexus_titan.operations.stage67_calibration_reconcile import inspect_stage67_calibration_reconciliation

ROOT = Path(__file__).resolve().parents[1]


def test_entire_selected_package_imports_and_retains_calibration_resolution():
    review = inspect_package_dependencies(ROOT)
    assert review.passed, review
    assert len(review.modules) > 100
    for name in review.modules:
        assert importlib.import_module(name).__name__ == name
    assert inspect_stage67_calibration_reconciliation(ROOT).frozen_source_lineage_check_passed


def test_missing_internal_dependency_is_reported(tmp_path):
    package = tmp_path / "src/nexus_titan"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "broken.py").write_text("from nexus_titan.missing import RiskGate\n")
    review = inspect_package_dependencies(tmp_path)
    assert not review.passed
    assert review.unresolved_internal_imports == (("nexus_titan.broken", "nexus_titan.missing"),)


def test_duplicate_definitions_and_identical_modules_are_visible(tmp_path):
    package = tmp_path / "src/nexus_titan"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    for name in ("first", "second"):
        (package / (name + ".py")).write_text("def reserve(): pass\ndef reserve(): pass\n")
    review = inspect_package_dependencies(tmp_path)
    assert not review.passed
    assert len(review.duplicate_definitions) == 2
    assert review.identical_module_groups == (("nexus_titan.first", "nexus_titan.second"),)
