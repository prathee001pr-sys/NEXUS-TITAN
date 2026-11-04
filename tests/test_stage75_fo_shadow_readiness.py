"""Stage75 integration QA: only fabricated F&O inputs and NO-GO outputs."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus_titan.data.stage71_fo_asof_alignment import (
    Stage71AlignedObservation, Stage71FOLearningPreflight,
)
from nexus_titan.derivatives.options_engine import calculate_option_greeks
from nexus_titan.derivatives.stage72_expiry_iv_research import (
    Stage72OptionResearchRow, Stage72OptionsResearchReport,
)
from nexus_titan.evolve.stage73_fo_experience import FOEvolveReview
from nexus_titan.intelligence.calibration import ProbabilityCalibrator
from nexus_titan.operations.stage69_risk_budget_preflight import Stage69ResearchPreflight
from nexus_titan.shadow.stage75_fo_shadow_readiness import (
    Stage75ReadinessBlocked, Stage75VirtualResearchBudget,
    inspect_stage75_fo_shadow_readiness,
)
from nexus_titan.simulation.stage74_fo_options_scenario_lab import (
    Stage74ScenarioResearchReport, Stage74StressOutcome,
)

ROOT = Path(__file__).resolve().parents[1]
AT = datetime(2026, 11, 2, 3, 46, tzinfo=timezone.utc)
SHA_71 = hashlib.sha256(b"stage71 synthetic alignment").hexdigest()
SHA_OPT = hashlib.sha256(b"stage71 synthetic options").hexdigest()
SHA_72 = hashlib.sha256(b"stage72 synthetic report").hexdigest()
SHA_73 = hashlib.sha256(b"stage73 synthetic OOS").hexdigest()
SHA_74 = hashlib.sha256(b"stage74 synthetic scenarios").hexdigest()


def fixture(underlying="NIFTY", capital_cents=10_000_000):
    bar_end = AT - timedelta(minutes=1)
    observed = Stage71AlignedObservation(
        underlying=underlying, option_dataset_id="qa-options",
        option_snapshot_sha256=SHA_OPT, option_observed_at=AT,
        option_quote_count=1, futures_dataset_id="qa-futures",
        futures_csv_sha256=SHA_71,
        futures_bar_opened_at=bar_end - timedelta(minutes=1),
        futures_bar_closed_at=bar_end,
        futures_age_seconds=60,
    )
    st71 = Stage71FOLearningPreflight(
        underlying=underlying, option_dataset_count=1,
        observed_option_snapshots=1, observed_futures_bars=3,
        aligned_observation_count=1, first_option_observed_at=AT,
        last_option_observed_at=AT, latest_completed_futures_at=bar_end,
        input_alignment_sha256=SHA_71, observations=(observed,),
    )
    row = Stage72OptionResearchRow(
        strike=24000.0, option_type="CE",
        bid=19.0, ask=20.0, midpoint=19.5, spread_bps=512.82,
        iv_bid=.15, iv_mid=.16, iv_ask=.17,
        model_greeks_at_mid=calculate_option_greeks(
            24000, 24000, 3, .16,
        ),
    )
    st72 = Stage72OptionsResearchReport(
        underlying=underlying, symbol=underlying+"OPT",
        observation_time=AT,
        declared_expiry_cutoff=AT + timedelta(days=3),
        time_to_expiry_days=3, source_option_sha256=SHA_OPT,
        source_alignment_sha256=SHA_71,
        risk_free_rate_assumption=.06, dividend_yield_assumption=0,
        rows=(row,), research_output_sha256=SHA_72,
    )
    empty_calibration = ProbabilityCalibrator().evaluate([])
    st73 = FOEvolveReview(
        champion="champion", challenger="challenger",
        champion_calibration=empty_calibration,
        challenger_calibration=empty_calibration,
        paired_count=0, unpaired_count=0, unresolved_count=0,
        champion_paired_brier=None, challenger_paired_brier=None,
        challenger_minus_champion_brier=None,
        lower_challenger_brier_observed=False,
        research_review_suggested=False,
        regime_scores=(), journal_head_sha256=SHA_73,
        review_sha256=SHA_73, blockers=("INSUFFICIENT_EVIDENCE",),
    )

    def stressed(name, sell_price):
        proceeds = float(sell_price*25)
        return Stage74StressOutcome(
            case_name=name, strike=24000.0, option_type="CE",
            lots=1, quantity=25,
            stressed_spot=24000, stressed_iv=.16,
            stressed_days_to_expiry=2.9, model_price_per_unit=19.5,
            model_value_change_rupees=0,
            indicative_exit_bid_proxy=sell_price,
            hypothetical_exit_price_after_friction=sell_price,
            hypothetical_entry_debit_rupees=500.,
            hypothetical_exit_proceeds_rupees=proceeds,
            indicative_entry_charges_rupees=0.,
            indicative_exit_charges_rupees=0.,
            hypothetical_round_trip_net_rupees=proceeds-500.,
            hypothetical_premium_at_risk_rupees=500.,
        )

    st74 = Stage74ScenarioResearchReport(
        underlying=underlying, symbol=underlying+"OPT",
        observation_time=AT, model_reference_spot=24000.,
        source_stage72_sha256=SHA_72, source_stage71_sha256=SHA_71,
        indicative_cost_schedule="qa-only",
        outcomes=(stressed("BASE", 16.), stressed("LIQUIDITY_LOSS", 0.)),
        scenario_digest_sha256=SHA_74,
    )
    st69 = Stage69ResearchPreflight(
        account_id="qa-account", request_id="synthetic-equity-req",
        source="SYNTHETIC_EQUITY_RESEARCH", local_budget_integrity_checked=True,
        local_synthetic_risk_screen_passed=True, local_budget_caps_checked=True,
        local_research_preflight_passed=True, requested_notional_cents=50000,
        blockers=(), observed_budget_revision=1,
    )
    budget = Stage75VirtualResearchBudget(
        account_id="qa-account", virtual_capital_cents=capital_cents,
    )
    return dict(stage71=st71, stage72=st72, stage73=st73,
                stage74=st74, stage69=st69, budget=budget)


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_all_local_structural_checks_pass_but_shadow_always_no_go(underlying):
    inputs = fixture(underlying=underlying)
    packet = inspect_stage75_fo_shadow_readiness(**inputs)
    assert packet.underlying == underlying
    assert packet.local_chain_structurally_consistent
    assert packet.research_budget_screen_passed
    assert packet.long_option_entry_debit_cents == 50000
    assert packet.maximum_hypothetical_scenario_loss_cents == 50000
    assert packet.option_debit_allocation_bps_rounded_up == 50
    assert packet.maximum_scenario_loss_bps_rounded_up == 50
    assert packet.source_stage71_sha256 == SHA_71
    assert len(packet.research_packet_sha256) == 64
    assert inspect_stage75_fo_shadow_readiness(**inputs) == packet
    assert len(packet.blockers) >= 7
    assert packet.verdict.endswith("NO_GO")
    assert all(not getattr(packet, flag) for flag in (
        "independently_authenticated_fo_source",
        "independently_verified_forward_outcomes",
        "official_margin_and_fees_verified",
        "global_risk_veto_unbypassable",
        "atomic_capital_book_verified",
        "owner_approval_authenticated",
        "real_shadow_trading_started",
        "paper_order_authorized",
        "strategy_promotion_authorized",
        "live_trading_enabled",
    ))
    assert packet.actual_fills_recorded == 0
    assert packet.broker_orders_transmitted == 0


@pytest.mark.parametrize("capital", [100_000, 500_000, 2_000_000])
def test_variable_capital_never_fixed_to_50000_rupees(capital):
    p = inspect_stage75_fo_shadow_readiness(**fixture(capital_cents=capital))
    assert p.virtual_capital_cents == capital
    assert not p.live_trading_enabled


def test_excessive_research_debit_is_blocked_even_with_equity_risk_preflight_pass():
    p = inspect_stage75_fo_shadow_readiness(**fixture(capital_cents=75_000))
    assert p.research_budget_screen_passed is False
    assert "RESEARCH_PREMIUM_OR_STRESS_BUDGET_EXCEEDED" in p.blockers
    assert any(c.name == "variable_capital_stress_budget"
               and c.status == "LOCAL_RESEARCH_BLOCKED" for c in p.checks)
    assert not p.paper_order_authorized


def test_synthetic_equity_preflight_cannot_authorize_fo():
    inputs = fixture()
    inputs["stage69"] = replace(inputs["stage69"],
                                local_research_preflight_passed=True,
                                local_budget_caps_checked=True)
    p = inspect_stage75_fo_shadow_readiness(**inputs)
    assert any("cannot authorize F&O" in c.detail for c in p.checks)
    inputs["stage69"] = replace(inputs["stage69"], order_submission_authorized=True)
    with pytest.raises(Stage75ReadinessBlocked, match="unauthorized"):
        inspect_stage75_fo_shadow_readiness(**inputs)


def test_wrong_underlying_and_different_stage_hashes_fail_closed():
    original = fixture()
    cases = (
        ("stage71", replace(original["stage71"], underlying="BANKNIFTY")),
        ("stage72", replace(original["stage72"], source_alignment_sha256=SHA_OPT)),
        ("stage74", replace(original["stage74"], source_stage72_sha256=SHA_OPT)),
        ("stage72", replace(original["stage72"], source_option_sha256=SHA_74)),
    )
    for key, changed in cases:
        inputs = dict(original)
        inputs[key] = changed
        with pytest.raises(Stage75ReadinessBlocked):
            inspect_stage75_fo_shadow_readiness(**inputs)


def test_future_candle_closed_after_observation_is_rejected():
    inputs = fixture()
    first = inputs["stage71"].observations[0]
    forged = replace(first, futures_bar_closed_at=AT+timedelta(seconds=1),
                     futures_age_seconds=-1)
    inputs["stage71"] = replace(inputs["stage71"], observations=(forged,))
    with pytest.raises(Stage75ReadinessBlocked, match="look-ahead|age mismatch"):
        inspect_stage75_fo_shadow_readiness(**inputs)


def test_duplicate_or_inconsistent_scenario_cashflows_are_rejected():
    inputs = fixture()
    one = inputs["stage74"].outcomes[0]
    inputs["stage74"] = replace(inputs["stage74"], outcomes=(one, one))
    with pytest.raises(Stage75ReadinessBlocked, match="consistent research contract"):
        inspect_stage75_fo_shadow_readiness(**inputs)
    inputs = fixture()
    forged = replace(inputs["stage74"].outcomes[0],
                     hypothetical_round_trip_net_rupees=1234.)
    inputs["stage74"] = replace(
        inputs["stage74"],
        outcomes=(forged,) + inputs["stage74"].outcomes[1:],
    )
    with pytest.raises(Stage75ReadinessBlocked, match="arithmetic"):
        inspect_stage75_fo_shadow_readiness(**inputs)


@pytest.mark.parametrize("key,attribute", [
    ("stage71", "paper_order_authorized"),
    ("stage72", "live_trading_enabled"),
    ("stage73", "strategy_promotion_authorized"),
    ("stage74", "actual_market_depth_verified"),
    ("stage69", "single_atomic_authority_for_all_ledger_books"),
])
def test_forged_authority_claims_block_all_evidence(key, attribute):
    inputs = fixture()
    inputs[key] = replace(inputs[key], **{attribute: True})
    with pytest.raises(Stage75ReadinessBlocked, match="unauthorized"):
        inspect_stage75_fo_shadow_readiness(**inputs)


def test_forged_challenger_improvement_on_zero_samples_denied():
    inputs = fixture()
    inputs["stage73"] = replace(
        inputs["stage73"], research_review_suggested=True,
        challenger_minus_champion_brier=-.1,
    )
    with pytest.raises(Stage75ReadinessBlocked, match="model review"):
        inspect_stage75_fo_shadow_readiness(**inputs)


def test_invalid_budget_cannot_be_a_trading_permission():
    for capital in (True, 0, -1, 10**16):
        inputs = fixture()
        inputs["budget"] = replace(inputs["budget"], virtual_capital_cents=capital)
        with pytest.raises(Stage75ReadinessBlocked, match="variable virtual-capital"):
            inspect_stage75_fo_shadow_readiness(**inputs)


def test_no_input_cli_is_unchanged_permanent_no_go():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage75_fo_shadow_readiness_smoke.py")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    assert packet["mode"] == "STAGE75_NO_INPUT_FO_SHADOW_READINESS"
    assert packet["live_trading_enabled"] is False
    assert packet["real_shadow_trading_started"] is False
    assert packet["broker_orders_transmitted"] == 0
    assert packet["verdict"].endswith("NO_GO")
