"""Stage51: static frontend security + offline end-to-end demo checks.

Tests actual local HTML/CSS/JS files and the Stage50-backed synthetic JSON
export. No live URL, HTTP server, exchange provider, broker or real orders.
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
STATIC = ROOT / "src" / "nexus_titan" / "dashboard" / "static"


def test_visual_assets_exist_and_keep_approved_theme_contract():
    html = (STATIC / "stage51.html").read_text(encoding="utf-8")
    css = (STATIC / "stage51.css").read_text(encoding="utf-8")
    js = (STATIC / "stage51.js").read_text(encoding="utf-8")
    assert html.lower().startswith("<!doctype html>")
    assert '<meta name="viewport"' in html
    assert 'href="stage51.css"' in html
    assert 'src="stage51.js"' in html
    assert 'type="file"' in html
    assert 'accept=".json,application/json"' in html
    assert "RESEARCH ONLY" in html
    assert "NO LIVE PRICE" in html
    assert "APPROVED TITAN FACE" in html
    assert "ASSET NOT CONNECTED" in html
    assert "stage51" in js
    for name in ("surface", "panel", "silver", "text", "cyan_activity",
                 "positive_market", "negative_market"):
        assert _LOCKED_THEME[name].lower() in css.lower()
    assert '@media(max-width:560px)' in css
    assert 'font-variant-numeric:tabular-nums' in css


def test_frontend_is_strictly_offline_nonexecuting_and_text_only():
    html = (STATIC / "stage51.html").read_text(encoding="utf-8")
    js = (STATIC / "stage51.js").read_text(encoding="utf-8")
    css = (STATIC / "stage51.css").read_text(encoding="utf-8")
    assert 'connect-src \'none\'' in html
    assert 'default-src \'none\'' in html
    assert "script-src 'self'" in html
    assert "style-src 'self'" in html
    assert "form-action 'none'" in html
    assert 'name="referrer" content="no-referrer"' in html
    assert "unsafe-inline" not in html
    assert "unsafe-eval" not in html
    assert "https://" not in html + js + css
    assert "http://" not in html + js + css
    assert "<iframe" not in html.lower()
    assert "<form" not in html.lower()
    for forbidden in (
        "innerHTML", "outerHTML", "insertAdjacentHTML",
        "fetch(", "XMLHttpRequest", "WebSocket(", "EventSource(",
        "sendBeacon(", "window.open(", "eval(", "new Function(",
        "localStorage.", "sessionStorage.", "document.cookie",
        "approve_order(", "execute_fill(", "submit_order(",
    ):
        assert forbidden not in js, forbidden
    assert 'li.textContent = message.slice(0, 200)' in js
    assert "file.size <= 256 * 1024" in js
    assert "Object.hasOwn" in js
    assert 'path(d, "market", "latest_price") === null' in js
    assert 'path(d, "account", "combined_cash_cents") === null' in js
    assert '"production_ready"' in js
    assert '"live_trading_enabled"' in js


def _run_demo(output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_stage51_visual_dashboard_demo.py"),
         "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, check=False,
        timeout=30,
    )


def test_real_stage50_snapshot_export_is_synthetic_and_never_overwrites(tmp_path):
    output = tmp_path / "safety_snapshot.json"
    completed = _run_demo(output)
    assert completed.returncode == 0, completed.stderr
    assert "NOT a real account" in completed.stdout
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["component"] == "TITAN_PAPER_SAFETY"
    assert data["data_source"] == "LOCAL_SYNTHETIC_PAPER_SQLITE_ONLY"
    assert data["account"]["account_id"] == "STAGE51-DEMO-NOT-REAL"
    assert data["account"]["initial_paper_capital_cents"] == 5000000
    assert data["account"]["combined_cash_cents"] is None
    assert data["status"] == "LOCAL_REVIEW_REQUIRED"  # no paper-session opt-in
    assert data["paper_orders"]["total"] == 0
    assert not data["paper_session"]["paper_orders_enabled_in_config"]
    assert not data["admission_fence"]["first_synthetic_buy_preflight_passed"]
    assert data["market"]["latest_price"] is None
    assert not data["market"]["provider_identity_verified"]
    assert not data["safety"]["production_ready"]
    assert not data["safety"]["broker_connected"]
    assert not data["safety"]["live_trading_enabled"]
    assert any("DEMO FILE ONLY" in s for s in data["notes"])
    text = output.read_text(encoding="utf-8")
    assert "signature_hex" not in text
    assert '"secret_key"' not in text
    assert '"token_id"' not in text
    assert len(output.read_bytes()) <= 256 * 1024
    if os.name == "posix":
        assert output.stat().st_mode & 0o077 == 0

    original = output.read_bytes()
    repeat = _run_demo(output)
    assert repeat.returncode == 2
    assert "no overwrites" in repeat.stderr
    assert output.read_bytes() == original


def test_export_rejects_non_json_output_and_preserves_existing(tmp_path):
    result = _run_demo(tmp_path / "unsafe.html")
    assert result.returncode == 2
    assert not (tmp_path / "unsafe.html").exists()
    existing = tmp_path / "original.json"
    existing.write_text("SAFE_USER_ORIGINAL", encoding="utf-8")
    bad = _run_demo(existing)
    assert bad.returncode == 2
    assert existing.read_text(encoding="utf-8") == "SAFE_USER_ORIGINAL"


def test_export_rejects_symlink_target_without_touching_source(tmp_path):
    original = tmp_path / "owned.json"
    original.write_text("UNMODIFIED", encoding="utf-8")
    symlink = tmp_path / "shortcut.json"
    try:
        symlink.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks not available in this runtime")
    result = _run_demo(symlink)
    assert result.returncode == 2
    assert original.read_text(encoding="utf-8") == "UNMODIFIED"


def test_node_browser_like_rendering_and_spoofing_rejection_if_available():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node runtime not installed; static+Python regressions still run")
    run = subprocess.run(
        [node, str(ROOT / "tests" / "helpers" / "stage51_browser_harness.cjs")],
        cwd=ROOT, capture_output=True, text=True, check=False, timeout=20,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "STAGE51_NODE_BROWSER_SECURITY_CHECKS_PASSED" in run.stdout
