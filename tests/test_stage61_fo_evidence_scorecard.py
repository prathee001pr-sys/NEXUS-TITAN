"""Stage61: evidence scorecard integration and adversarial no-go tests.

Tests execute real Stage59 preflight, Stage60 leak-safe OOS and Stage58
SYNTHETIC book/cost simulation against disposable fabricated NSE-like data.
No real history, verified profit, paper orders, broker or capital mutations.
"""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from nexus_titan.data.historical_fo_catalog import HistoricalCatalogResult
from nexus_titan.research.stage61_evidence_scorecard import (
    Stage61FOMarketReadinessScorecard,
    inspect_stage61_fo_evidence,
)
from scripts.run_stage61_fo_evidence_smoke import _inputs

ROOT = Path(__file__).resolve().parents[1]


def _evaluate(root, underlying="NIFTY", with_execution=True):
    hist, oos, execution = _inputs(root, underlying)
    return inspect_stage61_fo_evidence(
        hist, oos, execution=execution if with_execution else None,
    ), hist, oos, execution


def _never_authorized(result):
    assert isinstance(result, Stage61FOMarketReadinessScorecard)
    assert result.schema_version == 1
    assert not result.source_vendor_authenticated
    assert not result.source_licence_authenticated
    assert not result.independently_verified_option_chain
    assert not result.execution_scenario_bound_to_holdout
    assert not result.real_orderbook_depth_authenticated
    assert not result.actual_execution_or_fees_reconciled
    assert not result.genuine_futures_options_backtest_verified
    assert not result.strategy_promotion_authorized
    assert not result.global_risk_veto_unbypassable
    assert not result.independently_verified_human_identity
    assert not result.unified_capital_settlement_verified
    assert not result.live_trading_enabled
    assert not result.production_ready
    assert result.broker_orders_transmitted == 0
    assert len(result.mandatory_release_blockers) >= 8
    assert "NO_ACTUAL_FO_PNL_OR_REALISTIC_SHADOW_FILLS" in result.mandatory_release_blockers


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_real_stage59_stage60_stage58_local_objects_have_clean_shape_but_no_go(tmp_path, underlying):
    result, hist, oos, execution = _evaluate(tmp_path, underlying)
    assert result.underlying == underlying
    assert result.futures_symbol == underlying + "FUT"
    assert result.futures_dataset_id == hist.dataset_id
    assert result.inspected_candles == hist.count == 46
    assert result.oos_folds == 3
    assert result.oos_predictions == oos.total_directional_predictions
    assert result.oos_hit_rate == oos.overall_directional_hit_rate
    assert result.synthetic_execution_fragment_count == len(execution.fragments)
    assert result.synthetic_execution_fee_reserve == execution.conservative_fee_reserve
    assert result.local_inputs_structurally_consistent
    assert result.structural_conflicts == ()
    assert len(result.local_evidence_sha256) == 64
    assert "S61-EXECUTION-NOT-LINKED-TO-OOS" in result.missing_evidence
    assert "S61-OPTIONS-CATALOG-ABSENT" in result.missing_evidence
    assert all(x.status in ("LOCAL_CONSISTENCY", "MISSING_EVIDENCE") for x in result.checks)
    _never_authorized(result)


def test_deterministic_no_write_evidence_and_same_source_bytes(tmp_path):
    h, o, e = _inputs(tmp_path)
    before = (tmp_path / "futures.csv").read_bytes()
    a = inspect_stage61_fo_evidence(h, o, execution=e)
    b = inspect_stage61_fo_evidence(h, o, execution=e)
    assert a == b
    assert before == (tmp_path / "futures.csv").read_bytes()
    assert not list(tmp_path.glob("*.sqlite*"))
    _never_authorized(a)


def test_missing_execution_scenario_is_missing_not_an_error_or_implicit_fill(tmp_path):
    r, h, o, e = _evaluate(tmp_path, with_execution=False)
    assert r.local_inputs_structurally_consistent
    assert r.synthetic_execution_fragment_count == 0
    assert r.synthetic_execution_fee_reserve is None
    assert "S61-SIMULATED-EXECUTION-ABSENT" in r.missing_evidence
    _never_authorized(r)


