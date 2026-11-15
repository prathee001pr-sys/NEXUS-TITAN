"""Stage70 offline source-inventory tests: static evidence only."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest

from nexus_titan.operations.stage70_fo_integration_gate import (
    Stage70AuditBlocked, inspect_stage70_fo_integration,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "src/nexus_titan/virtual/order_manager.py",
    "src/nexus_titan/crypto/crypto_engine.py",
    "src/nexus_titan/shadow/guarded_options_research.py",
    "src/nexus_titan/operations/stage69_risk_budget_preflight.py",
    "src/nexus_titan/operations/brokerless_risk_veto.py",
)


def fixture_tree(tmp_path):
    for relative in SOURCES:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def mutate(root, relative, old, new):
    path = root / relative
    content = path.read_text(encoding="utf-8")
    assert old in content
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def test_current_tree_inventory_is_still_no_go():
    result = inspect_stage70_fo_integration(ROOT)
    assert result.sources_parsed == 5
    assert len(result.observed_execution_entrypoints) == 5
    assert "VirtualAccount.execute_fill" in result.observed_execution_entrypoints
    assert result.stage69_denied_authority_defaults_checked == 12
    assert len(result.source_digest_sha256) == 64
    assert result.static_inventory_complete
    for field in (
        "current_github_pr_graph_verified", "actual_main_merge_reviewed",
        "branch_protection_verified", "global_risk_veto_unbypassable",
        "atomic_capital_authority_verified", "licensed_fo_data_verified",
        "live_feed_shadow_pnl_verified", "human_release_approval_verified",
        "safe_to_merge", "production_ready", "live_trading_enabled",
    ):
        assert getattr(result, field) is False
    assert result.broker_orders_transmitted == 0
    assert len(result.external_release_blockers) >= 8
    assert "NO_GO" in result.verdict
    assert asdict(result)["static_inventory_complete"] is True


def test_repeated_inspection_does_not_change_sources_or_create_orders(tmp_path):
    root = fixture_tree(tmp_path)
    assert inspect_stage70_fo_integration(root) == inspect_stage70_fo_integration(root)
    assert sorted(p for p in root.rglob("*") if p.is_file()) == sorted(
        root / item for item in SOURCES
    )


@pytest.mark.parametrize("relative,old,new", [
    ("src/nexus_titan/virtual/order_manager.py", "def execute_fill(",
     "def execute_fill_alt("),
    ("src/nexus_titan/crypto/crypto_engine.py", "def execute_crypto_order(",
     "def execute_crypto_order_alt("),
    ("src/nexus_titan/shadow/guarded_options_research.py",
     "def guarded_options_research_buy(", "def guarded_options_research_buy_alt("),
    ("src/nexus_titan/operations/stage69_risk_budget_preflight.py",
     "global_legacy_entrypoints_fenced: bool = False",
     "global_legacy_entrypoints_fenced: bool = True"),
    ("src/nexus_titan/operations/stage69_risk_budget_preflight.py",
     "broker_orders_transmitted: int = 0", "broker_orders_transmitted: int = 1"),
    ("src/nexus_titan/operations/brokerless_risk_veto.py",
     'instrument_type: str = "EQUITY_DELIVERY"',
     'instrument_type: str = "OPTIONS"'),
])
def test_drift_or_unsafe_flags_fail_closed(tmp_path, relative, old, new):
    root = fixture_tree(tmp_path)
    mutate(root, relative, old, new)
    with pytest.raises(Stage70AuditBlocked):
        inspect_stage70_fo_integration(root)


def test_comment_spoof_cannot_restore_missing_method(tmp_path):
    root = fixture_tree(tmp_path)
    relative = "src/nexus_titan/virtual/order_manager.py"
    mutate(root, relative, "def execute_fill(", "def renamed_fill(")
    with (root / relative).open("a", encoding="utf-8") as handle:
        handle.write("\n# def execute_fill(\n")
    with pytest.raises(Stage70AuditBlocked):
        inspect_stage70_fo_integration(root)


def test_missing_and_symlinked_sources_fail_closed(tmp_path):
    root = fixture_tree(tmp_path)
    path = root / SOURCES[0]
    path.unlink()
    with pytest.raises(Stage70AuditBlocked):
        inspect_stage70_fo_integration(root)
    path.symlink_to(ROOT / SOURCES[0])
    with pytest.raises(Stage70AuditBlocked):
        inspect_stage70_fo_integration(root)


def test_unparseable_source_fails_closed(tmp_path):
    root = fixture_tree(tmp_path)
    (root / SOURCES[2]).write_text("def broken(:\n", encoding="utf-8")
    with pytest.raises(Stage70AuditBlocked):
        inspect_stage70_fo_integration(root)


def test_cli_reports_readonly_blocked_release():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage70_fo_integration_audit.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"].endswith("NO_GO")
    assert payload["broker_orders_transmitted"] == 0
    assert payload["safe_to_merge"] is False
    assert payload["live_trading_enabled"] is False
