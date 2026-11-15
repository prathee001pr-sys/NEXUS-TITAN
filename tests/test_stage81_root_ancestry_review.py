"""Stage81 two-root GitHub comparison and source hand-off adversarial tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from nexus_titan.operations import stage81_root_ancestry_review as mod
from nexus_titan.operations.stage81_root_ancestry_review import (
    Stage81AncestryBlocked, inspect_stage81_candidate,
)
from nexus_titan.intelligence.calibration import ProbabilityCalibrator, CalibrationObservation
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/STAGE81_TWO_ROOT_ANCESTRY_EVIDENCE_2026-11-04.json"


def evidence():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_actual_root_ancestry_and_stage73_import_review_no_go():
    report = inspect_stage81_candidate(ROOT, evidence())
    assert report.root_prs_present_in_development_history == (1, 3)
    assert report.source_file_count_inspected == 4
    assert report.calibration_runtime_import_contract_found
    assert report.independent_root_ancestry_locally_consistent
    assert report.verdict.endswith("NO_GO")
    assert len(report.source_contract_sha256) == 64
    assert len(report.blockers) >= 5
    assert report == inspect_stage81_candidate(ROOT, evidence())
    assert not report.actual_three_way_merge_review_completed
    assert not report.global_risk_veto_verified
    assert not report.unified_capital_authority_verified
    assert not report.merge_authorized
    assert not report.live_trading_enabled
    assert report.broker_orders_transmitted == 0


def test_calibration_contract_import_is_actually_executable():
    when = datetime(2026, 11, 4, tzinfo=timezone.utc)
    rows = [CalibrationObservation(
        prediction_id=f"synthetic-{n}", probability=float(n % 2),
        outcome=bool(n % 2), predicted_at=when,
        resolved_at=when + timedelta(minutes=1),
    ) for n in range(4)]
    report = ProbabilityCalibrator(min_samples=100).evaluate(rows)
    assert report.sample_count == 4
    assert report.brier_score == 0
    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert not report.sufficient_evidence


@pytest.mark.parametrize("change", [
    ("main_protected", True),
    ("candidate_sha", "0"*40),
    ("repository", "another-owner/not-titan"),
    ("root_ancestry", []),
])
def test_missing_or_forged_root_evidence_blocks(change):
    data = evidence()
    key, value = change
    data[key] = value
    with pytest.raises(Stage81AncestryBlocked):
        inspect_stage81_candidate(ROOT, data)


@pytest.mark.parametrize("attr,value", [
    ("status", "diverged"),
    ("merge_base_sha", "0"*40),
    ("behind_by", 1),
    ("ahead_by", 0),
    ("head_sha", "0"*40),
    ("base_ref", "main"),
])
def test_modified_root_compare_record_blocks(attr, value):
    data = evidence()
    data["root_ancestry"][0][attr] = value
    with pytest.raises(Stage81AncestryBlocked):
        inspect_stage81_candidate(ROOT, data)


def test_duplicate_root_record_is_not_two_roots():
    data = evidence()
    data["root_ancestry"][1] = copy.deepcopy(data["root_ancestry"][0])
    with pytest.raises(Stage81AncestryBlocked, match="identity"):
        inspect_stage81_candidate(ROOT, data)


def test_missing_calibration_runtime_handoff_blocks(monkeypatch):
    real = mod._read
    def fake(root, rel):
        blob = real(root, rel)
        if rel.endswith("evolve/stage73_fo_experience.py"):
            blob = blob.replace(
                b"nexus_titan.intelligence.calibration",
                b"nexus_titan.intelligence.no_calibration",
            )
        return blob
    monkeypatch.setattr(mod, "_read", fake)
    with pytest.raises(Stage81AncestryBlocked, match="Calibration"):
        inspect_stage81_candidate(ROOT, evidence())


def test_missing_source_file_denied(tmp_path):
    with pytest.raises(Stage81AncestryBlocked, match="source"):
        inspect_stage81_candidate(tmp_path, evidence())