def test_quoted_synthetic_execution_has_no_semantic_futures_holdout_link(tmp_path):
    r, h, o, e = _evaluate(tmp_path)
    assert e.segment == "FUTURES"
    assert e.filled_quantity > 0
    assert r.local_inputs_structurally_consistent
    assert "S61-EXECUTION-NOT-LINKED-TO-OOS" in r.missing_evidence
    assert r.execution_scenario_bound_to_holdout is False
    assert r.actual_execution_or_fees_reconciled is False
    _never_authorized(r)


def test_tampered_stage59_file_hash_does_not_match_oos_report(tmp_path):
    h, o, e = _inputs(tmp_path)
    changed = replace(h, file_sha256="f" * 64)
    r = inspect_stage61_fo_evidence(changed, o, execution=e)
    assert not r.local_inputs_structurally_consistent
    assert "S61-STAGE60-HISTORY-BINDING" in r.structural_conflicts
    assert r.local_evidence_sha256 is None
    _never_authorized(r)


@pytest.mark.parametrize("field,update", [
    ("dataset_id", "DIFFERENT"),
    ("symbol", "DIFFERENTFUT"),
    ("underlying", "OTHER"),
    ("timeframe", "5m"),
    ("expiry_date", "2026-11-04"),
    ("file_sha256", "d" * 64),
])
def test_oos_report_must_match_exact_stage59_history_identity(tmp_path, field, update):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, replace(o, **{{"file_sha256": "source_file_sha256", "expiry_date": "contract_expiry_date"}.get(field, field): update}), execution=e)
    assert not r.local_inputs_structurally_consistent
    assert "S61-STAGE60-HISTORY-BINDING" in r.structural_conflicts
    _never_authorized(r)


@pytest.mark.parametrize("field,value", [
    ("vendor_identity_authenticated", True),
    ("licence_authenticated", True),
    ("official_contract_master_authenticated", True),
    ("exchange_calendar_authenticated", True),
    ("source_is_independently_verified_exchange_history", True),
    ("full_exchange_universe_coverage_verified", True),
    ("real_orderbook_depth_present", True),
    ("fill_or_backtest_performance_verified", True),
    ("approved_for_strategy_promotion", True),
    ("production_ready", True),
    ("live_orders_transmitted", 1),
])
def test_spoofed_stage59_trust_flags_are_conflicts_not_real_evidence(tmp_path, field, value):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(replace(h, **{field: value}), o, execution=e)
    assert not r.local_inputs_structurally_consistent
    assert "S61-STAGE59-SOURCE-SHAPE" in r.structural_conflicts
    _never_authorized(r)


@pytest.mark.parametrize("field", [
    "dataset_source_authenticated",
    "licence_authenticated",
    "official_historical_lot_master_authenticated",
    "exchange_calendar_authenticated",
    "options_quotes_cross_instrument_synchronized",
    "executable_depth_verified",
    "margin_and_funding_verified",
    "execution_costs_or_broker_fills_verified",
    "real_fo_backtest_performance_verified",
    "strategy_promotion_authorized",
    "capital_ledger_updated",
    "independent_global_risk_veto_enforced",
    "live_trading_enabled",
    "production_ready",
])
def test_spoofed_stage60_authority_flags_are_not_upgraded(tmp_path, field):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, replace(o, **{field: True}), execution=e)
    assert "S61-STAGE60-HISTORY-BINDING" in r.structural_conflicts
    _never_authorized(r)


def test_spoofed_stage60_live_order_counter_fails(tmp_path):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, replace(o, live_orders_transmitted=1), execution=e)
    assert not r.local_inputs_structurally_consistent
    _never_authorized(r)


@pytest.mark.parametrize("field,value", [
    ("total_directional_predictions", 99),
    ("total_correct_directions", 99),
    ("total_candidate_labels", 99),
    ("total_flat_market_misses", 99),
    ("overall_directional_hit_rate", Decimal("0.99")),
    ("evidence_verdict", "ROBUST_BACKTEST_WINNER"),
    ("evidence_sample_sufficient", True),
])
def test_oos_aggregate_counts_and_verdict_cannot_be_overridden(tmp_path, field, value):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, replace(o, **{field: value}), execution=e)
    assert "S61-STAGE60-HELDOUT-LABELS" in r.structural_conflicts
    assert not r.local_inputs_structurally_consistent
    _never_authorized(r)


