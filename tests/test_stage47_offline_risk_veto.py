"""Stage47 adversarial offline Risk & Veto tests. NO REAL MARKET DATA."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from nexus_titan.operations.paper_deployment import (
    PaperDeploymentConfig, open_paper_only_deployment,
)
from nexus_titan.operations.offline_risk_veto import (
    Stage47OfflineRiskVetoEntry, Stage47RiskVetoBlocked,
    Stage47RiskVetoPolicy, SyntheticQuoteEvidence, SyntheticBuyProposal,
    inspect_stage47_risk_veto,
)
from nexus_titan.risk.portfolio_risk import PortfolioRiskConfig

NOW = datetime.fromisoformat("2026-11-03T09:30:00+05:30")


def _deployment(tmp_path, *, enabled=True, capital=50000):
    return open_paper_only_deployment(PaperDeploymentConfig(
        account_id="S47-QA", starting_capital=capital,
        virtual_state_dir=tmp_path / "virtual",
        research_db_path=tmp_path / "research.sqlite3",
        paper_orders_enabled=enabled,
    ), approval_authorizer=lambda actor, resource: actor == "SYNTHETIC_OWNER")


def _quote(**changes):
    return replace(SyntheticQuoteEvidence(
        observed_at=NOW, bid=99.95, ask=100.00,
        displayed_ask_quantity=100, expected_edge_bps=40,
        slippage_bps=3,
    ), **changes)


def _proposal(**changes):
    return replace(SyntheticBuyProposal(
        symbol="TEST", quantity=1, stop_price=95.0,
    ), **changes)


@pytest.mark.parametrize("capital", [12500, 50000, 75000])
def test_fresh_synthetic_only_risk_veto_approved_no_external_authority(tmp_path, capital):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path, capital=capital))
    r = gate.inspect(_proposal(), _quote(), now=NOW)
    assert r.new_synthetic_buy_permitted, r.blockers
    assert r.stage45_ready
    assert r.maximum_authoritative_units >= 1
    assert r.maximum_exact_risk_units >= 1
    assert r.quote_age_seconds == 0
    assert r.observed_spread_bps is not None and 0 < r.observed_spread_bps < 60
    assert r.red_team_veto is False
    assert r.external_quote_authentication is False
    assert r.independent_global_risk_veto_enforced is False
    assert r.independent_human_identity_verified is False
    assert r.cross_ledger_atomicity_verified is False
    assert r.licensed_real_data_verified is False
    assert r.automatic_strategy_promotion_allowed is False
    assert r.broker_orders_transmitted == 0
    assert r.production_ready is False


def test_synthetic_buy_is_pending_and_does_not_fill_or_place_broker_order(tmp_path):
    deployment = _deployment(tmp_path)
    wrapper = Stage47OfflineRiskVetoEntry(deployment)
    start = deployment.virtual_account.cash_balance
    outcome = wrapper.request_buy(_proposal(), _quote(), now=NOW)
    assert outcome.status == "PENDING_APPROVAL"
    assert outcome.requires_manual_approval
    assert outcome.live_orders_transmitted == 0
    assert deployment.virtual_account.cash_balance == start
    assert not any(order.fills for order in deployment.virtual_account.orders.values())
    with pytest.raises(Stage47RiskVetoBlocked, match="Stage45"):
        wrapper.request_buy(_proposal(symbol="OTHER"), _quote(), now=NOW)
    assert len(deployment.virtual_account.orders) == 1


def test_session_disabled_blocks_without_creating_intent(tmp_path):
    deployment = _deployment(tmp_path, enabled=False)
    wrapper = Stage47OfflineRiskVetoEntry(deployment)
    with pytest.raises(Stage47RiskVetoBlocked, match="Stage45"):
        wrapper.request_buy(_proposal(), _quote(), now=NOW)
    assert not deployment.virtual_account.orders


@pytest.mark.parametrize("offset", [-31, 1])
def test_stale_or_future_quote_is_vetoed(tmp_path, offset):
    deployment = _deployment(tmp_path)
    observation = _quote(observed_at=NOW + timedelta(seconds=offset))
    report = Stage47OfflineRiskVetoEntry(deployment).inspect(
        _proposal(), observation, now=NOW,
    )
    assert not report.new_synthetic_buy_permitted
    assert any("future-dated or stale" in b for b in report.blockers)
    assert not deployment.virtual_account.orders


def test_quote_exact_age_boundary_is_inclusive(tmp_path):
    deployment = _deployment(tmp_path)
    quote = _quote(observed_at=NOW-timedelta(seconds=30))
    r = inspect_stage47_risk_veto(deployment, _proposal(), quote, now=NOW)
    assert r.new_synthetic_buy_permitted


@pytest.mark.parametrize("changes", [
    {"bid": 90.0},
    {"bid": 110.0},
    {"ask": float("nan")},
    {"bid": True},
    {"displayed_ask_quantity": 0},
    {"displayed_ask_quantity": True},
    {"displayed_ask_quantity": 0.5},
    {"expected_edge_bps": -5},
    {"expected_edge_bps": float("inf")},
    {"slippage_bps": -1},
    {"slippage_bps": True},
    {"source_reference": "EXCHANGE/NSE"},
    {"source_reference": ""},
    {"realized_daily_loss_pct": float("nan")},
    {"consecutive_losses": True},
    {"current_drawdown_pct": -1},
])
def test_untrusted_quote_abnormalities_fail_closed(tmp_path, changes):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    verdict = gate.inspect(_proposal(), _quote(**changes), now=NOW)
    assert not verdict.new_synthetic_buy_permitted
    with pytest.raises(Stage47RiskVetoBlocked):
        gate.request_buy(_proposal(), _quote(**changes), now=NOW)


def test_naive_or_non_datetime_observations_fail_closed(tmp_path):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    quote = _quote(observed_at=NOW.replace(tzinfo=None))
    assert not gate.inspect(_proposal(), quote, now=NOW).new_synthetic_buy_permitted
    assert not gate.inspect(_proposal(), _quote(), now=NOW.replace(tzinfo=None)).new_synthetic_buy_permitted
    assert not gate.inspect(_proposal(), _quote(), now="not-a-clock").new_synthetic_buy_permitted


def test_red_team_vetoes_edge_below_spread_plus_slippage(tmp_path):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    r = gate.inspect(_proposal(), _quote(expected_edge_bps=3), now=NOW)
    assert r.red_team_veto
    assert any("Red-Team veto" in b for b in r.blockers)
    assert not r.new_synthetic_buy_permitted


def test_spread_threshold_and_slippage_caps_both_enforced(tmp_path):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    spread = gate.inspect(_proposal(), _quote(bid=99), now=NOW)
    assert not spread.new_synthetic_buy_permitted
    assert any("spread" in b.lower() for b in spread.blockers)
    slip = gate.inspect(_proposal(), _quote(slippage_bps=26), now=NOW)
    assert not slip.new_synthetic_buy_permitted
    assert any("slippage" in b.lower() for b in slip.blockers)


def test_depth_and_stop_direction_both_required(tmp_path):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    depth = gate.inspect(_proposal(quantity=3), _quote(displayed_ask_quantity=2), now=NOW)
    assert not depth.new_synthetic_buy_permitted
    assert any("liquidity" in b.lower() for b in depth.blockers)
    stop = gate.inspect(_proposal(stop_price=101), _quote(), now=NOW)
    assert not stop.new_synthetic_buy_permitted


@pytest.mark.parametrize("changes", [
    {"symbol": ""}, {"symbol": None}, {"quantity": True}, {"quantity": -1},
    {"quantity": 0}, {"quantity": 1.5}, {"quantity": 10001},
    {"lot_size": 0}, {"lot_size": True}, {"lot_size": 2},
    {"stop_price": float("inf")}, {"stop_price": -2},
    {"instrument_type": "OPTIONS"}, {"instrument_type": "FUTURES"},
])
def test_invalid_buy_or_unverified_fo_instrument_never_admitted(tmp_path, changes):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    r = gate.inspect(_proposal(**changes), _quote(), now=NOW)
    assert not r.new_synthetic_buy_permitted
    assert not gate._deployment.virtual_account.orders


@pytest.mark.parametrize("changes", [
    {"max_quote_age_seconds": 0}, {"max_quote_age_seconds": False},
    {"max_quote_age_seconds": 200}, {"max_spread_bps": float("nan")},
    {"max_spread_bps": 0}, {"max_slippage_bps": -1},
    {"max_slippage_bps": True}, {"max_lots_per_trade": 0},
    {"max_order_units": 0}, {"max_order_units": 20000},
])
def test_policy_invalid_or_excessively_permissive_rejected(tmp_path, changes):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    policy = replace(Stage47RiskVetoPolicy(), **changes)
    verdict = gate.inspect(_proposal(), _quote(), policy=policy, now=NOW)
    assert not verdict.new_synthetic_buy_permitted


def test_exact_quantity_cap_vetoes_oversize_even_if_authoritative_allows(tmp_path):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    verdict = gate.inspect(_proposal(quantity=21), _quote(), now=NOW)
    assert not verdict.new_synthetic_buy_permitted
    assert any("quantity cap" in b or "Exact synthetic" in b for b in verdict.blockers)


@pytest.mark.parametrize("changes,reason", [
    ({"realized_daily_loss_pct": 3.0}, "Daily loss"),
    ({"consecutive_losses": 3}, "Consecutive loss"),
    ({"current_drawdown_pct": 10.0}, "drawdown"),
])
def test_risk_circuit_breakers_veto_unsafe_synthetic_entry(tmp_path, changes, reason):
    gate = Stage47OfflineRiskVetoEntry(_deployment(tmp_path))
    out = gate.inspect(_proposal(), _quote(**changes), now=NOW)
    assert not out.new_synthetic_buy_permitted
    assert any(reason.lower() in x.lower() for x in out.blockers)


def test_policy_drift_between_config_and_effective_risk_engine_blocks(tmp_path):
    d = _deployment(tmp_path)
    d.virtual_account.risk_engine._portfolio_mgr.config = PortfolioRiskConfig(
        max_risk_per_trade_pct=50, max_portfolio_exposure_pct=90,
    )
    gate = Stage47OfflineRiskVetoEntry(d)
    out = gate.inspect(_proposal(), _quote(), now=NOW)
    assert not out.new_synthetic_buy_permitted
    assert any("policy drift" in b for b in out.blockers)
    assert not d.virtual_account.orders


def test_policy_drift_between_nominal_and_virtual_account_blocks(tmp_path):
    d = _deployment(tmp_path)
    d.virtual_account.risk_engine.config = PortfolioRiskConfig(
        max_risk_per_trade_pct=30, max_portfolio_exposure_pct=90,
    )
    assert not Stage47OfflineRiskVetoEntry(d).inspect(
        _proposal(), _quote(), now=NOW,
    ).new_synthetic_buy_permitted


def test_kill_switch_and_stale_handle_rejected(tmp_path):
    d = _deployment(tmp_path)
    d.virtual_account.activate_emergency_kill_switch("synthetic S47")
    assert not Stage47OfflineRiskVetoEntry(d).inspect(
        _proposal(), _quote(), now=NOW,
    ).new_synthetic_buy_permitted
    assert not Stage47OfflineRiskVetoEntry(_deployment(tmp_path)).inspect(
        _proposal(), _quote(), now=NOW,
    ).new_synthetic_buy_permitted


def test_inspection_has_no_cash_or_order_side_effects(tmp_path):
    d = _deployment(tmp_path)
    gate = Stage47OfflineRiskVetoEntry(d)
    starting_balance = d.virtual_account.cash_balance
    initial_rev = d.virtual_account._snapshot_revision
    a = gate.inspect(_proposal(), _quote(), now=NOW)
    b = gate.inspect(_proposal(), _quote(), now=NOW)
    assert a == b
    assert d.virtual_account._snapshot_revision == initial_rev
    assert d.virtual_account.cash_balance == starting_balance
    assert not d.virtual_account.orders


def test_reject_unknown_wrapper_types(tmp_path):
    with pytest.raises(TypeError):
        Stage47OfflineRiskVetoEntry(object())
    with pytest.raises(TypeError):
        inspect_stage47_risk_veto(object(), _proposal(), _quote(), now=NOW)
