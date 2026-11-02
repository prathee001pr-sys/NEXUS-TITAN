"""Stage22 end-to-end offline integration tests, exercising real Stage7–21 APIs.

Fixtures are synthetic, not exchange or broker observations.
"""
from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

from nexus_titan.data.option_chain_ingest import OptionChainIngestionError
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_stage22_research_smoke.py"
run_offline_smoke = runpy.run_path(str(SCRIPT))["run_offline_smoke"]
ACCOUNT = "STAGE22-SYNTHETIC-RESEARCH"


def test_full_csv_to_readiness_integration_with_restore_and_restart(tmp_path):
    report = run_offline_smoke(tmp_path)
    assert report["dataset"] == "SYNTHETIC_ONLY_NOT_NSE_DATA"
    assert report["snapshot_count"] == 1
    assert report["quote_count"] == 2
    assert report["requested_quantity"] == 50
    assert report["filled_quantity"] == 50
    assert report["simulated_fill_status"] == "FILLED"
    assert report["simulated_fee_reserve"] > 0
    assert report["virtual_capital"] == 50000.0
    assert 0 < report["projected_cash"] < 50000
    assert report["reserved_cash_after_settlement"] == 0.0
    assert report["restart_state_match"]
    assert report["duplicate_order_rejected_after_restart"]
    assert report["sqlite_backup_verified_locally"]
    assert report["day_close_structure_valid"]
    assert report["readiness_decision"] == "BLOCKED_STRUCTURAL_VALIDATION"
    assert report["external_evidence_verified"] is False
    assert report["live_trading_enabled"] is False
    assert report["automatic_strategy_promotion"] is False


def test_single_command_cli_runs_without_venv_or_live_apis():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT, text=True, capture_output=True, timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["dataset"] == "SYNTHETIC_ONLY_NOT_NSE_DATA"
    assert result["restart_state_match"]
    assert result["readiness_decision"] == "BLOCKED_STRUCTURAL_VALIDATION"
    assert result["live_trading_enabled"] is False


def test_adjustable_virtual_capital_and_restart_exact_amount(tmp_path):
    out = run_offline_smoke(tmp_path, starting_capital=23000.0)
    assert out["virtual_capital"] == 23000.0
    assert 0 < out["projected_cash"] < 23000
    restarted = DurableResearchShadowLedger(
        tmp_path / "synthetic_research_ledger.sqlite3",
        account_id=ACCOUNT, starting_capital=23000.0,
    )
    assert restarted.verify_integrity()
    assert restarted.status().cash_balance == out["projected_cash"]


def test_no_depth_does_not_invent_csv_volume_as_fill(tmp_path):
    result = run_offline_smoke(tmp_path, displayed_ask_quantity=0)
    assert result["simulated_fill_status"] == "UNFILLED"
    assert result["filled_quantity"] == 0
    assert result["projected_cash"] == result["virtual_capital"]
    assert result["simulated_fee_reserve"] == 0.0
    assert result["readiness_decision"] == "BLOCKED_STRUCTURAL_VALIDATION"


def test_limited_displayed_depth_produces_lot_rounded_partial_fill(tmp_path):
    out = run_offline_smoke(tmp_path, displayed_ask_quantity=100)
    assert out["simulated_fill_status"] == "PARTIAL"
    assert out["filled_quantity"] == 25
    assert out["requested_quantity"] == 50
    assert out["restart_state_match"]
    assert out["reserved_cash_after_settlement"] == 0


def test_bad_source_checksum_fails_before_research_account_creation(tmp_path):
    with pytest.raises(OptionChainIngestionError, match="checksum mismatch"):
        run_offline_smoke(tmp_path, expected_sha256_override="0" * 64)
    assert (tmp_path / "synthetic_options_snapshot.csv").exists()
    assert not (tmp_path / "synthetic_research_ledger.sqlite3").exists()
    assert not (tmp_path / "synthetic_recovery.sqlite3").exists()


def test_insufficient_virtual_cash_fails_without_settlement_or_balance_loss(tmp_path):
    with pytest.raises(ResearchLedgerError, match="Insufficient unreserved"):
        run_offline_smoke(tmp_path, starting_capital=100.0)
    ledger = DurableResearchShadowLedger(
        tmp_path / "synthetic_research_ledger.sqlite3",
        account_id=ACCOUNT, starting_capital=100.0,
    )
    status = ledger.status()
    assert status.cash_balance == 100.0
    assert status.reserved_cash == 0
    assert status.open_order_count == 0
    assert status.option_inventory == ()
    assert not (tmp_path / "synthetic_recovery.sqlite3").exists()


@pytest.mark.parametrize("bad_depth", [-1, True, 1.5])
def test_invalid_displayed_depth_fails_without_ledger_mutation(tmp_path, bad_depth):
    with pytest.raises(ValueError, match="ask_quantity"):
        run_offline_smoke(tmp_path, displayed_ask_quantity=bad_depth)
    assert not (tmp_path / "synthetic_research_ledger.sqlite3").exists()


def test_never_reuses_workspace_files_or_writes_into_existing_db(tmp_path):
    first = run_offline_smoke(tmp_path)
    source_bytes = (tmp_path / "synthetic_research_ledger.sqlite3").read_bytes()
    with pytest.raises(ValueError, match="fresh workspace"):
        run_offline_smoke(tmp_path)
    assert (tmp_path / "synthetic_research_ledger.sqlite3").read_bytes() == source_bytes
    assert first["live_trading_enabled"] is False


def test_isolated_runs_are_deterministic_and_not_share_capital(tmp_path):
    left = run_offline_smoke(tmp_path / "a")
    right = run_offline_smoke(tmp_path / "b")
    assert left == right
    assert (tmp_path / "a" / "synthetic_recovery.sqlite3").exists()
    assert (tmp_path / "b" / "synthetic_recovery.sqlite3").exists()
    assert left["live_trading_enabled"] is False


def test_dummy_provenance_is_never_presented_as_verified_exchange_data(tmp_path):
    out = run_offline_smoke(tmp_path)
    assert out["external_evidence_verified"] is False
    assert out["readiness_decision"] != "APPROVED"
    assert "SYNTHETIC" in out["dataset"]
    assert out["automatic_strategy_promotion"] is False