def test_future_label_injected_into_previous_fold_is_rejected(tmp_path):
    h, o, e = _inputs(tmp_path)
    fold = o.folds[0]
    altered = replace(fold.observations[0], target_at=fold.holdout_last_at + timedelta(minutes=1))
    replacement = replace(fold, observations=(altered,) + fold.observations[1:])
    r = inspect_stage61_fo_evidence(h, replace(o, folds=(replacement,) + o.folds[1:]), execution=e)
    assert "S61-STAGE60-HELDOUT-LABELS" in r.structural_conflicts
    _never_authorized(r)


def test_same_prediction_cannot_be_recounted_twice_in_fold(tmp_path):
    h, o, e = _inputs(tmp_path)
    fold = o.folds[0]
    altered = replace(fold.observations[1], origin_at=fold.observations[0].origin_at)
    f = replace(fold, observations=(fold.observations[0], altered) + fold.observations[2:])
    r = inspect_stage61_fo_evidence(h, replace(o, folds=(f,) + o.folds[1:]), execution=e)
    assert "S61-STAGE60-HELDOUT-LABELS" in r.structural_conflicts
    _never_authorized(r)


def test_positive_perfect_directional_score_can_never_be_strategy_promotion(tmp_path):
    h, o, e = _inputs(tmp_path)
    modified = replace(o, evidence_sample_sufficient=True, evidence_verdict="EXPLORATORY_SAMPLE_ONLY")
    r = inspect_stage61_fo_evidence(h, modified, execution=e)
    assert not r.strategy_promotion_authorized
    assert not r.genuine_futures_options_backtest_verified
    _never_authorized(r)


@pytest.mark.parametrize("field", [
    "depth_provenance_independently_authenticated",
    "official_contract_master_independently_authenticated",
    "official_fees_or_margin_verified",
    "capital_reserved_in_any_account",
    "broker_fill_reconciliation_verified",
    "external_human_identity_verified",
    "independent_risk_veto_enforced",
    "approved_for_strategy_promotion",
    "live_trading_enabled",
    "production_ready",
])
def test_spoofed_execution_authentication_rejected(tmp_path, field):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, o, execution=replace(e, **{field: True}))
    assert "S61-STAGE58-ARITHMETIC" in r.structural_conflicts
    assert r.synthetic_execution_fee_reserve is None
    _never_authorized(r)


@pytest.mark.parametrize("field,value", [
    ("filled_quantity", 999),
    ("remaining_quantity", 999),
    ("status", "FILLED_WHEN_PARTIAL"),
    ("conservative_fee_reserve", -1),
    ("conservative_fee_reserve", 0),
    ("fragment_fees_sum", float("nan")),
    ("aggregate_fee_estimate", float("inf")),
    ("fill_ratio", 2.0),
    ("live_orders_transmitted", 1),
])
def test_fake_simulated_fills_and_fee_accumulator_are_detected(tmp_path, field, value):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, o, execution=replace(e, **{field: value}))
    assert not r.local_inputs_structurally_consistent
    assert "S61-STAGE58-ARITHMETIC" in r.structural_conflicts
    _never_authorized(r)


def test_no_fill_cannot_have_paper_fee_or_execution_price(tmp_path):
    h, o, e = _inputs(tmp_path)
    first = e.fragments[0]
    forged = replace(first, filled_quantity=0, fees=first.fees)
    r = inspect_stage61_fo_evidence(h, o, execution=replace(
        e, fragments=(forged,) + e.fragments[1:],
    ))
    assert "S61-STAGE58-ARITHMETIC" in r.structural_conflicts
    _never_authorized(r)


