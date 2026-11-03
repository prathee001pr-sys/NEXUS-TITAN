"""Stage58 multi-snapshot F&O execution stress/reconciliation QA.

All quote/depth, instrument provenance and fees are SYNTHETIC, manually
declared fixtures. No production exchange feed, actual fills, broker or
capital accounting is present or authenticated.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
import math

import pytest

from nexus_titan.cost.charges import IndianCostConfig, calculate_indian_trade_costs
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import MarketCalendar, nse_equity_derivatives_baseline
from nexus_titan.simulation.stage58_execution_stress import (
    Stage58DisplayedObservation, Stage58ExecutionBlocked,
    simulate_stage58_synthetic_execution,
)
from nexus_titan.virtual.microstructure import MicrostructureConfig, OrderBookSnapshot


AT = datetime.fromisoformat("2026-11-02T09:16:00+05:30")
COSTS = IndianCostConfig()
CAL = nse_equity_derivatives_baseline()


def _contract(segment="OPTIONS", **changes):
    params = dict(
        symbol="SYNTHNIFTYOPT" if segment == "OPTIONS" else "SYNTHNIFTYFUT",
        underlying="NIFTY", exchange="NSE", segment=segment,
        lot_size=25, tick_size=0.05,
        freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5), strike_step=50.0,
        source_reference="qa/test-point-in-time-reference",
        source_verified=True,
    )
    params.update(changes)
    return PointInTimeContractSpec(**params)


def _obs(*, event="Q-1", at=AT, bid=5.45, ask=5.50, bid_qty=200,
         ask_qty=200, age_ms=100, declared=True, ref="qa/test-displayed-depth",
         queue_traded_volume=0, symbol="SYNTHNIFTYOPT", tick=0.05,
         halted=False):
    book = OrderBookSnapshot(
        symbol=symbol, timestamp=at.isoformat(),
        bid_price=bid, ask_price=ask, bid_qty=bid_qty, ask_qty=ask_qty,
        last_traded_price=(bid + ask) / 2, quote_age_ms=age_ms,
        tick_size=tick, is_halted=halted,
    )
    return Stage58DisplayedObservation(
        event_id=event, observed_at=at, book=book,
        depth_source_reference=ref,
        depth_source_declared_verified=declared,
        queue_traded_volume=queue_traded_volume,
    )


def _run(observations=None, **changes):
    params = dict(
        observations=(_obs(),) if observations is None else observations,
        contract=_contract(), calendar=CAL,
        side="BUY", requested_lots=2, costs=COSTS,
    )
    params.update(changes)
    return simulate_stage58_synthetic_execution(**params)


def _deny_real_authority(report):
    assert not report.depth_provenance_independently_authenticated
    assert not report.official_contract_master_independently_authenticated
    assert not report.official_fees_or_margin_verified
    assert not report.capital_reserved_in_any_account
    assert not report.broker_fill_reconciliation_verified
    assert not report.external_human_identity_verified
    assert not report.independent_risk_veto_enforced
    assert not report.approved_for_strategy_promotion
    assert not report.live_trading_enabled
    assert report.live_orders_transmitted == 0
    assert not report.production_ready
    assert all(f.live_orders_transmitted == 0 for f in report.fragments)


@pytest.mark.parametrize("segment", ["OPTIONS", "FUTURES"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_synthetic_futures_options_buy_sell_fee_accounting(segment, side):
    spec = _contract(segment)
    report = _run(
        (_obs(symbol=spec.symbol),),
        contract=spec, side=side,
    )
    assert report.segment == segment
    assert report.side == side
    assert report.requested_quantity == 50
    assert report.filled_quantity == 50
    assert report.remaining_quantity == 0
    assert report.status == "FILLED"
    assert report.average_fill_price is not None
    assert report.filled_notional > 0
    assert report.fragment_fees_sum > 0
    assert report.aggregate_fee_estimate > 0
    assert report.conservative_fee_reserve == max(
        report.fragment_fees_sum, report.aggregate_fee_estimate,
    )
    assert report.conservative_execution_friction >= report.conservative_fee_reserve
    assert report.fill_ratio == 1
    assert report.schedule_version == COSTS.version
    assert len(report.fragments) == 1
    f = report.fragments[0]
    assert f.status == "FILLED"
    assert f.filled_quantity == 50
    assert f.fees is not None
    assert f.fees.schedule_version == COSTS.version
    assert f.mid_shortfall >= 0
    _deny_real_authority(report)


def test_option_buy_sell_side_specific_stt():
    buy = _run()
    sell = _run(side="SELL")
    assert buy.fragments[0].fees.stt == 0
    assert sell.fragments[0].fees.stt > buy.fragments[0].fees.stt
    _deny_real_authority(buy)
    _deny_real_authority(sell)


def test_two_snapshots_complete_one_order_no_double_liquidity():
    second = _obs(event="Q-2", at=AT + timedelta(seconds=1))
    report = _run((_obs(), second), requested_lots=4)
    assert report.requested_quantity == 100
    assert report.filled_quantity == 100
    assert report.remaining_quantity == 0
    assert len(report.fragments) == 2
    assert [f.filled_quantity for f in report.fragments] == [50, 50]
    assert report.fragments[0].status == "PARTIAL"
    assert report.fragments[1].status == "FILLED"
    assert report.fragment_fees_sum == round(sum(
        f.fees.total_charges for f in report.fragments
    ), 2)
    assert report.aggregate_fee_estimate == calculate_indian_trade_costs(
        "BUY", report.average_fill_price, 100, "OPTIONS", COSTS,
    ).total_charges
    assert report.conservative_fee_reserve >= report.fragment_fees_sum
    assert report.conservative_fee_reserve >= report.aggregate_fee_estimate
    assert report.conservative_fee_reserve < (
        report.fragment_fees_sum + report.aggregate_fee_estimate
    )
    _deny_real_authority(report)


def test_one_snapshot_partial_fill_respects_lots_and_residual():
    report = _run(requested_lots=4)
    assert report.status == "PARTIAL"
    assert report.filled_quantity == 50
    assert report.remaining_quantity == 50
    assert report.fill_ratio == 0.5
    assert len(report.fragments) == 1
    _deny_real_authority(report)


def test_zero_displayed_ask_depth_no_phantom_fill_or_fees():
    report = _run((_obs(ask_qty=0),))
    assert report.status == "UNFILLED"
    assert report.filled_quantity == 0
    assert report.remaining_quantity == 50
    assert report.average_fill_price is None
    assert report.fragment_fees_sum == 0
    assert report.aggregate_fee_estimate == 0
    assert report.conservative_fee_reserve == 0
    assert report.conservative_execution_friction == 0
    assert report.filled_notional == 0
    assert report.fragments[0].fees is None
    assert report.fragments[0].execution_price is None
    _deny_real_authority(report)


def test_unfilled_first_snapshot_then_second_partial_fill_only_latter_fee():
    records = (
        _obs(ask_qty=0),
        _obs(event="Q-2", at=AT + timedelta(seconds=1)),
    )
    result = _run(records, requested_lots=4)
    assert result.filled_quantity == 50
    assert result.remaining_quantity == 50
    assert result.status == "PARTIAL"
    assert [f.filled_quantity for f in result.fragments] == [0, 50]
    assert result.fragments[0].fees is None
    assert result.fragment_fees_sum == result.fragments[1].fees.total_charges


def test_halted_market_does_not_create_phantom_fill():
    report = _run((_obs(halted=True),))
    assert report.status == "UNFILLED"
    assert report.filled_quantity == 0
    assert report.fragment_fees_sum == 0


def test_resting_limit_without_queue_evidence_not_assumed_filled():
    r = _run(order_type="LIMIT", limit_price=5.45)
    assert r.status == "UNFILLED"
    assert r.filled_quantity == 0
    assert r.fragments[0].fees is None


def test_resting_limit_with_synthetic_queue_evidence_is_lot_aligned():
    r = _run((_obs(queue_traded_volume=200),),
             order_type="LIMIT", limit_price=5.45)
    assert r.status == "FILLED"
    assert r.filled_quantity == 50
    assert r.average_fill_price == 5.45
    assert r.signed_mid_shortfall < 0  # passive price better than mid
    assert r.conservative_execution_friction == r.conservative_fee_reserve
    _deny_real_authority(r)


def test_aggressive_limit_not_marketable_is_unfilled():
    r = _run(order_type="LIMIT", limit_price=5.45)
    assert r.status == "UNFILLED"
    assert r.fragment_fees_sum == 0


def test_market_order_rejects_limit_field():
    with pytest.raises(Stage58ExecutionBlocked, match="MARKET"):
        _run(order_type="MARKET", limit_price=5.5)


@pytest.mark.parametrize("limit", [0, -1, 5.43, 5.501, True, float("nan"), float("inf")])
def test_limit_must_align_with_contract_tick(limit):
    with pytest.raises(Stage58ExecutionBlocked, match="LIMIT price"):
        _run(order_type="LIMIT", limit_price=limit)


def test_market_impact_stress_reduces_fill_or_increases_frictions():
    baseline = _run()
    stress = _run(
        microstructure=MicrostructureConfig(
            max_participation_rate=0.10,
            impact_coefficient_bps=200.0, arrival_latency_ms=500.0,
        ),
    )
    assert stress.filled_quantity <= baseline.filled_quantity
    assert stress.filled_quantity >= 0
    # Cannot infer net profits from comparison when stressed scenario
    # fills fewer lots. The comparison is only an execution sensitivity.
    assert stress.live_orders_transmitted == 0
    assert not stress.production_ready


def test_impact_pushed_limit_price_prevents_fill():
    r = _run(
        order_type="LIMIT", limit_price=5.50,
        microstructure=MicrostructureConfig(
            impact_coefficient_bps=500, arrival_latency_ms=200,
        ),
    )
    assert r.status == "UNFILLED"
    assert r.filled_quantity == 0
    assert r.fragment_fees_sum == 0


@pytest.mark.parametrize("changes,reason", [
    ({"declared": False}, "displayed-depth source"),
    ({"ref": " "}, "displayed-depth source"),
    ({"symbol": "DIFFERENT"}, "symbol/tick mismatch"),
    ({"tick": 0.10}, "symbol/tick mismatch"),
    ({"age_ms": 2500}, "Stale"),
    ({"bid": 5.10, "ask": 5.50}, "spread"),
])
def test_bad_depth_source_contract_or_quote_vetoes_whole_scenario(changes, reason):
    with pytest.raises(Stage58ExecutionBlocked, match=reason):
        _run((_obs(**changes),))


def test_future_or_mismatched_timestamp_rejected_even_if_book_is_fresh():
    o = _obs()
    altered = replace(o, observed_at=AT + timedelta(microseconds=1))
    with pytest.raises(Stage58ExecutionBlocked, match="clock"):
        _run((altered,))


def test_repeated_event_id_rejected_even_at_different_times():
    with pytest.raises(Stage58ExecutionBlocked, match="repeated"):
        _run((_obs(), _obs(at=AT + timedelta(seconds=1))))


def test_reversed_order_rejected_even_with_distinct_ids():
    with pytest.raises(Stage58ExecutionBlocked, match="strictly"):
        _run((_obs(event="Q-2", at=AT + timedelta(seconds=1)), _obs()))


def test_two_same_timestamp_records_rejected():
    with pytest.raises(Stage58ExecutionBlocked, match="strictly"):
        _run((_obs(), _obs(event="Q-2")))


def test_off_session_evening_quote_cannot_fill():
    with pytest.raises(Stage58ExecutionBlocked, match="outside"):
        _run((_obs(at=datetime.fromisoformat("2026-11-02T17:00:00+05:30")),))


def test_calendar_holiday_prevents_simulation():
    closed = nse_equity_derivatives_baseline(holidays=frozenset({date(2026, 11, 2)}))
    with pytest.raises(Stage58ExecutionBlocked, match="outside"):
        _run(calendar=closed)


def test_contract_expired_or_outside_effective_window_vetoes():
    for contract in (
        _contract(expiry_date=date(2026, 11, 1)),
        _contract(effective_from=date(2026, 11, 3)),
        _contract(effective_to=date(2026, 11, 1)),
    ):
        with pytest.raises(Stage58ExecutionBlocked, match="contract/expiry"):
            _run(contract=contract)


def test_contract_unverified_or_non_nse_vetoes():
    with pytest.raises(Stage58ExecutionBlocked, match="contract metadata"):
        _run(contract=_contract(source_verified=False))
    with pytest.raises(Stage58ExecutionBlocked, match="contract metadata"):
        _run(contract=_contract(exchange="BSE"))
    with pytest.raises(Stage58ExecutionBlocked, match="contract metadata"):
        _run(contract=_contract(segment="INDEX"))


@pytest.mark.parametrize("lots", [0, -1, True, 11, 100, 2.5])
def test_futures_options_lot_order_limits_veto(lots):
    with pytest.raises(Stage58ExecutionBlocked, match="lots"):
        _run(requested_lots=lots)


def test_contract_freeze_quantity_blocks_oversized_lots():
    with pytest.raises(Stage58ExecutionBlocked, match="freeze"):
        _run(requested_lots=2, contract=_contract(freeze_quantity=25))


def test_cost_schedule_must_be_explicit_and_not_future_dated():
    with pytest.raises(Stage58ExecutionBlocked, match="cost schedule"):
        _run(costs=None)
    with pytest.raises(Stage58ExecutionBlocked, match="Future fee"):
        _run(costs=replace(COSTS, effective_date="2026-12-01"))


def test_cost_schedule_edition_is_returned_and_changes_fees():
    variant = replace(COSTS, version="QA-EXPLICIT-DISCOUNT",
                      brokerage_pct=0.01)
    baseline = _run()
    change = _run(costs=variant)
    assert change.schedule_version == variant.version
    assert change.fragment_fees_sum < baseline.fragment_fees_sum
    assert change.filled_quantity == baseline.filled_quantity
    _deny_real_authority(change)


def test_snapshot_count_is_bounded_and_nonempty():
    with pytest.raises(Stage58ExecutionBlocked, match="Nonempty"):
        _run(())
    with pytest.raises(Stage58ExecutionBlocked, match="Nonempty"):
        _run([_obs()])
    with pytest.raises(Stage58ExecutionBlocked, match="Nonempty"):
        _run(tuple(_obs(event=f"Q-{i}", at=AT + timedelta(seconds=i))
                   for i in range(41)))


def test_invalid_config_boolean_cap_fails():
    with pytest.raises(Stage58ExecutionBlocked, match="cap"):
        _run(max_spread_bps=True)
    with pytest.raises(Stage58ExecutionBlocked, match="cap"):
        _run(max_observations=False)


def test_scenario_is_deterministic_pure_and_does_not_mutate_history():
    records = (_obs(), _obs(event="Q-2", at=AT + timedelta(seconds=1)))
    before = tuple(records)
    a = _run(records, requested_lots=4)
    b = _run(records, requested_lots=4)
    assert a == b
    assert records == before
    assert all(x.fees is not None for x in a.fragments)
    _deny_real_authority(a)


def test_future_period_cost_schedule_rejected_when_no_fills_too():
    with pytest.raises(Stage58ExecutionBlocked, match="Future fee"):
        _run((_obs(ask_qty=0),), costs=replace(COSTS, effective_date="2027-01-01"))


def test_stage58_offline_script_smoke_only_research():
    import json
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage58_execution_stress_smoke.py")],
        cwd=root, capture_output=True, text=True, timeout=35, check=False,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["mode"] == "STAGE58_LOCAL_FO_EXECUTION_STRESS_ONLY"
    assert data["baseline"]["status"] == "FILLED"
    assert data["baseline"]["filled_quantity"] == 100
    assert data["baseline"]["fragment_fees_sum"] > 0
    assert data["stress"]["filled_quantity"] <= 100
    assert data["unfilled"]["filled_quantity"] == 0
    assert data["unfilled"]["conservative_fee_reserve"] == 0
    assert data["baseline"]["live_orders_transmitted"] == 0
    assert data["baseline"]["depth_provenance_independently_authenticated"] is False
    assert data["baseline"]["production_ready"] is False
