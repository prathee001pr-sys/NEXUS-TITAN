"""Stage60 no-fill out-of-sample futures research regression and adversarial QA.

All NSE-like prices/metadata are FABRICATED. A high hit rate, positive
marker or an option-window match is not a verified strategy, P&L,
order-fill record, licensed data source or live-trading permission.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus_titan.data.historical_fo_catalog import HistoricalCatalogResult
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.ohlcv import OHLCVCandle
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.stage59_futures_history import (
    Stage59FuturesCSVDeclaration, Stage59HistoryBlocked,
    preflight_stage59_futures_csv,
)
from nexus_titan.research.stage60_purged_oos import (
    Stage60ResearchBlocked, Stage60ResearchConfig, inspect_stage60_purged_oos,
)

START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
HEADER = "timestamp,symbol,exchange,segment,expiry_date,lot_size,open,high,low,close,volume,open_interest"


def _contract(underlying="NIFTY", **kw):
    opts = dict(
        symbol=underlying + "FUT", underlying=underlying,
        exchange="NSE", segment="FUTURES", lot_size=25, tick_size=0.05,
        freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_reference="qa/fabricated-point-in-time-contract",
        source_verified=True,
    )
    opts.update(kw)
    return PointInTimeContractSpec(**opts)


def _fixture(root, underlying="NIFTY", *, prices=None, count=46):
    root.mkdir(parents=True, exist_ok=True)
    if prices is None:
        prices = [10000 + (i % 9) * 5 for i in range(count)]
    assert len(prices) == count
    contract = _contract(underlying)
    rows = [HEADER]
    for i, cents in enumerate(prices):
        price = f"{cents // 100}.{cents % 100:02d}"
        when = (START + timedelta(minutes=i)).isoformat()
        rows.append(
            f"{when},{contract.symbol},NSE,FUTURES,2026-11-05,25,"
            f"100.00,105.00,95.00,{price},1000,2000"
        )
    payload = ("\n".join(rows) + "\n").encode("utf-8")
    (root / "futures.csv").write_bytes(payload)
    declaration = Stage59FuturesCSVDeclaration(
        dataset_id="stage60-qa-" + underlying.lower(),
        filename="futures.csv", expected_sha256=hashlib.sha256(payload).hexdigest(),
        provider_reference="qa/synthetic-futures-vendor",
        licence_reference="qa/unverified-licence",
        calendar_reference="qa/unverified-holiday-list",
        contract_reference=contract.source_reference,
        expected_first=START,
        expected_last=START + timedelta(minutes=count - 1),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    calendar = nse_equity_derivatives_baseline()
    history = preflight_stage59_futures_csv(
        root, declaration=declaration, contract=contract, calendar=calendar,
    )
    return history, contract, calendar


def _config(**kw):
    return replace(Stage60ResearchConfig(), **kw)


def _run(root, underlying="NIFTY", *, prices=None, count=46, config=None):
    history, contract, calendar = _fixture(
        root, underlying, prices=prices, count=count,
    )
    report = inspect_stage60_purged_oos(
        history, contract=contract, calendar=calendar,
        config=config or Stage60ResearchConfig(),
    )
    return report, history, contract, calendar


def _not_real(report):
    assert report.implementation_scope == "FIXED_MA_DIRECTIONAL_OOS_NOT_FO_BACKTEST_PNL"
    assert not report.dataset_source_authenticated
    assert not report.licence_authenticated
    assert not report.official_historical_lot_master_authenticated
    assert not report.exchange_calendar_authenticated
    assert not report.options_quotes_cross_instrument_synchronized
    assert not report.executable_depth_verified
    assert not report.margin_and_funding_verified
    assert not report.execution_costs_or_broker_fills_verified
    assert not report.real_fo_backtest_performance_verified
    assert not report.strategy_promotion_authorized
    assert not report.capital_ledger_updated
    assert not report.independent_global_risk_veto_enforced
    assert report.live_orders_transmitted == 0
    assert not report.live_trading_enabled
    assert not report.production_ready
    assert all(f.actual_trades_recorded == f.actual_fills_verified == 0 for f in report.folds)


@pytest.mark.parametrize("underlying", ["NIFTY", "BANKNIFTY"])
def test_multiple_purged_holdouts_with_independent_target_labels(tmp_path, underlying):
    r, h, contract, cal = _run(tmp_path, underlying)
    assert r.underlying == underlying
    assert r.symbol == underlying + "FUT"
    assert r.timeframe == "1m"
    assert r.contract_expiry_date == "2026-11-05"
    assert r.source_file_sha256 == h.file_sha256
    assert len(r.local_evidence_digest) == 64
    assert len(r.folds) == 3
    assert [f.fold_number for f in r.folds] == [1, 2, 3]
    assert r.total_candidate_labels == 21
    assert 0 <= r.total_directional_predictions <= 21
    assert r.total_correct_directions <= r.total_directional_predictions
    assert r.evidence_verdict == "INSUFFICIENT_OUT_OF_SAMPLE_OBSERVATIONS"
    assert not r.evidence_sample_sufficient
    previous_end = None
    for fold in r.folds:
        assert not fold.trained_strategy_parameters
        assert fold.candidate_label_count == 7
        assert fold.training_last_at < fold.embargo_first_at
        assert fold.embargo_first_at <= fold.embargo_last_at
        assert fold.embargo_last_at < fold.holdout_first_at
        assert fold.holdout_first_at <= fold.holdout_last_at
        if previous_end is not None:
            assert fold.training_last_at == previous_end
            assert fold.holdout_first_at > previous_end
        previous_end = fold.holdout_last_at
        assert len(fold.observations) == fold.directional_prediction_count
        assert fold.correct_direction_count == sum(
            o.correct for o in fold.observations
        )
        assert fold.neutral_signal_count + fold.directional_prediction_count == fold.candidate_label_count
        assert fold.hit_rate is None or 0 <= fold.hit_rate <= 1
        for item in fold.observations:
            assert item.origin_in_holdout and item.target_in_same_holdout
            assert fold.holdout_first_at <= item.origin_at < item.target_at <= fold.holdout_last_at
            assert item.target_at - item.origin_at == timedelta(minutes=1)
            assert item.prediction in (-1, 1)
            assert item.actual_next_close_direction in (-1, 0, 1)
            assert item.correct == (item.prediction == item.actual_next_close_direction)
            assert item.orders_or_fills == 0
    _not_real(r)


def test_sample_enough_for_local_description_never_entitles_promotion(tmp_path):
    report, *_ = _run(tmp_path, config=_config(minimum_oos_predictions=1))
    assert report.evidence_sample_sufficient
    assert report.evidence_verdict == "EXPLORATORY_SAMPLE_ONLY"
    _not_real(report)


def test_fixed_trend_data_generates_predictable_directional_signal_accuracy(tmp_path):
    # Rising close series makes fixed trailing MA predict UP; it
    # does not indicate fillable prices, actual returns or profit.
    seq = [10000 + i * 5 for i in range(46)]
    report, *_ = _run(tmp_path, prices=seq)
    assert report.total_directional_predictions == 21
    assert report.total_correct_directions == 21
    assert report.overall_directional_hit_rate == 1
    _not_real(report)


def test_flat_market_does_not_divide_by_zero_or_invent_trades(tmp_path):
    report, *_ = _run(tmp_path, prices=[10000] * 46)
    assert report.total_directional_predictions == 0
    assert report.total_correct_directions == 0
    assert report.overall_directional_hit_rate is None
    assert all(f.neutral_signal_count == 7 and f.hit_rate is None for f in report.folds)
    assert report.evidence_verdict == "INSUFFICIENT_OUT_OF_SAMPLE_OBSERVATIONS"
    _not_real(report)


def test_nonzero_ma_signal_with_flat_future_counts_as_miss(tmp_path):
    # Rising until first OOS origin, then flat. Moving averages retain
    # a long bias while the subsequent labelled move may be zero.
    seq = [10000 + min(i, 14) * 5 for i in range(46)]
    report, *_ = _run(tmp_path, prices=seq)
    assert report.total_flat_market_misses >= 1
    assert report.total_correct_directions <= report.total_directional_predictions - 1
    _not_real(report)


def test_first_fold_independent_of_any_later_future_bars(tmp_path):
    seq = [10000 + (i % 9) * 5 for i in range(46)]
    first, *_ = _run(tmp_path / "initial", prices=seq)
    changed = seq[:]
    changed[24:] = [10200 - (i % 10) * 5 for i in range(24, 46)]
    second, *_ = _run(tmp_path / "changed", prices=changed)
    assert first.folds[0] == second.folds[0]
    assert first.local_evidence_digest != second.local_evidence_digest
    assert first.source_file_sha256 != second.source_file_sha256
    _not_real(second)


def test_holdout_terminal_bar_cannot_label_into_next_embargo_or_fold(tmp_path):
    r, h, *_ = _run(tmp_path)
    first = r.folds[0]
    assert first.observations[-1].target_at <= first.holdout_last_at
    assert all(o.origin_at < first.holdout_last_at for o in first.observations)
    assert all(o.target_at <= first.holdout_last_at for o in first.observations)
    assert first.observations[-1].target_at == first.holdout_last_at


def test_every_observation_uses_earlier_close_only_not_same_label(tmp_path):
    seq = [10000 + i * 5 for i in range(46)]
    a, *_ = _run(tmp_path / "a", prices=seq)
    changed = seq[:]
    # Alter target at first fold's origin+1, without modifying origin.
    changed[15] = 10000 + 15 * 5 - 50
    b, *_ = _run(tmp_path / "b", prices=changed)
    assert a.folds[0].observations[0].prediction == b.folds[0].observations[0].prediction
    assert a.folds[0].observations[0].actual_next_close_direction != b.folds[0].observations[0].actual_next_close_direction


@pytest.mark.parametrize("case", ["wrong_symbol", "wrong_expiry", "wrong_lot", "wrong_source", "false_verified", "options_segment"])
def test_wrong_injected_contract_is_rejected_before_research(tmp_path, case):
    h, c, cal = _fixture(tmp_path)
    opts = {
        "wrong_symbol": {"symbol": "WRONGFUT"},
        "wrong_expiry": {"expiry_date": date(2026, 11, 4)},
        "wrong_lot": {"lot_size": 30},
        "wrong_source": {"source_reference": ""},
        "false_verified": {"source_verified": False},
        "options_segment": {"segment": "OPTIONS"},
    }
    if case == "wrong_source":
        wrong = replace(c, source_verified=False, source_reference="")
    else:
        wrong = replace(c, **opts[case])
    with pytest.raises(Stage60ResearchBlocked):
        inspect_stage60_purged_oos(h, contract=wrong, calendar=cal)


@pytest.mark.parametrize("field,bad", [
    ("initial_train_bars", 0), ("initial_train_bars", True),
    ("holdout_bars", 2), ("embargo_bars", 0), ("embargo_bars", -1),
    ("max_folds", 0), ("max_folds", True),
    ("fast_ma_bars", 0), ("slow_ma_bars", 0),
    ("minimum_oos_predictions", 0), ("minimum_oos_predictions", False),
])
def test_config_invalid_bounded_parameters_fail_closed(field, bad):
    with pytest.raises(Stage60ResearchBlocked):
        replace(Stage60ResearchConfig(), **{field: bad})


def test_zero_or_inverted_ma_window_denied():
    with pytest.raises(Stage60ResearchBlocked):
        Stage60ResearchConfig(fast_ma_bars=5, slow_ma_bars=5)
    with pytest.raises(Stage60ResearchBlocked):
        Stage60ResearchConfig(fast_ma_bars=6, slow_ma_bars=4)
    with pytest.raises(Stage60ResearchBlocked):
        Stage60ResearchConfig(slow_ma_bars=12)


def test_insufficient_candles_or_only_partial_holdout_denied(tmp_path):
    h, c, cal = _fixture(tmp_path, count=20)
    with pytest.raises(Stage60ResearchBlocked, match="too short|inconsistent"):
        inspect_stage60_purged_oos(h, contract=c, calendar=cal)


def test_two_folds_can_be_requested_without_using_remaining_tail(tmp_path):
    r, *_ = _run(tmp_path, config=_config(max_folds=2))
    assert len(r.folds) == 2
    assert r.total_candidate_labels == 14
    assert r.folds[-1].holdout_last_at <= START + timedelta(minutes=31)


def test_tampering_with_preflighted_history_timestamp_fails_closed(tmp_path):
    h, c, cal = _fixture(tmp_path)
    row = replace(h.candles[13], timestamp=h.candles[12].timestamp)
    damaged = replace(h, candles=h.candles[:13] + (row,) + h.candles[14:])
    with pytest.raises(Stage60ResearchBlocked, match="grid"):
        inspect_stage60_purged_oos(damaged, contract=c, calendar=cal)


def test_tampered_count_sha_or_authority_claim_rejected(tmp_path):
    h, c, cal = _fixture(tmp_path)
    variants = (
        replace(h, expected_slots=40),
        replace(h, count=40),
        replace(h, file_sha256="not-a-hash"),
        replace(h, licence_authenticated=True),
        replace(h, source_is_independently_verified_exchange_history=True),
        replace(h, approved_for_strategy_promotion=True),
        replace(h, live_orders_transmitted=1),
        replace(h, production_ready=True),
    )
    for candidate in variants:
        with pytest.raises(Stage60ResearchBlocked):
            inspect_stage60_purged_oos(candidate, contract=c, calendar=cal)


def test_mismatched_candle_vendor_label_fails_before_oos(tmp_path):
    h, c, cal = _fixture(tmp_path)
    forged = replace(h.candles[18], source="qa/other-provider")
    altered = replace(h, candles=h.candles[:18] + (forged,) + h.candles[19:])
    with pytest.raises(Stage60ResearchBlocked, match="grid"):
        inspect_stage60_purged_oos(altered, contract=c, calendar=cal)


def test_holiday_day_no_longer_claims_valid_session(tmp_path):
    h, c, _ = _fixture(tmp_path)
    closed = nse_equity_derivatives_baseline(
        holidays=frozenset({date(2026, 11, 2)}),
    )
    with pytest.raises(Stage60ResearchBlocked, match="session"):
        inspect_stage60_purged_oos(h, contract=c, calendar=closed)


def test_contract_expires_before_futures_window(tmp_path):
    h, c, cal = _fixture(tmp_path)
    with pytest.raises(Stage60ResearchBlocked, match="expiry|contract/session"):
        inspect_stage60_purged_oos(
            h, contract=replace(c, expiry_date=date(2026, 11, 1)),
            calendar=cal,
        )


def test_bad_options_catalog_does_not_become_cross_instrument_proof(tmp_path):
    h, c, cal = _fixture(tmp_path)
    with pytest.raises(Stage60ResearchBlocked, match="Typed"):
        inspect_stage60_purged_oos(h, contract=c, calendar=cal, option_catalog=object())


def _fake_catalog(h, *, underlying="NIFTY", auth=False, first=None, last=None):
    # Deliberately operator-constructed; demonstrates inability to turn
    # strings/flags into independently authenticated option quote data.
    return HistoricalCatalogResult(
        partitions=(SimpleNamespace(preflight=SimpleNamespace(
            underlying=underlying, snapshot_count=4,
        )),),
        dataset_count=1, snapshot_count=4, unique_contracts=1,
        first_observed_at=h.first_observed_at if first is None else first,
        last_observed_at=h.last_observed_at if last is None else last,
        external_source_authenticated=auth,
    )


def test_declared_options_time_window_is_only_metadata_not_joint_backtest(tmp_path):
    h, c, cal = _fixture(tmp_path)
    report = inspect_stage60_purged_oos(
        h, contract=c, calendar=cal, option_catalog=_fake_catalog(h),
    )
    assert report.options_catalog_declared_window_observed
    assert report.related_options_snapshot_count == 4
    assert not report.options_quotes_cross_instrument_synchronized
    assert not report.real_fo_backtest_performance_verified
    _not_real(report)


def test_claimed_external_option_authentication_rejected(tmp_path):
    h, c, cal = _fixture(tmp_path)
    with pytest.raises(Stage60ResearchBlocked, match="claims external authority"):
        inspect_stage60_purged_oos(
            h, contract=c, calendar=cal, option_catalog=_fake_catalog(h, auth=True),
        )


def test_claimed_full_market_options_coverage_rejected(tmp_path):
    h, c, cal = _fixture(tmp_path)
    fake = replace(_fake_catalog(h), full_market_history_coverage_verified=True)
    with pytest.raises(Stage60ResearchBlocked, match="external authority"):
        inspect_stage60_purged_oos(
            h, contract=c, calendar=cal, option_catalog=fake,
        )


def test_missing_partition_preflight_fails_explicitly(tmp_path):
    h, c, cal = _fixture(tmp_path)
    malformed = replace(_fake_catalog(h), partitions=(object(),))
    with pytest.raises(Stage60ResearchBlocked, match="Invalid declared options"):
        inspect_stage60_purged_oos(
            h, contract=c, calendar=cal, option_catalog=malformed,
        )


def test_missing_option_underlying_or_window_rejected(tmp_path):
    h, c, cal = _fixture(tmp_path)
    for candidate in (
        _fake_catalog(h, underlying="BANKNIFTY"),
        _fake_catalog(h, first=h.first_observed_at + timedelta(minutes=1)),
        _fake_catalog(h, last=h.last_observed_at - timedelta(minutes=1)),
    ):
        with pytest.raises(Stage60ResearchBlocked):
            inspect_stage60_purged_oos(
                h, contract=c, calendar=cal, option_catalog=candidate,
            )


def test_fixed_research_remains_pure_deterministic_with_no_db_mutation(tmp_path):
    h, c, cal = _fixture(tmp_path)
    before = (tmp_path / "futures.csv").read_bytes()
    a = inspect_stage60_purged_oos(h, contract=c, calendar=cal)
    b = inspect_stage60_purged_oos(h, contract=c, calendar=cal)
    assert a == b
    assert h.candles == h.candles
    assert before == (tmp_path / "futures.csv").read_bytes()
    assert len(list(tmp_path.glob("*.sqlite*"))) == 0
    _not_real(a)


def test_stage60_smoke_script_no_real_futures_backtest():
    import json
    import subprocess
    import sys
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "run_stage60_purged_oos_smoke.py")],
        capture_output=True, text=True, cwd=root, timeout=40, check=False,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["mode"] == "STAGE60_FIXED_MA_PURGED_OOS_DIRECTIONAL_QA_ONLY"
    assert data["nifty"]["folds"] == 3
    assert data["banknifty"]["folds"] == 3
    assert data["nifty"]["real_fo_backtest_performance_verified"] is False
    assert data["banknifty"]["strategy_promotion_authorized"] is False
    assert data["live_orders_transmitted"] == 0
    assert data["production_ready"] is False
