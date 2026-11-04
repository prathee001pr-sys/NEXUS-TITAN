"""Stage74 F&O digital-twin scenario tests; all prices and cases fabricated."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.derivatives.options_engine import calculate_option_greeks
from nexus_titan.derivatives.stage72_expiry_iv_research import (
    Stage72OptionResearchRow, Stage72OptionsResearchReport, _price,
)
from nexus_titan.simulation.stage74_fo_options_scenario_lab import (
    STAGE74_CASES, Stage74ScenarioBlocked, Stage74StressCase,
    simulate_stage74_long_option_scenarios,
)

ROOT = Path(__file__).resolve().parents[1]
IST = ZoneInfo("Asia/Kolkata")
AT = datetime(2026, 11, 2, 9, 16, tzinfo=IST)
CUTOFF = datetime(2026, 11, 5, 15, 30, tzinfo=IST)
SHA = hashlib.sha256(b"stage74-fabricated-only").hexdigest()


def fixture(underlying="NIFTY", option_type="CE", *, time=AT):
    contract = PointInTimeContractSpec(
        symbol=underlying+"OPT", underlying=underlying, exchange="NSE",
        segment="OPTIONS", lot_size=25, tick_size=.05, freeze_quantity=1000,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5), expiry_date=date(2026, 11, 5),
        source_reference="synthetic/contract-claim-not-verified",
        source_verified=True, max_lots_per_trade=10,
    )
    days = (CUTOFF-time).total_seconds()/86400
    fair = _price(24000, 24000, days/365, .20, .06, 0, option_type)
    mid = round(round(fair/.05)*.05, 2)
    greeks = calculate_option_greeks(24000, 24000, days, .20,
                                     risk_free_rate=.06, option_type=option_type)
    row = Stage72OptionResearchRow(
        strike=24000., option_type=option_type,
        bid=round(mid-1, 2), ask=round(mid+1, 2),
        midpoint=mid, spread_bps=round(20000/mid, 4),
        iv_bid=.195, iv_mid=.20, iv_ask=.205,
        model_greeks_at_mid=greeks,
    )
    report = Stage72OptionsResearchReport(
        underlying=underlying, symbol=contract.symbol,
        observation_time=time, declared_expiry_cutoff=CUTOFF,
        time_to_expiry_days=days,
        source_option_sha256=SHA,
        source_alignment_sha256=SHA,
        risk_free_rate_assumption=.06, dividend_yield_assumption=0,
        rows=(row,), research_output_sha256=SHA,
    )
    return report, contract


def analyse(case, **kwargs):
    report, contract = case
    return simulate_stage74_long_option_scenarios(
        report=report, contract=contract,
        reference_spot=24000, strike=24000, option_type=report.rows[0].option_type,
        lots=1, **kwargs,
    )


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
@pytest.mark.parametrize("side", ["CE", "PE"])
def test_default_synthetic_stress_cases_are_bounded_and_non_authoritative(underlying, side):
    report = analyse(fixture(underlying, side))
    assert len(report.outcomes) == len(STAGE74_CASES) == 4
    assert len(report.scenario_digest_sha256) == 64
    assert report.source_stage71_sha256 == SHA
    assert report == analyse(fixture(underlying, side))
    for item in report.outcomes:
        assert item.quantity == 25
        assert item.hypothetical_entry_debit_rupees > 0
        assert item.hypothetical_premium_at_risk_rupees == item.hypothetical_entry_debit_rupees
        assert item.hypothetical_exit_price_after_friction >= 0
        assert item.independently_verified_depth_or_fill is False
        assert item.scenario_is_a_historical_backtest is False
        assert item.hypothetical_round_trip_net_rupees == pytest.approx(
            round(item.hypothetical_exit_proceeds_rupees-item.hypothetical_entry_debit_rupees, 2),
            abs=.01,
        )
    for field in (
        "real_exchange_data_authenticated", "official_cost_tariff_authenticated",
        "actual_market_depth_verified", "live_or_historical_fills_verified",
        "portfolio_margin_verified", "calibrated_stress_probabilities_verified",
        "actual_profitability_verified", "strategy_promotion_authorized",
        "paper_order_authorized", "live_trading_enabled",
    ):
        assert getattr(report, field) is False
    assert report.broker_orders_transmitted == 0
    assert "NO_GO" in report.verdict


def isolated(name, spot_move=0, iv_shift=0, time_minutes=0,
             spread=1, slip=0, haircut=0):
    return (Stage74StressCase(name, spot_move, iv_shift,
                              time_minutes, spread, slip, haircut),)


def test_upside_shock_increases_call_model_and_reduces_put_model():
    call = analyse(fixture(option_type="CE"), scenarios=isolated("UP", spot_move=3))
    put = analyse(fixture(option_type="PE"), scenarios=isolated("UP", spot_move=3))
    assert call.outcomes[0].model_value_change_rupees > 0
    assert put.outcomes[0].model_value_change_rupees < 0


def test_iv_increase_increases_model_value_and_time_decay_reduces_it():
    base = analyse(fixture(), scenarios=isolated("BASE"))
    iv_up = analyse(fixture(), scenarios=isolated("IV_UP", iv_shift=10))
    theta = analyse(fixture(), scenarios=isolated("THETA", time_minutes=120))
    assert iv_up.outcomes[0].model_price_per_unit > base.outcomes[0].model_price_per_unit
    assert theta.outcomes[0].model_price_per_unit < base.outcomes[0].model_price_per_unit


def test_liquidity_haircut_is_worse_but_never_a_fill_claim():
    calm = analyse(fixture(), scenarios=isolated("CALM"))
    panic = analyse(fixture(), scenarios=isolated(
        "PANIC", spread=5, slip=250, haircut=9500,
    ))
    assert panic.outcomes[0].hypothetical_round_trip_net_rupees < (
        calm.outcomes[0].hypothetical_round_trip_net_rupees
    )
    assert not panic.outcomes[0].independently_verified_depth_or_fill


def test_indicative_charges_are_applied_and_versioned():
    result = analyse(fixture(), scenarios=isolated("FLAT"))
    item = result.outcomes[0]
    assert item.indicative_entry_charges_rupees >= 0
    assert item.indicative_exit_charges_rupees >= 0
    assert result.indicative_cost_schedule == IndianCostConfig().version
    assert item.hypothetical_entry_debit_rupees > fixture()[0].rows[0].ask*25


def test_no_partial_output_when_later_scenario_invalid():
    good = Stage74StressCase("OK", 0, 0, 0, 1, 0, 0)
    bad = Stage74StressCase("BAD", 0, 0, 0, 1, 501, 0)
    with pytest.raises(Stage74ScenarioBlocked, match="Invalid scenario"):
        analyse(fixture(), scenarios=(good, bad))


def test_near_expiry_is_rejected_instead_of_claiming_accurate_gamma():
    near = CUTOFF - timedelta(minutes=70)
    good = fixture(time=near)
    with pytest.raises(Stage74ScenarioBlocked, match="Too close to expiry"):
        analyse(good, scenarios=isolated("LATE", time_minutes=20))


def test_cross_session_stress_refused():
    with pytest.raises(Stage74ScenarioBlocked, match="Cross-session"):
        analyse(fixture(), scenarios=isolated("OVERNIGHT", time_minutes=1440))


@pytest.mark.parametrize("bad", [
    Stage74StressCase("BAD", 21, 0, 0, 1, 0, 0),
    Stage74StressCase("BAD", 0, -41, 0, 1, 0, 0),
    Stage74StressCase("BAD", 0, 0, -1, 1, 0, 0),
    Stage74StressCase("BAD", 0, 0, 0, .5, 0, 0),
    Stage74StressCase("BAD", 0, 0, 0, 1, -1, 0),
    Stage74StressCase("BAD", 0, 0, 0, 1, 0, 10001),
])
def test_out_of_bound_scenario_parameters_rejected(bad):
    with pytest.raises(Stage74ScenarioBlocked):
        analyse(fixture(), scenarios=(bad,))


def test_duplicate_case_name_rejected():
    case = Stage74StressCase("REPEAT", 0, 0, 0, 1, 0, 0)
    with pytest.raises(Stage74ScenarioBlocked, match="duplicate"):
        analyse(fixture(), scenarios=(case, case))


def test_unauthenticated_operator_claims_do_not_become_authority():
    report, contract = fixture()
    for fake in (
        replace(report, live_trading_enabled=True),
        replace(report, strategy_promotion_authorized=True),
        replace(report, real_market_depth_verified=True) if hasattr(report, "real_market_depth_verified") else replace(report, tradeable_bid_ask_depth_verified=True),
        replace(report, source_alignment_sha256="bad"),
    ):
        with pytest.raises(Stage74ScenarioBlocked):
            analyse((fake, contract))


def test_wrong_underlying_contract_or_spot_is_rejected():
    report, contract = fixture()
    with pytest.raises(Stage74ScenarioBlocked, match="identity"):
        analyse((report, replace(contract, underlying="BANKNIFTY")))
    with pytest.raises(Stage74ScenarioBlocked, match="reproduce"):
        simulate_stage74_long_option_scenarios(
            report=report, contract=contract, reference_spot=23000,
            strike=24000, option_type="CE", lots=1,
        )


def test_unmatched_strike_or_short_option_not_supported():
    report, contract = fixture()
    with pytest.raises(Stage74ScenarioBlocked, match="eligible option row"):
        simulate_stage74_long_option_scenarios(
            report=report, contract=contract, reference_spot=24000,
            strike=24100, option_type="CE", lots=1,
        )
    with pytest.raises(Stage74ScenarioBlocked, match="Only bounded long"):
        simulate_stage74_long_option_scenarios(
            report=report, contract=contract, reference_spot=24000,
            strike=24000, option_type="SHORT_CE", lots=1,
        )


def test_invalid_lots_costs_and_spread_fail_closed():
    for lots in (True, 0, 11):
        report, contract = fixture()
        with pytest.raises(Stage74ScenarioBlocked, match="lots|long CE/PE"):
            simulate_stage74_long_option_scenarios(
                report=report, contract=contract, reference_spot=24000,
                strike=24000, option_type="CE", lots=lots,
            )
    report, contract = fixture()
    bad_costs = replace(IndianCostConfig(), stt_options_sell_pct=float("nan"))
    with pytest.raises(Stage74ScenarioBlocked, match="tariff"):
        analyse((report, contract), costs=bad_costs)
    crossed = replace(report.rows[0], bid=report.rows[0].ask+1)
    with pytest.raises(Stage74ScenarioBlocked, match="bid/ask"):
        analyse((replace(report, rows=(crossed,)), contract))


def test_no_input_cli_reports_no_go_and_no_orders():
    run = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_stage74_fo_scenario_smoke.py")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stderr
    packet = json.loads(run.stdout)
    assert packet["mode"] == "STAGE74_NO_MARKET_INPUT_SCENARIO_QA"
    assert packet["live_trading_enabled"] is False
    assert packet["actual_fills_recorded"] == 0
    assert packet["broker_orders_transmitted"] == 0
    assert packet["verdict"].endswith("NO_GO")
