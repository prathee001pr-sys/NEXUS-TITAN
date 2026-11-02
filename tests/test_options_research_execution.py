"""Synthetic offline tests for quote-driven options research execution.

No real NSE data or broker orders are involved.
"""
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_history import (
    ResearchOptionChainHistory, assemble_research_option_chain_history,
)
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, OptionResearchExecutionError, simulate_historical_option_fill,
)
from nexus_titan.virtual.microstructure import MicrostructureConfig
import hashlib


BASE = datetime.fromisoformat("2026-11-02T09:16:00+05:30")


def _contract(**kw):
    props = dict(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1), effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5), strike_step=50.0,
        source_reference="evidence/test-contract", source_verified=True,
    )
    props.update(kw)
    return PointInTimeContractSpec(**props)


def _snapshot(at=BASE):
    stamp = (at - timedelta(seconds=1)).isoformat()
    quotes = tuple(
        OptionChainQuote(
            timestamp=stamp, symbol="NIFTYOPT", underlying="NIFTY",
            expiry_date="2026-11-05", strike=100.0, option_type=typ,
            bid=5.0, ask=5.5, ltp=5.25, volume=1000,
            open_interest=1200, underlying_spot=100.0, lot_size=25,
        ) for typ in ("CE", "PE")
    )
    return ResearchOptionChainSnapshot(
        quotes=quotes, sha256=hashlib.sha256(at.isoformat().encode()).hexdigest(),
        observed_at=at, provider_reference="evidence/test-provider",
        licence_evidence_reference="evidence/test-licence",
        calendar_evidence_reference="evidence/test-calendar",
        contract_evidence_reference="evidence/test-contract",
    )


def _history(*snapshots):
    if not snapshots:
        snapshots = (_snapshot(),)
    return assemble_research_option_chain_history(
        list(snapshots), contract=_contract(),
        calendar=nse_equity_derivatives_baseline(),
    )


def _depth(*, bid=400, ask=400, at=BASE, declared=True):
    return OptionDisplayedDepth(
        as_of=at, bid_quantity=bid, ask_quantity=ask,
        source_reference="evidence/test-top-book",
        source_declared_verified=declared,
    )


def _run(history=None, **overrides):
    params = dict(
        history=_history() if history is None else history,
        contract=_contract(), calendar=nse_equity_derivatives_baseline(),
        observed_at=BASE, strike=100.0, option_type="CE", side="BUY", lots=2,
        depth=_depth(),
    )
    params.update(overrides)
    return simulate_historical_option_fill(**params)


def test_buy_fill_crosses_spread_and_includes_realized_fragment_fees():
    filled = _run()
    assert filled.status == "FILLED"
    assert filled.filled_quantity == 50 and filled.remaining_quantity == 0
    assert filled.execution_price >= 5.5
    assert filled.notional == round(filled.execution_price * 50, 2)
    assert filled.estimated_fees > 0 and filled.fees_breakdown is not None
    assert filled.execution_shortfall_vs_mid >= 0
    assert filled.total_estimated_friction == round(
        filled.execution_shortfall_vs_mid + filled.estimated_fees, 2
    )
    assert filled.live_orders_transmitted == 0
    assert not filled.approved_for_strategy_promotion


def test_sell_fill_uses_bid_and_side_specific_fees():
    sell = _run(side="SELL")
    buy = _run(side="BUY")
    assert sell.status == "FILLED"
    assert sell.execution_price <= 5.0
    assert sell.fees_breakdown.stt > buy.fees_breakdown.stt
    assert sell.execution_shortfall_vs_mid >= 0


def test_depth_capped_partial_fill_lot_integrity_and_fees_only_filled():
    partial = _run(lots=4, depth=_depth(bid=400, ask=200))
    assert partial.status == "PARTIAL"
    assert partial.filled_quantity == 50
    assert partial.remaining_quantity == 50
    assert partial.fees_breakdown is not None
    assert partial.fees_breakdown.total_charges == partial.estimated_fees


def test_liquidity_too_low_rejects_and_charges_nothing():
    item = _run(depth=_depth(ask=50))
    assert item.status == "UNFILLED"
    assert item.filled_quantity == 0 and item.remaining_quantity == 50
    assert item.execution_price is None
    assert item.notional == 0 and item.estimated_fees == 0
    assert item.fees_breakdown is None


def test_zero_displayed_ask_depth_never_uses_csv_daily_volume_as_depth():
    assert _run(depth=_depth(ask=0)).status == "UNFILLED"


def test_wrong_depth_source_declaration_fails_closed():
    with pytest.raises(OptionResearchExecutionError, match="depth declaration"):
        _run(depth=_depth(declared=False))


