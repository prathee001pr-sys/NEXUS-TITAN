"""Regression tests for Phase 7 safety, provenance and execution hardening."""
from __future__ import annotations

import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from nexus_titan.cost.charges import IndianCostConfig, calculate_indian_trade_costs
from nexus_titan.core.security_gates import (
    CryptographicApprovalVerifier,
    evaluate_g0_to_g9_quality_gates,
)
from nexus_titan.data.canonical import load_canonical_data
from nexus_titan.data.instrument_master import PointInTimeInstrumentMaster
from nexus_titan.data.provenance import DatasetManifest, verify_dataset_manifest
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote, inspect_option_chain_snapshot
from nexus_titan.research.backtest import run_backtest
from nexus_titan.virtual.microstructure import (
    MicrostructureSimulator, OrderBookSnapshot, ShadowPaperRunner,
)


def _book(**overrides):
    values = dict(
        symbol="TCS", timestamp="2026-11-01T10:00:00+05:30",
        bid_price=99.95, ask_price=100.00, bid_qty=400, ask_qty=400,
        last_traded_price=99.98, quote_age_ms=10.0,
    )
    values.update(overrides)
    return OrderBookSnapshot(**values)


def test_approval_replay_is_blocked_across_verifier_instances_and_restart():
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "approval.sqlite3"
        signer = CryptographicApprovalVerifier("a-strong-test-secret-key-12345", db_path=db)
        token = signer.issue_token(
            token_id="ONE-SHOT-1001", actor="owner", role="RISK_OWNER",
            target_entity_id="ORDER-1", snapshot_hash="sha256:abc", ttl_seconds=300,
            now_epoch=1_700_000_000,
        )
        assert signer.verify_and_consume(
            token, expected_target_id="ORDER-1", expected_snapshot_hash="sha256:abc",
            now_epoch=1_700_000_010,
        )
        # Simulate a new process/verifier opening the same durable database.
        restarted = CryptographicApprovalVerifier("a-strong-test-secret-key-12345", db_path=db)
        with pytest.raises(PermissionError, match="replay"):
            restarted.verify_and_consume(
                token, expected_target_id="ORDER-1", expected_snapshot_hash="sha256:abc",
                now_epoch=1_700_000_020,
            )


def test_approval_rejects_future_issued_and_expired_tokens():
    with tempfile.TemporaryDirectory() as td:
        verifier = CryptographicApprovalVerifier("a-strong-test-secret-key-12345", db_path=Path(td)/"a.db")
        token = verifier.issue_token(
            token_id="FUTURE-1", actor="owner", role="RISK_OWNER", target_entity_id="X",
            snapshot_hash="Y", ttl_seconds=30, now_epoch=2_000,
        )
        with pytest.raises(PermissionError, match="not yet valid"):
            verifier.verify_and_consume(token, expected_target_id="X", expected_snapshot_hash="Y", now_epoch=1_999)
        with pytest.raises(PermissionError, match="expired"):
            verifier.verify_and_consume(token, expected_target_id="X", expected_snapshot_hash="Y", now_epoch=2_031)


def test_naive_csv_timestamps_use_declared_india_timezone():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "local.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            "2026-10-26T09:15:00,100,101,99,100.5,1000\n",
            encoding="utf-8",
        )
        candles, report = load_canonical_data(path, interval="1m", source_timezone="Asia/Kolkata")
        assert report.is_valid
        assert candles[0].timestamp == "2026-10-26T03:45:00+00:00"


def test_unknown_source_timezone_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "local.csv"
        path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
        candles, report = load_canonical_data(path, source_timezone="Not/A_Timezone")
        assert not report.is_valid
        assert not candles
        assert any("Unknown source timezone" in item for item in report.errors)


def test_unknown_derivative_lot_size_raises_instead_of_defaulting_to_one():
    master = PointInTimeInstrumentMaster()
    with pytest.raises(KeyError, match="No point-in-time contract spec"):
        master.resolve_lot_size("UNKNOWN_FUT", date(2026, 11, 1))


def test_provenance_requires_full_sha256_and_exact_file_match():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bars.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            + "\n".join(f"2026-10-{i:02d}T09:15:00+05:30,100,101,99,100,1000" for i in range(1, 32))
            + "\n", encoding="utf-8",
        )
        import hashlib
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match="exactly 64"):
            DatasetManifest(
                dataset_id="prefix", file_path=str(path), sha256_checksum=digest[:16],
                vendor_name="Vendor", licence_id="LIC-1", instrument_symbol="NIFTY",
                venue="NSE", interval="1d", timezone_name="Asia/Kolkata",
                start_timestamp="", end_timestamp="", bar_count=31,
                dataset_class="LICENSED_EXCHANGE_HISTORY",
            )


