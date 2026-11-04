"""Stage73 synthetic evidence tests: no actual F&O data, model fit or orders."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nexus_titan.derivatives.options_engine import calculate_option_greeks
from nexus_titan.derivatives.stage72_expiry_iv_research import (
    Stage72OptionResearchRow, Stage72OptionsResearchReport,
)
from nexus_titan.evolve.stage73_fo_experience import (
    Stage73Blocked, Stage73FOExperienceMemory,
)

ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
START = datetime(2026, 11, 2, 9, 16, tzinfo=IST)
EXPIRY = datetime(2026, 11, 5, 15, 30, tzinfo=IST)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def stage72(i, underlying="NIFTY"):
    when = START + timedelta(minutes=10*i)
    row = Stage72OptionResearchRow(
        strike=24000, option_type="CE", bid=300, ask=301, midpoint=300.5,
        spread_bps=33.28, iv_bid=.18, iv_mid=.2, iv_ask=.22,
        model_greeks_at_mid=calculate_option_greeks(24000, 24000, 3, .2),
    )
    return Stage72OptionsResearchReport(
        underlying=underlying, symbol=underlying+"OPT",
        observation_time=when, declared_expiry_cutoff=EXPIRY,
        time_to_expiry_days=3,
        source_option_sha256=sha(f"option{i}"),
        source_alignment_sha256=sha(f"alignment{i}"),
        risk_free_rate_assumption=.06, dividend_yield_assumption=0,
        rows=(row,), research_output_sha256=sha(f"stage72{i}"),
    )


def add(memory, i, model, probability, *, report=None, regime="TREND"):
    r = report or stage72(i)
    return memory.add_forecast(
        r, episode_id=f"event{i}", model_id=model, probability_up=probability,
        regime=regime, predicted_at=r.observation_time,
        horizon_at=r.observation_time + timedelta(minutes=5),
        model_training_cutoff=r.observation_time - timedelta(days=1),
    )


def resolve(memory, i, up=True, *, when=None):
    return memory.record_outcome(
        episode_id=f"event{i}", up=up,
        resolved_at=when or START + timedelta(minutes=10*i+6),
        declared_label_sha256=sha(f"label{i}"),
    )


def test_challenger_improved_paired_brier_but_no_strategy_promotion():
    m = Stage73FOExperienceMemory()
    for i in range(4):
        add(m, i, "A", .5)
        add(m, i, "B", .9)
        resolve(m, i, True)
    result = m.compare(champion="A", challenger="B", min_paired_samples=4)
    assert m.verify_local_integrity()
    assert result.paired_count == 4 and result.unpaired_count == 0
    assert result.champion_paired_brier == pytest.approx(.25)
    assert result.challenger_paired_brier == pytest.approx(.01)
    assert result.challenger_minus_champion_brier == pytest.approx(-.24)
    assert result.lower_challenger_brier_observed
    assert result.research_review_suggested
    assert result.challenger_calibration.sample_count == 4
    assert result.regime_scores
    assert len(result.review_sha256) == 64
    for flag in (
        "independent_exchange_data_verified", "independently_verified_outcomes",
        "real_oos_protocol_verified", "option_trade_pnl_verified",
        "model_weights_updated", "strategy_promotion_authorized",
        "paper_order_authorized", "live_trading_enabled",
    ):
        assert getattr(result, flag) is False
    assert result.broker_orders_transmitted == 0
    assert result.verdict.endswith("NO_GO")
    assert m.compare(champion="A", challenger="B", min_paired_samples=4) == result


def test_insufficient_and_unpaired_evidence_do_not_suggest_review():
    m = Stage73FOExperienceMemory()
    add(m, 0, "A", .5)
    add(m, 0, "B", .9)
    resolve(m, 0)
    result = m.compare(champion="A", challenger="B")
    assert result.lower_challenger_brier_observed
    assert not result.research_review_suggested
    add(m, 1, "A", .6)
    resolve(m, 1)
    result = m.compare(champion="A", challenger="B", min_paired_samples=2)
    assert result.unpaired_count == 1
    assert not result.research_review_suggested


def test_duplicated_forecasts_outcomes_and_forecast_after_label_fail_closed():
    m = Stage73FOExperienceMemory()
    add(m, 0, "A", .5)
    with pytest.raises(Stage73Blocked, match="Duplicate"):
        add(m, 0, "A", .6)
    resolve(m, 0)
    with pytest.raises(Stage73Blocked, match="replay"):
        resolve(m, 0)
    with pytest.raises(Stage73Blocked, match="resolved"):
        add(m, 0, "B", .8)


def test_one_episode_must_use_same_data_regime_and_horizon():
    m = Stage73FOExperienceMemory()
    add(m, 0, "A", .5)
    with pytest.raises(Stage73Blocked, match="differing episode inputs"):
        add(m, 0, "B", .7, regime="RANGE")
    with pytest.raises(Stage73Blocked, match="differing episode inputs"):
        add(m, 0, "B", .7, report=replace(stage72(0), research_output_sha256=sha("other")))
    with pytest.raises(Stage73Blocked, match="differing episode inputs"):
        m.add_forecast(
            stage72(0), episode_id="event0", model_id="B", probability_up=.7,
            regime="TREND", predicted_at=START,
            horizon_at=START + timedelta(minutes=6),
            model_training_cutoff=START - timedelta(days=1),
        )


def test_future_knowledge_and_stale_features_denied():
    m = Stage73FOExperienceMemory()
    r = stage72(0)
    for predicted, trained in (
        (START, START + timedelta(minutes=1)),
        (START + timedelta(minutes=3), START - timedelta(days=1)),
    ):
        with pytest.raises(Stage73Blocked, match="Future knowledge"):
            m.add_forecast(
                r, episode_id="event0", model_id="A", probability_up=.7,
                regime="TREND", predicted_at=predicted,
                horizon_at=START + timedelta(minutes=5),
                model_training_cutoff=trained,
            )


def test_outcome_before_horizon_or_after_expiry_denied():
    m = Stage73FOExperienceMemory()
    add(m, 0, "A", .5)
    for t in (START + timedelta(minutes=4), EXPIRY + timedelta(seconds=1)):
        with pytest.raises(Stage73Blocked, match="Outcome before horizon"):
            resolve(m, 0, when=t)


@pytest.mark.parametrize("bad", [-0.01, 1.01, True, float("nan"), float("inf")])
def test_invalid_probability_rejected(bad):
    with pytest.raises(Stage73Blocked, match="Probability"):
        add(Stage73FOExperienceMemory(), 0, "A", bad)


def test_no_label_before_forecast_and_no_nonbinary_labels():
    m = Stage73FOExperienceMemory()
    with pytest.raises(Stage73Blocked, match="precede"):
        resolve(m, 0)
    add(m, 0, "A", .5)
    with pytest.raises(Stage73Blocked, match="bool"):
        resolve(m, 0, 1)


def test_forged_approval_and_bad_hash_rejected():
    m = Stage73FOExperienceMemory()
    r = stage72(0)
    for fake in (
        replace(r, live_trading_enabled=True),
        replace(r, strategy_promotion_authorized=True),
        replace(r, research_output_sha256="NOT_A_HASH"),
    ):
        with pytest.raises(Stage73Blocked):
            add(m, 0, "A", .5, report=fake)


def test_tampering_detected_without_claiming_external_signature():
    m = Stage73FOExperienceMemory()
    original = add(m, 0, "A", .5)
    assert m.verify_local_integrity()
    m._forecasts[("event0", "A")] = replace(original, probability_up=.95)
    assert m.verify_local_integrity() is False
    with pytest.raises(Stage73Blocked, match="integrity"):
        m.compare(champion="A", challenger="B")


def test_pending_outcomes_have_no_performance_claim():
    m = Stage73FOExperienceMemory()
    add(m, 0, "A", .5)
    add(m, 0, "B", .9)
    result = m.compare(champion="A", challenger="B")
    assert result.unresolved_count == 1
    assert result.paired_count == 0
    assert result.champion_paired_brier is None
    assert result.research_review_suggested is False


def test_empty_memory_safe_and_local_journal_deterministic():
    m = Stage73FOExperienceMemory()
    assert m.verify_local_integrity()
    report = m.compare(champion="A", challenger="B")
    assert report.paired_count == 0
    assert report.journal_head_sha256 == "0"*64
    assert not report.live_trading_enabled


def test_invalid_budget_and_model_ids_rejected():
    for v in (True, 0, 20001):
        with pytest.raises(Stage73Blocked, match="budget"):
            Stage73FOExperienceMemory(max_forecasts=v)
    with pytest.raises(Stage73Blocked, match="Distinct"):
        Stage73FOExperienceMemory().compare(champion="A", challenger="A")


def test_offline_smoke_proves_no_model_updates_or_orders():
    p = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage73_fo_evolve_smoke.py")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    assert d["verdict"] == "STAGE73_RESEARCH_ONLY_NO_GO"
    assert d["model_weights_updated"] is False
    assert d["broker_orders_transmitted"] == 0
    assert d["live_trading_enabled"] is False