def test_depth_cannot_be_from_future_or_be_stale():
    with pytest.raises(OptionResearchExecutionError, match="after observation"):
        _run(depth=_depth(at=BASE + timedelta(milliseconds=100)))
    with pytest.raises(OptionResearchExecutionError, match="stale"):
        _run(depth=_depth(at=BASE - timedelta(seconds=4)))


def test_depth_quote_timestamp_mismatch_fails():
    # Configure longer age to exercise depth-vs-quote timestamp check.
    with pytest.raises(OptionResearchExecutionError, match="unsynchronized"):
        _run(depth=_depth(at=BASE - timedelta(seconds=3)),
             microstructure=MicrostructureConfig(max_quote_age_ms=1500.0))


def test_limit_not_marketable_keeps_order_unfilled():
    outcome = _run(order_type="LIMIT", limit_price=4.00)
    assert outcome.status == "UNFILLED"
    assert outcome.estimated_fees == 0


def test_marketable_limit_must_respect_limit_price():
    outcome = _run(order_type="LIMIT", limit_price=5.5)
    assert outcome.status in ("UNFILLED", "PARTIAL", "FILLED")
    if outcome.filled_quantity:
        assert outcome.execution_price <= 5.5


@pytest.mark.parametrize("bad", [
    {"lots": 0}, {"lots": True}, {"lots": 100},
    {"side": "HOLD"}, {"option_type": "PEE"},
    {"strike": 0}, {"strike": float("nan")},
    {"order_type": "STOP"},
    {"order_type": "MARKET", "limit_price": 5.5},
    {"order_type": "LIMIT"},
    {"depth": None}, {"contract": "invalid"},
])
def test_invalid_order_request_is_rejected(bad):
    with pytest.raises((OptionResearchExecutionError, ValueError)):
        _run(**bad)


def test_wrong_contract_metadata_fails_validation():
    with pytest.raises(OptionResearchExecutionError, match="NSE OPTIONS"):
        _run(contract=_contract(segment="FUTURES"))


def test_unverified_contract_does_not_get_simulated_fills():
    with pytest.raises(OptionResearchExecutionError, match="Historical data integrity"):
        _run(contract=_contract(source_verified=False))


def test_missing_strike_or_timestamp_is_not_filled():
    with pytest.raises(OptionResearchExecutionError, match="option leg"):
        _run(strike=200)
    with pytest.raises(OptionResearchExecutionError, match="snapshot"):
        _run(observed_at=BASE + timedelta(minutes=1))


def test_forged_history_cannot_bypass_gap_gate():
    first, last = _snapshot(BASE), _snapshot(BASE + timedelta(minutes=2))
    forged = ResearchOptionChainHistory((first, last), 1, 2)
    with pytest.raises(OptionResearchExecutionError, match="Historical data integrity"):
        _run(history=forged)


def test_forged_history_with_promotion_flag_is_rejected():
    forged = replace(_history(), approved_for_strategy_promotion=True)
    with pytest.raises(OptionResearchExecutionError, match="promotion"):
        _run(history=forged)


def test_forged_history_with_wrong_expected_slots_is_rejected():
    forged = replace(_history(), expected_slots=0)
    with pytest.raises(OptionResearchExecutionError, match="Historical data integrity"):
        _run(history=forged)


def test_missing_depth_source_reference_raises():
    with pytest.raises(ValueError, match="source_reference"):
        OptionDisplayedDepth(
            as_of=BASE, bid_quantity=10, ask_quantity=10,
            source_reference="", source_declared_verified=True,
        )


def test_invalid_depth_quantities_rejected():
    for bad_qty in (-1, True, 0.5):
        with pytest.raises(ValueError, match="bid_quantity"):
            OptionDisplayedDepth(
                as_of=BASE, bid_quantity=bad_qty, ask_quantity=10,
                source_reference="test", source_declared_verified=True,
            )


def test_simulation_config_controls_latency_and_impact_without_live_trades():
    result = _run(
        microstructure=MicrostructureConfig(
            max_participation_rate=0.25, impact_coefficient_bps=40.0,
            arrival_latency_ms=300.0
        )
    )
    assert result.status == "FILLED"
    assert result.live_orders_transmitted == 0


def test_fee_override_is_applied_only_to_filled_quantity():
    baseline = _run()
    cheaper = _run(costs=IndianCostConfig(brokerage_pct=0.0))
    assert cheaper.estimated_fees <= baseline.estimated_fees


def test_price_of_unfilled_request_never_becomes_phantom_pnl():
    unfilled = _run(depth=_depth(ask=0))
    assert unfilled.execution_shortfall_vs_mid == 0
    assert unfilled.total_estimated_friction == 0
