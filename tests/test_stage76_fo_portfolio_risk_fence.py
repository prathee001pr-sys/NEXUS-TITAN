"""Stage76 adversarial synthetic F&O portfolio tests; NO paper/live approval."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from nexus_titan.operations.stage76_fo_portfolio_risk_fence import (
    Stage76FOResearchPolicy, Stage76RiskBlocked,
    Stage76UntrustedRiskTelemetry, inspect_stage76_fo_portfolio_risk,
)
from nexus_titan.shadow.stage75_fo_shadow_readiness import (
    Stage75FOShadowReadinessPacket, Stage75ReadinessCheck,
)

ROOT = Path(__file__).resolve().parents[1]
CAP = 10_000_000  # ₹100,000; purely synthetic and NOT fixed by the engine.
SHA = hashlib.sha256(b"qa-unverified-stage75").hexdigest()


def sample_packet(underlying="NIFTY", strike=24000, side="CE",
                  debit=1_000_000, loss=600_000, capital=CAP,
                  account="qa-account", local_pass=True):
    checks = (
        Stage75ReadinessCheck("point_in_time_research_chain", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("out_of_sample_model_review", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("long_option_scenario_accounting", "LOCAL_RESEARCH_PASS", "synthetic"),
        Stage75ReadinessCheck("variable_capital_stress_budget",
                              "LOCAL_RESEARCH_PASS" if local_pass else "LOCAL_RESEARCH_BLOCKED",
                              "synthetic"),
        Stage75ReadinessCheck("global_fo_risk_capital_gate", "EXTERNAL_MISSING", "no global risk"),
        Stage75ReadinessCheck("real_fo_forward_shadow_evidence", "EXTERNAL_MISSING", "no real feed"),
    )
    return Stage75FOShadowReadinessPacket(
        underlying=underlying,
        option_symbol=underlying + "OPT",
        selected_strike=float(strike), selected_option_type=side,
        source_stage71_sha256=SHA, source_stage72_sha256=SHA,
        stage73_review_sha256=SHA, stage74_scenarios_sha256=SHA,
        account_id=account, virtual_capital_cents=capital,
        long_option_entry_debit_cents=debit,
        maximum_hypothetical_scenario_loss_cents=loss,
        option_debit_allocation_bps_rounded_up=(debit*10000+capital-1)//capital,
        maximum_scenario_loss_bps_rounded_up=(loss*10000+capital-1)//capital,
        research_budget_screen_passed=local_pass,
        paired_oos_research_samples=3,
        local_chain_structurally_consistent=True,
        checks=checks,
        blockers=(
            "GLOBAL_UNBYPASSABLE_FO_RISK_GATE_NOT_VERIFIED",
            "ATOMIC_FO_CAPITAL_RESERVATIONS_NOT_VERIFIED",
        ),
        research_packet_sha256=hashlib.sha256(
            f"{underlying}:{strike}:{side}:{debit}:{loss}:{capital}".encode(),
        ).hexdigest(),
    )


def sample_telemetry(**changes):
    return Stage76UntrustedRiskTelemetry(
        account_id="qa-account",
        daily_realized_loss_bps=10,
        drawdown_bps=40,
        consecutive_losses=0,
        kill_switch_active=False,
        risk_engine_healthy=True,
        **changes,
    )


def review(packets=None, *, policy=None, telemetry=None):
    return inspect_stage76_fo_portfolio_risk(
        packets=packets if packets is not None else (
            sample_packet(),
            sample_packet("BANKNIFTY", 54000, "PE", 2_000_000, 1_000_000),
        ),
        policy=policy if policy is not None else Stage76FOResearchPolicy(),
        telemetry=telemetry if telemetry is not None else sample_telemetry(),
    )


def test_two_underlyings_aggregate_research_only_and_deterministic():
    result = review()
    assert result.research_idea_count == 2
    assert result.virtual_capital_cents == CAP
    assert result.total_hypothetical_debit_cents == 3_000_000
    assert result.total_hypothetical_stress_loss_cents == 1_600_000
    assert result.max_theoretical_premium_loss_cents == 3_000_000
    assert result.total_debit_allocation_bps_rounded_up == 3000
    assert result.total_stress_loss_bps_rounded_up == 1600
    assert result.local_portfolio_budget_checks_passed
    assert result.local_untrusted_risk_telemetry_checks_passed
    assert result.local_research_fence_passed
    assert len(result.underlying_exposures) == 2
    assert len(result.local_research_audit_sha256) == 64
    assert any("NOT_GLOBALLY_FENCED" in s for s in result.blockers)
    assert any("NOT_A_SINGLE_ATOMIC_CAPITAL_AUTHORITY" in s for s in result.blockers)
    assert review() == result
    reversed_result = review(packets=(
        sample_packet("BANKNIFTY", 54000, "PE", 2_000_000, 1_000_000),
        sample_packet(),
    ))
    assert reversed_result.local_research_audit_sha256 == result.local_research_audit_sha256
    for attribute in (
        "current_positions_and_pending_orders_reconciled",
        "authoritative_capital_or_reservation_performed",
        "global_mandatory_fo_risk_veto_enforced",
        "independent_risk_telemetry_authenticated",
        "historical_real_fo_data_verified",
        "actual_fill_or_shadow_pnl_verified",
        "owner_approval_authenticated", "order_submission_authorized",
        "paper_order_authorized", "strategy_promotion_authorized",
        "live_trading_enabled",
    ):
        assert getattr(result, attribute) is False
    assert result.broker_orders_transmitted == 0
    assert result.verdict.endswith("NO_GO")


def test_aggregate_limit_blocks_even_if_both_individual_stage75_packets_pass():
    p1 = sample_packet(debit=2_300_000, loss=1_000_000)
    p2 = sample_packet("BANKNIFTY", 54000, debit=2_300_000, loss=1_000_000)
    result = review(packets=(p1, p2))
    assert result.total_debit_allocation_bps_rounded_up == 4600
    assert not result.local_portfolio_budget_checks_passed
    assert not result.local_research_fence_passed
    assert "AGGREGATE_FO_RESEARCH_CAPITAL_OR_STRESS_LIMIT_EXCEEDED" in result.blockers


def test_market_concentration_rejects_even_when_total_budget_passes():
    packets = (
        sample_packet("NIFTY", 24000, debit=2_000_000, loss=1_000_000),
        sample_packet("NIFTY", 24100, "PE", debit=2_000_000, loss=1_000_000),
    )
    result = review(packets=packets)
    assert result.total_debit_allocation_bps_rounded_up == 4000
    assert not result.local_portfolio_budget_checks_passed
    assert result.underlying_exposures[0].debit_allocation_bps_rounded_up == 4000


def test_correlated_conservative_stress_limit_is_independent_cap():
    packets = (
        sample_packet(debit=2_000_000, loss=1_700_000),
        sample_packet("BANKNIFTY", 54000, debit=2_000_000, loss=1_700_000),
    )
    result = review(packets=packets)
    assert result.total_debit_allocation_bps_rounded_up == 4000
    assert result.total_stress_loss_bps_rounded_up == 3400
    assert not result.local_portfolio_budget_checks_passed


@pytest.mark.parametrize("override", [
    {"kill_switch_active": True}, {"risk_engine_healthy": False},
    {"daily_realized_loss_bps": 300}, {"drawdown_bps": 1000},
    {"consecutive_losses": 3},
])
def test_untrusted_risk_telemetry_vetoes_research(override):
    values = dict(
        account_id="qa-account", daily_realized_loss_bps=10,
        drawdown_bps=40, consecutive_losses=0, kill_switch_active=False,
        risk_engine_healthy=True,
    )
    values.update(override)
    result = review(telemetry=Stage76UntrustedRiskTelemetry(**values))
    assert not result.local_untrusted_risk_telemetry_checks_passed
    assert not result.local_research_fence_passed
    assert "UNTRUSTED_RISK_TELEMETRY_VETO_OR_HEALTH_FAILURE" in result.blockers


def test_failed_stage75_local_safety_cannot_be_hidden_by_aggregation():
    packet = sample_packet(local_pass=False)
    result = review(packets=(packet,))
    assert not result.local_research_fence_passed
    assert "STAGE75_LOCAL_RESEARCH_PREREQUISITE_FAILED" in result.blockers


def test_duplicate_instrument_or_cross_account_rejected():
    p = sample_packet()
    with pytest.raises(Stage76RiskBlocked, match="Duplicate"):
        review(packets=(p, replace(p, research_packet_sha256=hashlib.sha256(b"other").hexdigest())))
    with pytest.raises(Stage76RiskBlocked, match="Cross-account"):
        review(packets=(p, sample_packet("BANKNIFTY", 54000, account="second-account")))


def test_independently_declared_different_capitals_cannot_be_aggregated():
    with pytest.raises(Stage76RiskBlocked, match="capital snapshots"):
        review(packets=(sample_packet(), sample_packet(
            "BANKNIFTY", 54000, debit=200_000, loss=100_000, capital=1_000_000,
        )))


def test_forged_external_authority_or_nonzero_orders_rejected():
    packet = sample_packet()
    for forged in (
        replace(packet, live_trading_enabled=True),
        replace(packet, atomic_capital_book_verified=True),
        replace(packet, real_shadow_trading_started=True),
        replace(packet, broker_orders_transmitted=1),
        replace(packet, verdict="RELEASE_APPROVED"),
    ):
        with pytest.raises(Stage76RiskBlocked):
            review(packets=(forged,))


def test_stage75_wrong_bps_malformed_blockers_and_hash_rejected():
    p = sample_packet()
    for forged in (
        replace(p, option_debit_allocation_bps_rounded_up=100),
        replace(p, maximum_hypothetical_scenario_loss_cents=p.long_option_entry_debit_cents+1),
        replace(p, blockers=()),
        replace(p, research_packet_sha256="not-sha"),
        replace(p, checks=tuple(c for c in p.checks if c.name != "global_fo_risk_capital_gate")),
    ):
        with pytest.raises(Stage76RiskBlocked):
            review(packets=(forged,))


@pytest.mark.parametrize("bad_policy", [
    {"max_single_debit_bps": 5001},
    {"max_portfolio_debit_bps": 0},
    {"max_per_underlying_debit_bps": 5000, "max_portfolio_debit_bps": 4000},
    {"max_research_ideas": True},
    {"max_daily_loss_bps": 5000},
])
def test_invalid_policy_never_silently_weakens_risk(bad_policy):
    with pytest.raises(Stage76RiskBlocked):
        Stage76FOResearchPolicy(**bad_policy)


def test_unbounded_tuple_and_malformed_telemetry_fail_closed():
    with pytest.raises(Stage76RiskBlocked, match="Nonempty"):
        review(packets=())
    invalid = Stage76UntrustedRiskTelemetry(
        account_id="qa-account", daily_realized_loss_bps=True,
        drawdown_bps=0, consecutive_losses=0,
        kill_switch_active=False, risk_engine_healthy=True,
    )
    with pytest.raises(Stage76RiskBlocked, match="telemetry"):
        review(telemetry=invalid)


def test_variable_capital_is_accepted_and_not_hardcoded():
    p = sample_packet(debit=100_000, loss=50_000, capital=1_000_000)
    result = review(packets=(p,))
    assert result.virtual_capital_cents == 1_000_000
    assert result.total_debit_allocation_bps_rounded_up == 1000
    assert result.verdict.endswith("NO_GO")


def test_no_input_cli_no_authority():
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage76_fo_portfolio_risk_smoke.py")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stderr
    report = json.loads(run.stdout)
    assert report["mode"] == "STAGE76_FO_NO_INPUT_RISK_RESEARCH"
    assert report["global_mandatory_fo_risk_veto_enforced"] is False
    assert report["order_submission_authorized"] is False
    assert report["broker_orders_transmitted"] == 0