def test_unverified_research_dataset_never_passes_provenance_gate():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "bars.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            + "\n".join(f"2026-10-{i:02d}T09:15:00+05:30,100,101,99,100,1000" for i in range(1, 32))
            + "\n", encoding="utf-8",
        )
        import hashlib
        from nexus_titan.data.provenance import build_manifest_from_csv
        manifest = build_manifest_from_csv(
            path, dataset_id="unverified", vendor_name="Research source", licence_id="UNKNOWN",
            dataset_class="UNVERIFIED_RESEARCH_SAMPLE", timezone_name="Asia/Kolkata",
        )
        ok, issues = verify_dataset_manifest(manifest, path)
        assert not ok
        assert any("not licensed exchange history" in item for item in issues)


def test_microstructure_rejects_invalid_side_order_type_and_bad_limits():
    sim = MicrostructureSimulator()
    for side in ("HOLD", "BUY_TO_COVER", ""):
        with pytest.raises(ValueError, match="side"):
            sim.evaluate_order_against_book(
                side=side, order_type="MARKET", requested_qty=1, lot_size=1, book=_book()
            )
    with pytest.raises(ValueError, match="order_type"):
        sim.evaluate_order_against_book(
            side="BUY", order_type="STOP", requested_qty=1, lot_size=1, book=_book()
        )
    with pytest.raises(ValueError, match="tick size"):
        sim.evaluate_order_against_book(
            side="BUY", order_type="LIMIT", requested_qty=1, lot_size=1,
            book=_book(), limit_price=99.98,
        )