def test_duplicate_execution_event_id_fails_scorecard(tmp_path):
    h, o, e = _inputs(tmp_path)
    assert len(e.fragments) >= 2
    altered = replace(e.fragments[1], event_id=e.fragments[0].event_id)
    r = inspect_stage61_fo_evidence(h, o, execution=replace(
        e, fragments=(e.fragments[0], altered),
    ))
    assert "S61-STAGE58-ARITHMETIC" in r.structural_conflicts
    _never_authorized(r)


def test_option_segment_synthetic_quote_does_not_prove_futures_execution(tmp_path):
    h, o, e = _inputs(tmp_path)
    r = inspect_stage61_fo_evidence(h, o, execution=replace(e, segment="OPTIONS"))
    assert "S61-FUTURES-EXECUTION-SEGMENT-MISMATCH" in r.missing_evidence
    assert not r.execution_scenario_bound_to_holdout
    _never_authorized(r)


def test_invalid_execution_type_refused_without_side_effect(tmp_path):
    h, o, e = _inputs(tmp_path)
    with pytest.raises(TypeError, match="Stage58"):
        inspect_stage61_fo_evidence(h, o, execution=object())


def test_invalid_history_and_oos_types_refused_without_side_effect(tmp_path):
    h, o, e = _inputs(tmp_path)
    with pytest.raises(TypeError, match="Stage59"):
        inspect_stage61_fo_evidence(object(), o)
    with pytest.raises(TypeError, match="Stage60"):
        inspect_stage61_fo_evidence(h, object())


def test_spoofed_catalog_claimed_real_exchange_authority_is_a_conflict(tmp_path):
    h, o, e = _inputs(tmp_path)
    bogus = HistoricalCatalogResult(
        partitions=(object(),),
        dataset_count=1, snapshot_count=1, unique_contracts=1,
        first_observed_at=h.first_observed_at,
        last_observed_at=h.last_observed_at,
        external_source_authenticated=True,
    )
    r = inspect_stage61_fo_evidence(h, o, execution=e, option_catalog=bogus)
    assert "S61-STAGE44-OPTIONS-METADATA" in r.structural_conflicts
    assert not r.independently_verified_option_chain
    _never_authorized(r)


def test_unverified_options_catalog_without_oos_join_is_not_authenticated(tmp_path):
    h, o, e = _inputs(tmp_path)
    fake = HistoricalCatalogResult(
        partitions=(object(),),
        dataset_count=1, snapshot_count=1, unique_contracts=1,
        first_observed_at=h.first_observed_at,
        last_observed_at=h.last_observed_at,
    )
    r = inspect_stage61_fo_evidence(h, o, execution=e, option_catalog=fake)
    assert "S61-STAGE44-OPTIONS-METADATA" in r.structural_conflicts
    _never_authorized(r)


def test_scorecard_checksum_changes_when_source_claim_changes(tmp_path):
    h, o, e = _inputs(tmp_path)
    a = inspect_stage61_fo_evidence(h, o, execution=e)
    b = inspect_stage61_fo_evidence(h, o, execution=None)
    assert a.local_evidence_sha256 != b.local_evidence_sha256
    assert b.local_inputs_structurally_consistent
    _never_authorized(a)
    _never_authorized(b)


def test_stage61_no_broker_smoke_for_both_underlyings():
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_stage61_fo_evidence_smoke.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=40, check=False,
    )
    assert p.returncode == 0, p.stderr
    info = json.loads(p.stdout)
    assert info["mode"] == "STAGE61_SYNTHETIC_EVIDENCE_NO_GO_SCORECARD_ONLY"
    for underlying in ("nifty", "banknifty"):
        v = info[underlying]
        assert v["candles"] == 46
        assert v["oos_folds"] == 3
        assert v["synthetic_execution_fragments"] >= 1
        assert v["local_inputs_structurally_consistent"] is True
        assert v["execution_scenario_bound_to_holdout"] is False
        assert v["genuine_futures_options_backtest_verified"] is False
        assert v["strategy_promotion_authorized"] is False
        assert v["production_ready"] is False
        assert v["broker_orders_transmitted"] == 0
    assert info["actual_fo_pnl_verified"] is False
    assert info["real_vendor_data_present"] is False
    assert info["broker_orders_transmitted"] == 0
