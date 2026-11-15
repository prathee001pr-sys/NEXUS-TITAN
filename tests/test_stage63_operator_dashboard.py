"""Stage63 offline operator dashboard security, source and browser QA.

The stage63 static view is independent from the locked Stage51 paper screen,
loads only user-selected Stage62 CLI and Stage61 synthetic smoke JSON, and
never has a network, order, approval or real data source.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.dashboard.paper_read_model import _LOCKED_THEME


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/nexus_titan/dashboard/static"


def test_stage63_preserves_locked_stage51_layout_and_premium_theme():
    html = (STATIC / "stage63.html").read_text(encoding="utf-8")
    css = (STATIC / "stage63.css").read_text(encoding="utf-8")
    common = (STATIC / "stage51.css").read_text(encoding="utf-8")
    script = (STATIC / "stage63.js").read_text(encoding="utf-8")
    assert html.lower().startswith("<!doctype html>")
    assert 'href="stage51.css"' in html
    assert 'href="stage63.css"' in html
    assert 'src="stage63.js"' in html
    assert "STAGE 63" in html
    assert "RELEASE NO-GO" in html
    assert "OFFLINE" in html
    assert "READ ONLY" in html
    assert "APPROVED TITAN FACE" in html
    assert "ASSET NOT CONNECTED" in html
    assert "Original approved cybernetic face asset" in html
    assert 'id="auditFile"' in html
    assert 'id="researchFile"' in html
    assert 'id="clearAll"' in html
    assert "No automatic source refresh" in html
    assert "No broker" not in html  # No misleading active broker widget
    assert "stage63.js" in html
    assert "Stage63" in script
    assert "@media(max-width:560px)" in css
    for token in ("surface", "panel", "silver", "text", "cyan_activity",
                  "positive_market", "negative_market"):
        assert _LOCKED_THEME[token].lower() in common.lower()


def test_stage63_static_bundle_is_strictly_networkless_and_text_only():
    html = (STATIC / "stage63.html").read_text(encoding="utf-8")
    css = (STATIC / "stage63.css").read_text(encoding="utf-8")
    script = (STATIC / "stage63.js").read_text(encoding="utf-8")
    assert "default-src 'none'" in html
    assert "connect-src 'none'" in html
    assert "script-src 'self'" in html
    assert "style-src 'self'" in html
    assert "form-action 'none'" in html
    assert "base-uri 'none'" in html
    assert 'name="referrer" content="no-referrer"' in html
    assert "unsafe-inline" not in html
    assert "unsafe-eval" not in html
    for string in ("https://", "http://", "<iframe", "<form", "onerror=",
                   "onload=", "<img"):
        assert string not in (html + css).lower()
    for unsafe in (
        "innerHTML", "outerHTML", "insertAdjacentHTML", "XMLHttpRequest",
        "WebSocket(", "EventSource(", "sendBeacon(", "window.open(",
        "fetch(", "eval(", "new Function(", "localStorage.",
        "sessionStorage.", "document.cookie",
        "approve_order(", "execute_fill(", "submit_order(",
        "cancel_order(", "emergency_square_off(",
    ):
        assert unsafe not in script, unsafe
    assert "document.createElement(\"li\")" in script
    assert ".textContent =" in script
    assert "Object.hasOwn" in script
    assert "const MAX_FILE_BYTES = 256 * 1024" in script
    assert "selectionGeneration" not in script  # Independent file generations
    assert "auditGeneration" in script and "researchGeneration" in script
    assert "const STAGE62_FALSE" in script
    assert "const STAGE61_FALSE" in script


def test_actual_stage62_cli_and_stage61_smoke_exports_are_supported_locally():
    for name, expected_mode in (
        ("run_stage62_integration_audit.py",
         "STAGE62_FROZEN_SNAPSHOT_NO_MERGE_LOCAL_AST_ONLY"),
        ("run_stage61_fo_evidence_smoke.py",
         "STAGE61_SYNTHETIC_EVIDENCE_NO_GO_SCORECARD_ONLY"),
    ):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name)],
            capture_output=True, text=True, cwd=ROOT, timeout=50, check=False,
        )
        assert proc.returncode == 0, proc.stderr
        result = json.loads(proc.stdout)
        assert result["mode"] == expected_mode
        assert result["production_ready"] is False
        if name.startswith("run_stage62"):
            assert result["frozen_pr_count"] == 52
            assert result["frozen_root_prs"] == [1, 3]
            assert result["frozen_changed_paths_complete"] is False
            assert result["merge_authorized"] is False
        else:
            assert result["real_vendor_data_present"] is False
            assert result["actual_fo_pnl_verified"] is False
            assert result["nifty"]["candles"] == 46
            assert result["banknifty"]["candles"] == 46
            assert result["broker_orders_transmitted"] == 0


def test_node_browser_validation_xss_spoofed_authority_and_stale_read():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node missing: static and Python JSON tests still run")
    proc = subprocess.run(
        [node, str(ROOT / "tests/helpers/stage63_browser_harness.cjs")],
        capture_output=True, text=True, cwd=ROOT, timeout=95, check=False,
        env={**os.environ, "PYTHON": sys.executable},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "STAGE63_NODE_OFFLINE_OPERATOR_SECURITY_CHECKS_PASSED" in proc.stdout