def test_order_book_and_microstructure_config_reject_non_finite_values():
    with pytest.raises(ValueError, match="finite"):
        _book(ask_price=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        _book(quote_age_ms=float("inf"))
    with pytest.raises(ValueError, match="finite"):
        from nexus_titan.virtual.microstructure import MicrostructureConfig
        MicrostructureConfig(impact_coefficient_bps=float("nan"))


def test_illiquid_option_chain_is_not_valid_execution_evidence():
    quote = OptionChainQuote(
        timestamp="2026-11-01T10:00:00+05:30", symbol="NIFTY26NOV22000CE",
        underlying="NIFTY", expiry_date="2026-11-05", strike=22000.0,
        option_type="CE", bid=100.0, ask=130.0, ltp=115.0, volume=100,
        open_interest=0, underlying_spot=22010.0, lot_size=25,
    )
    result = inspect_option_chain_snapshot([quote], max_spread_pct=10.0)
    assert not result.is_valid
    assert result.wide_spread_quotes == 1
    assert result.zero_oi_quotes == 1
    assert len(result.errors) >= 2


def test_shadow_runner_persists_account_across_runner_restart():
    with tempfile.TemporaryDirectory() as td:
        first = ShadowPaperRunner(starting_capital=50_000, account_id="PERSIST-TEST", state_dir=td)
        order, outcome = first.route_shadow_order(
            book=_book(ask_price=100.0, bid_price=99.95, ask_qty=400),
            side="BUY", quantity=10, stop_price=95.0, target_price=110.0,
        )
        assert outcome.accepted_for_fill
        assert order.filled_qty == 10
        second = ShadowPaperRunner(starting_capital=50_000, account_id="PERSIST-TEST", state_dir=td)
        assert second.account.positions["TCS"].quantity == 10
        assert order.order_id in second.account.orders


def test_quality_gates_do_not_trust_fabricated_test_count_or_assume_safety_passed():
    report = evaluate_g0_to_g9_quality_gates(
        tests_passed=315, tests_total=0, test_run_success=False, test_run_attempted=False,
        golden_accounting_reconciled=True, shadow_50k_reconciled=True,
    )
    statuses = {item["gate_id"]: item["status"] for item in report["gates"]}
    assert statuses["G0"] == "EXTERNAL_INPUT_REQUIRED"
    assert statuses["G4"] == "FAILED"
    assert statuses["G6"] == "EXTERNAL_INPUT_REQUIRED"
    assert statuses["G9"] == "EXTERNAL_INPUT_REQUIRED"
    assert report["code_verified_gates"] == 0


def test_backtest_rejects_fractional_contract_quantity_and_bad_ohlc():
    good = [
        {"timestamp": "2026-10-01", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10.0},
        {"timestamp": "2026-10-02", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 12.0},
    ]
    with pytest.raises(ValueError, match="whole number"):
        run_backtest(good, quantity=1.5)
    invalid = [dict(item) for item in good]
    invalid[1]["high"] = 99.0
    with pytest.raises(ValueError, match="impossible OHLC"):
        run_backtest(invalid)


def test_backtest_rejects_duplicate_timestamps_and_invalid_signal():
    candles = [
        {"timestamp": "2026-10-01", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10.0},
        {"timestamp": "2026-10-01", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 12.0},
    ]
    with pytest.raises(ValueError, match="increasing"):
        run_backtest(candles)
    candles[1]["timestamp"] = "2026-10-02"
    with pytest.raises(ValueError, match="exactly -1, 0, or 1"):
        run_backtest(candles, signal=lambda index, rows: 0.5)


def test_intraday_backtest_closes_positions_at_session_boundary():
    candles = [
        {"timestamp": "2026-10-01T15:28:00+05:30", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000.0},
        {"timestamp": "2026-10-01T15:29:00+05:30", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 1000.0},
        {"timestamp": "2026-10-02T09:15:00+05:30", "open": 103.0, "high": 104.0, "low": 102.0, "close": 103.5, "volume": 1000.0},
    ]
    result = run_backtest(
        candles, instrument_type="EQUITY_INTRADAY",
        signal=lambda index, rows: 1 if index == 0 else 0,
    )
    assert result.total_trades == 1
    assert result.trade_log[0]["exit_reason"] == "INTRADAY_SESSION_END"


def test_short_options_backtest_fails_closed_without_span_elm_model():
    candles = [
        {"timestamp": "2026-10-01", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10.0},
        {"timestamp": "2026-10-02", "open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 12.0},
    ]
    with pytest.raises(ValueError, match="SPAN/ELM"):
        run_backtest(candles, instrument_type="OPTIONS", allow_short=True)


def test_transaction_costs_reject_fractional_units_and_bad_config():
    with pytest.raises(ValueError, match="whole integer"):
        calculate_indian_trade_costs("BUY", 100.0, 1.5, "FUTURES")
    with pytest.raises(ValueError, match="whole integer"):
        calculate_indian_trade_costs("BUY", 100.0, True, "FUTURES")
    with pytest.raises(ValueError, match="finite non-negative"):
        calculate_indian_trade_costs("BUY", 100.0, 1, "FUTURES", IndianCostConfig(brokerage_pct=-1.0))

def test_transaction_cost_total_equals_rounded_component_sum():
    result = calculate_indian_trade_costs("SELL", 1234.56, 75, "FUTURES")
    component_sum = round(
        result.brokerage + result.stt + result.exchange_charges
        + result.sebi_charges + result.stamp_duty + result.gst, 2
    )
    assert result.total_charges == component_sum


def test_futures_and_index_option_accounting_match_hand_calculated_goldens():
    """Check indicative model arithmetic; not a broker/exchange rate certification."""
    from nexus_titan.cost.charges import calculate_indian_trade_costs
    from nexus_titan.derivatives.chain_and_settlement import (
        estimate_span_elm_margin, settle_option_at_expiry,
    )

    margin = estimate_span_elm_margin(
        underlying_spot=20_000.0, quantity=25, instrument_type="FUTURES",
        span_pct=12.0, elm_pct=3.0,
    )
    assert (margin.notional_value, margin.span_margin, margin.exposure_margin,
            margin.total_margin_blocked) == (500_000.0, 60_000.0, 15_000.0, 75_000.0)

    buy = calculate_indian_trade_costs("BUY", 20_000.0, 25, "FUTURES")
    assert (buy.brokerage, buy.stt, buy.exchange_charges, buy.sebi_charges,
            buy.stamp_duty, buy.gst, buy.total_charges) == (
                20.0, 0.0, 9.15, 0.50, 10.0, 5.34, 44.99)
    sell = calculate_indian_trade_costs("SELL", 20_000.0, 25, "FUTURES")
    assert (sell.brokerage, sell.stt, sell.exchange_charges, sell.sebi_charges,
            sell.stamp_duty, sell.gst, sell.total_charges) == (
                20.0, 250.0, 9.15, 0.50, 0.0, 5.34, 284.99)

    option = settle_option_at_expiry(
        symbol="NIFTY26NOV20000CE", option_type="CE", side="LONG",
        settlement_spot=20_100.0, strike=20_000.0, quantity=25,
        entry_premium=80.0, is_index_option=True,
    )
    assert option.is_in_the_money and option.exercised
    assert option.intrinsic_payoff_per_unit == 100.0
    assert option.gross_pnl == 500.0
    assert option.exercise_stt == 3.75
    assert option.net_pnl_after_exercise_stt == 494.64


def test_bundled_contract_catalogue_is_research_only_until_source_verified():
    master = PointInTimeInstrumentMaster()
    assert master.resolve_lot_size("NIFTY", "2026-05-15") == 25
    with pytest.raises(PermissionError, match="unverified"):
        master.resolve_verified_lot_size("NIFTY", "2026-05-15")


def test_approval_token_can_only_be_consumed_once_under_concurrent_calls():
    from concurrent.futures import ThreadPoolExecutor

    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "approval.sqlite3"
        signer = CryptographicApprovalVerifier("a-strong-test-secret-key-12345", db_path=db)
        token = signer.issue_token(
            token_id="CONCURRENT-ONE-SHOT", actor="owner", role="RISK_OWNER",
            target_entity_id="ORDER-C", snapshot_hash="sha256:concurrent", ttl_seconds=300,
        )

        def consume(_):
            verifier = CryptographicApprovalVerifier(
                "a-strong-test-secret-key-12345", db_path=db,
            )
            try:
                verifier.verify_and_consume(
                    token, expected_target_id="ORDER-C",
                    expected_snapshot_hash="sha256:concurrent",
                )
                return "accepted"
            except PermissionError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(consume, range(8)))
        assert outcomes.count("accepted") == 1
        assert outcomes.count("rejected") == 7


def test_approval_replay_database_is_owner_read_write_only_on_posix():
    import os
    import stat
    if os.name != "posix":
        pytest.skip("POSIX file mode assertions do not apply on this platform")
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "approval.sqlite3"
        CryptographicApprovalVerifier("a-strong-test-secret-key-12345", db_path=db)
        assert stat.S_IMODE(db.stat().st_mode) == 0o600


def test_backtest_strategy_only_sees_read_only_history_up_to_current_bar():
    candles = [
        {"timestamp": f"2026-10-0{i+1}", "open": 100.0+i, "high": 102.0+i,
         "low": 99.0+i, "close": 101.0+i, "volume": 1000.0}
        for i in range(4)
    ]
    seen = []

    def guarded_signal(index, history):
        seen.append((index, len(history), history[-1]["close"]))
        assert len(history) == index + 1
        assert history[-1]["close"] == candles[index]["close"]
        with pytest.raises(TypeError):
            history[-1]["close"] = -999
        with pytest.raises(IndexError):
            history[index + 1]
        return 0

    run_backtest(candles, signal=guarded_signal)
    assert seen == [(0, 1, 101.0), (1, 2, 102.0), (2, 3, 103.0)]
    assert candles[-1]["close"] == 104.0


def test_backtest_rejects_partial_or_malformed_timestamp_columns():
    candles = [
        {"timestamp": "2026-10-01", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0, "volume": 10.0},
        {"open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 12.0},
    ]
    with pytest.raises(ValueError, match="every candle"):
        run_backtest(candles)
    candles[1]["timestamp"] = "not-a-date"
    with pytest.raises(ValueError, match="invalid ISO-8601"):
        run_backtest(candles)


@pytest.mark.parametrize(
    "timestamp, expected_error",
    [
        ("2026-03-08T02:30:00", "Nonexistent local timestamp"),
        ("2026-11-01T01:30:00", "Ambiguous local timestamp"),
    ],
)
def test_canonical_data_rejects_nonexistent_or_ambiguous_dst_wall_times(timestamp, expected_error):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "dst.csv"
        path.write_text(
            "timestamp,open,high,low,close,volume\n"
            f"{timestamp},100,101,99,100.5,1000\n",
            encoding="utf-8",
        )
        candles, report = load_canonical_data(
            path, interval="1m", source_timezone="America/New_York",
        )
        assert not report.is_valid
        assert not candles
        assert any(expected_error in error for error in report.errors)


def test_backtest_dashboard_hash_returns_full_streamed_sha256():
    import hashlib
    from nexus_titan.research.backtest import compute_file_sha256

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "large_dataset.bin"
        payload = (b"NEXUS-TITAN-PROVENANCE" * 100_000)
        path.write_bytes(payload)
        actual = compute_file_sha256(path)
        assert len(actual) == 64
        assert actual == hashlib.sha256(payload).hexdigest()

