"""Run the comprehensive NEXUS TITAN V2 Phase 7 Advanced Backtesting, Walk-Forward, Monte Carlo, Derivatives, Microstructure Shadow, and G0-G9 Quality Gate Suite.

Usage:
  PYTHONPATH=src python3 scripts/run_advanced_backtest_suite.py \
      --csv data/nifty_daily_sample.csv \
      --json-out reports/phase7_advanced_backtest_report.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.core.security_gates import (
    CryptographicApprovalVerifier, evaluate_g0_to_g9_quality_gates,
)
from nexus_titan.crypto.crypto_engine import CryptoVirtualAccount
from nexus_titan.data.instrument_master import PointInTimeInstrumentMaster
from nexus_titan.data.provenance import build_manifest_from_csv, verify_dataset_manifest
from nexus_titan.derivatives.chain_and_settlement import (
    OptionChainQuote,
    estimate_span_elm_margin,
    inspect_option_chain_snapshot,
    settle_option_at_expiry,
)
from nexus_titan.derivatives.options_engine import calculate_option_greeks, solve_implied_volatility
from nexus_titan.cost.charges import calculate_indian_trade_costs
from nexus_titan.research.backtest import load_candles, run_backtest
from nexus_titan.research.post_mortem import generate_post_mortem
from nexus_titan.research.v6_strategies import AVAILABLE_STRATEGIES
from nexus_titan.research.v6_validation import (
    evaluate_multiple_comparison_bias,
    evaluate_strategy_promotion,
    rolling_walk_forward_validation,
    run_monte_carlo_simulation,
)
from nexus_titan.virtual.order_manager import OrderState, VirtualAccount
from nexus_titan.virtual.microstructure import (
    MicrostructureSimulator,
    OrderBookSnapshot,
    ShadowPaperRunner,
)



def compute_source_code_fingerprint() -> dict[str, object]:
    """Fingerprint the exact source and scripts used to generate this report."""
    digest = hashlib.sha256()
    files = sorted((ROOT / "src").rglob("*.py")) + [ROOT / "scripts" / "run_advanced_backtest_suite.py"]
    unique_files = sorted(set(files), key=lambda path: path.relative_to(ROOT).as_posix())
    for path in unique_files:
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return {"sha256": digest.hexdigest(), "python_source_file_count": len(unique_files)}


def verify_phase7_safety_smoke_checks() -> dict[str, bool]:
    """Run small deterministic checks used by release gates; never treat them as a pentest."""
    checks = {
        "approval_replay_protection_verified": False,
        "stale_feed_protection_verified": False,
        "kill_switch_verified": False,
        "daily_loss_lockout_verified": False,
        "microstructure_golden_fixtures_passed": False,
    }
    with tempfile.TemporaryDirectory(prefix="titan-gate-smoke-") as temp_dir:
        root = Path(temp_dir)
        try:
            smoke_signing_key = "phase7-smoke-only-secret-key-2026"
            approval_db = root / "approval.sqlite3"
            signer = CryptographicApprovalVerifier(smoke_signing_key, db_path=approval_db)
            token = signer.issue_token(
                token_id="PHASE7-SMOKE-REPLAY", actor="LOCAL_TEST_OWNER",
                role="RISK_OWNER", target_entity_id="SMOKE-ORDER",
                snapshot_hash="sha256:phase7-smoke", ttl_seconds=300,
            )
            signer.verify_and_consume(
                token, expected_target_id="SMOKE-ORDER",
                expected_snapshot_hash="sha256:phase7-smoke",
            )
            restarted = CryptographicApprovalVerifier(smoke_signing_key, db_path=approval_db)
            try:
                restarted.verify_and_consume(
                    token, expected_target_id="SMOKE-ORDER",
                    expected_snapshot_hash="sha256:phase7-smoke",
                )
            except PermissionError:
                checks["approval_replay_protection_verified"] = True

            stale = OrderBookSnapshot(
                "SMOKE", "2026-11-01T10:00:00+05:30", 99.95, 100.00, 100, 100,
                99.98, quote_age_ms=5_000.0,
            )
            stale_result = MicrostructureSimulator().evaluate_order_against_book(
                side="BUY", order_type="MARKET", requested_qty=1, lot_size=1, book=stale,
            )
            checks["stale_feed_protection_verified"] = not stale_result.accepted_for_fill and "STALE_QUOTE_BLOCKED" in stale_result.status_reason

            account = VirtualAccount("GATE-KILL", 50_000, state_dir=root / "kill", require_pretrade_risk_check=False)
            account.activate_emergency_kill_switch("gate smoke test", actor="LOCAL_TEST")
            rejected = account.submit_order("TCS", "BUY", 1, entry_price=100.0, stop_price=90.0)
            checks["kill_switch_verified"] = rejected.state == OrderState.REJECTED

            loss_account = VirtualAccount("GATE-LOSS", 10_000, state_dir=root / "loss", require_pretrade_risk_check=True)
            buy = loss_account.submit_order("TCS", "BUY", 10, entry_price=100.0, stop_price=90.0)
            loss_account.execute_fill(buy.order_id, 100.0)
            sell = loss_account.submit_order("TCS", "SELL", 10)
            loss_account.execute_fill(sell.order_id, 60.0)
            try:
                loss_account.submit_order("INFY", "BUY", 1, entry_price=100.0, stop_price=90.0)
            except ValueError as exc:
                checks["daily_loss_lockout_verified"] = "Daily loss limit" in str(exc)

            good = OrderBookSnapshot(
                "SMOKE", "2026-11-01T10:00:00+05:30", 99.95, 100.00, 400, 400,
                99.98, quote_age_ms=10.0,
            )
            filled = MicrostructureSimulator().evaluate_order_against_book(
                side="BUY", order_type="MARKET", requested_qty=10, lot_size=1, book=good,
            )
            checks["microstructure_golden_fixtures_passed"] = (
                filled.accepted_for_fill and filled.filled_qty > 0
                and filled.execution_price >= good.ask_price
                and filled.filled_qty + filled.residual_qty == 10
            )
        except Exception:
            # Any unexpected smoke-test failure leaves every unresolved gate false.
            pass
    return checks


def verify_partial_fill_accounting_golden() -> bool:
    """Compare a two-part exit against an independently hand-calculated equity P&L."""
    with tempfile.TemporaryDirectory(prefix="titan-accounting-golden-") as temp_dir:
        account = VirtualAccount(
            "GOLDEN-PARTIAL-EXIT", 100_000.0, state_dir=temp_dir,
            require_pretrade_risk_check=False,
        )
        entry = account.submit_order("TCS", "BUY", 10, instrument_type="EQUITY_DELIVERY")
        account.execute_fill(entry.order_id, 100.0, fill_qty=10)
        exit_order = account.submit_order("TCS", "SELL", 10, instrument_type="EQUITY_DELIVERY")
        account.execute_fill(exit_order.order_id, 110.0, fill_qty=4, idempotency_key="GOLDEN-EXIT-4")
        account.execute_fill(exit_order.order_id, 120.0, fill_qty=6, idempotency_key="GOLDEN-EXIT-6")
        expected_gross = 4 * (110.0 - 100.0) + 6 * (120.0 - 100.0)
        fees = sum(fill.fees for order in account.orders.values() for fill in order.fills)
        expected_net = round(expected_gross - fees, 2)
        rec = account.reconcile()
        return (
            rec.is_reconciled and abs(rec.balance_discrepancy) <= 0.01
            and abs(account.realized_pnl - expected_net) <= 0.01
            and abs(rec.realized_pnl - expected_net) <= 0.01
        )


def verify_futures_options_accounting_golden() -> dict[str, bool]:
    """Compare derivative calculations with hand-calculated model fixtures.

    These fixtures verify arithmetic and fee-component allocation only. They do
    not certify that the indicative rate schedule matches a broker contract note
    or current exchange SPAN/ELM parameters.
    """
    results = {
        "futures_margin_arithmetic": False,
        "futures_buy_cost_arithmetic": False,
        "futures_sell_cost_arithmetic": False,
        "index_option_expiry_pnl_arithmetic": False,
    }
    try:
        margin = estimate_span_elm_margin(
            underlying_spot=20_000.0, quantity=25, instrument_type="FUTURES",
            span_pct=12.0, elm_pct=3.0,
        )
        results["futures_margin_arithmetic"] = (
            margin.notional_value == 500_000.0
            and margin.span_margin == 60_000.0
            and margin.exposure_margin == 15_000.0
            and margin.total_margin_blocked == 75_000.0
        )

        # ₹500,000 futures turnover: brokerage ₹20, exchange ₹9.15,
        # SEBI ₹0.50, buy-side stamp ₹10, GST ₹5.34; rounded total ₹44.99.
        buy_cost = calculate_indian_trade_costs("BUY", 20_000.0, 25, "FUTURES")
        results["futures_buy_cost_arithmetic"] = (
            buy_cost.brokerage == 20.0 and buy_cost.stt == 0.0
            and buy_cost.exchange_charges == 9.15 and buy_cost.sebi_charges == 0.50
            and buy_cost.stamp_duty == 10.0 and buy_cost.gst == 5.34
            and buy_cost.total_charges == 44.99
        )

        # Same sell turnover adds ₹250 futures STT and removes buy stamp duty.
        sell_cost = calculate_indian_trade_costs("SELL", 20_000.0, 25, "FUTURES")
        results["futures_sell_cost_arithmetic"] = (
            sell_cost.brokerage == 20.0 and sell_cost.stt == 250.0
            and sell_cost.exchange_charges == 9.15 and sell_cost.sebi_charges == 0.50
            and sell_cost.stamp_duty == 0.0 and sell_cost.gst == 5.34
            and sell_cost.total_charges == 284.99
        )

        # Long 20000 CE: settlement 20100, intrinsic ₹100, premium ₹80,
        # 25 units -> gross ₹500; indicative entry charges ₹1.61 and
        # configured exercise STT ₹3.75 -> net ₹494.64.
        option = settle_option_at_expiry(
            symbol="NIFTY26NOV20000CE", option_type="CE", side="LONG",
            settlement_spot=20_100.0, strike=20_000.0, quantity=25,
            entry_premium=80.0, is_index_option=True,
        )
        results["index_option_expiry_pnl_arithmetic"] = (
            option.is_in_the_money and option.exercised
            and option.settlement_mode == "CASH_INDEX"
            and option.intrinsic_payoff_per_unit == 100.0
            and option.gross_pnl == 500.0 and option.exercise_stt == 3.75
            and option.net_pnl_after_exercise_stt == 494.64
        )
    except Exception:
        return results
    return results

def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN Phase 7 Advanced Backtest & Verification Suite")
    parser.add_argument("--csv", default=str(ROOT / "data" / "nifty_daily_sample.csv"))
    parser.add_argument("--capital", type=float, default=50_000.0)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--source-timezone", default="Asia/Kolkata",
                        help="Timezone used for naive CSV timestamps (default: Asia/Kolkata).")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Do not execute pytest; G0 will remain unverified.")
    args = parser.parse_args()

    test_evidence = {"passed": 0, "total": 0, "success": False, "output": "Not run"}
    if not args.skip_tests:
        test_run = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-o", "addopts="],
            cwd=ROOT, capture_output=True, text=True, check=False,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src") + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else "")},
        )
        combined_test_output = (test_run.stdout or "") + "\n" + (test_run.stderr or "")
        summary_line = next((line.strip() for line in reversed(combined_test_output.splitlines())
                            if re.search(r"\d+ passed", line)), "")
        counts = {name: int(count) for count, name in re.findall(
            r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)", summary_line
        )}
        test_total = sum(counts.values())
        subtests_match = re.search(r"(\d+) subtests passed", summary_line)
        test_evidence = {
            "passed": counts.get("passed", 0),
            "total": test_total,
            "subtests_passed": int(subtests_match.group(1)) if subtests_match else 0,
            "success": test_run.returncode == 0 and test_total > 0
                       and counts.get("failed", 0) == 0 and counts.get("error", 0) == 0
                       and counts.get("errors", 0) == 0 and counts.get("passed", 0) > 0,
            "return_code": test_run.returncode,
            "output_tail": combined_test_output[-4000:],
        }

    csv_path = Path(args.csv).resolve()
    manifest = build_manifest_from_csv(
        csv_path,
        dataset_id=f"NIFTY-RESEARCH-{csv_path.stem}",
        instrument_symbol="NIFTY",
        interval="1d",
        timezone_name=args.source_timezone,
        dataset_class="SYNTHETIC_SMOKE_FIXTURE" if csv_path.name in {"market_sample.csv", "nifty_daily_sample.csv"} else "UNVERIFIED_RESEARCH_SAMPLE",
    )
    manifest_ok, manifest_notes = verify_dataset_manifest(manifest, csv_path)
    manifest_report = manifest.to_dict()
    try:
        manifest_report["file_path"] = csv_path.relative_to(ROOT).as_posix()
    except ValueError:
        manifest_report["file_path"] = csv_path.name
    candles = load_candles(csv_path, symbol="NIFTY", interval="1d")

    master = PointInTimeInstrumentMaster()
    lot_2023 = master.resolve_lot_size("BANKNIFTY", "2023-05-15")
    lot_2026 = master.resolve_lot_size("BANKNIFTY", "2026-05-15")
    nifty_lot_2026 = master.resolve_lot_size("NIFTY", "2026-05-15")

    strategy_reports = []
    num_trials = len(AVAILABLE_STRATEGIES)

    for key, factory in AVAILABLE_STRATEGIES.items():
        strategy = factory()
        bt = run_backtest(
            candles,
            starting_capital=args.capital,
            quantity=1.0,
            fee_per_side=20.0,
            slippage_per_side=2.0,
            signal=strategy.get_signal,
            stop_loss_pct=1.5,
            target_pct=3.5,
            use_indian_statutory_costs=True,
            instrument_type="EQUITY_DELIVERY",
            spread_bps=2.0,
        )
        _, wf_anchored = rolling_walk_forward_validation(
            candles,
            lambda _: (lambda i, rows, k=key: AVAILABLE_STRATEGIES[k]().get_signal(i, rows)),
            num_folds=4,
            min_trades_gate=5,
            starting_capital=args.capital,
            use_indian_statutory_costs=True,
            window_mode="anchored",
        )
        _, wf_sliding = rolling_walk_forward_validation(
            candles,
            lambda _: (lambda i, rows, k=key: AVAILABLE_STRATEGIES[k]().get_signal(i, rows)),
            num_folds=4,
            min_trades_gate=5,
            starting_capital=args.capital,
            use_indian_statutory_costs=True,
            window_mode="sliding",
        )
        mc = run_monte_carlo_simulation(
            [t["pnl"] for t in bt.trade_log],
            starting_capital=args.capital,
            iterations=500,
            method="block_bootstrap",
            block_size=2,
        )
        dsr = evaluate_multiple_comparison_bias(
            bt.sharpe_ratio, num_trials=num_trials, sample_length=len(candles)
        )
        promo = evaluate_strategy_promotion(
            strategy.name,
            bt,
            wf_anchored,
            mc,
            is_verified_dataset=manifest.allowed_for_strategy_promotion,
        )
        pm = generate_post_mortem(strategy.name, bt, slippage_per_side=2.0)

        strategy_reports.append({
            "strategy_key": key,
            "strategy_name": strategy.name,
            "backtest": {
                k: v for k, v in asdict(bt).items() if k != "equity_curve"
            },
            "walk_forward_4fold_anchored": asdict(wf_anchored),
            "walk_forward_4fold_sliding": asdict(wf_sliding),
            "monte_carlo": asdict(mc),
            "deflated_sharpe": asdict(dsr),
            "promotion_decision": asdict(promo),
            "post_mortem": asdict(pm),
        })

    # Run a Futures Long+Short backtest demonstration on the same series
    futures_bt = run_backtest(
        candles,
        starting_capital=250_000.0,
        quantity=float(nifty_lot_2026),
        instrument_lot_size=nifty_lot_2026,
        signal=AVAILABLE_STRATEGIES["rsi"]().get_signal,
        stop_loss_pct=1.2,
        target_pct=2.5,
        use_indian_statutory_costs=True,
        instrument_type="FUTURES",
        initial_margin_pct=20.0,
        allow_short=True,
        spread_bps=1.5,
    )

    # Run ₹50,000 Shadow Paper Account simulation with partial fill & microstructure
    shadow_state = tempfile.TemporaryDirectory(prefix="titan-shadow-demo-")
    shadow = ShadowPaperRunner(
        starting_capital=50_000.0, account_id="TITAN-50K-SHADOW-DEMO",
        state_dir=shadow_state.name,
    )
    book_entry = OrderBookSnapshot(
        symbol="RELIANCE",
        timestamp="2026-11-01T09:20:00+05:30",
        bid_price=1299.50,
        ask_price=1300.00,
        bid_qty=200,
        ask_qty=40,  # 25% participation cap = 10 units filled on first tick
        last_traded_price=1299.75,
        quote_age_ms=45.0,
    )
    shadow_order, sim_entry = shadow.route_shadow_order(
        book=book_entry,
        side="BUY",
        quantity=10,
        order_type="MARKET",
        instrument_type="EQUITY_DELIVERY",
        lot_size=1,
        stop_price=1275.00,
        target_price=1350.00,
    )
    # Mark-to-market & partial exit test (5 units then 5 units)
    shadow.account.mark_to_market({"RELIANCE": 1318.00}, trigger_exits=False)
    sell_ord = shadow.account.submit_order("RELIANCE", "SELL", 10, instrument_type="EQUITY_DELIVERY")
    shadow.account.execute_fill(sell_ord.order_id, fill_price=1318.00, fill_qty=5, idempotency_key="SELL-PART-1")
    shadow.account.execute_fill(sell_ord.order_id, fill_price=1322.00, fill_qty=5, idempotency_key="SELL-PART-2")
    shadow_statement = shadow.generate_daily_statement("2026-11-01")

    # Options chain, Greeks, SPAN/ELM margin, and expiry settlement check
    spot_px = candles[-1]["close"]
    atm_strike = round(spot_px / 50.0) * 50.0
    call_greeks = calculate_option_greeks(spot_px, atm_strike, 7.0, 0.14, option_type="CE", dividend_yield=0.012)
    solved_iv = solve_implied_volatility(call_greeks.theoretical_price, spot_px, atm_strike, 7.0, "CE", dividend_yield=0.012)
    chain_snapshot = [
        OptionChainQuote(
            timestamp="2026-11-01T15:29:00+05:30",
            symbol=f"NIFTY26NOV{int(atm_strike)}CE",
            underlying="NIFTY",
            expiry_date="2026-11-05",
            strike=atm_strike,
            option_type="CE",
            bid=max(0.05, round(call_greeks.theoretical_price - 0.50, 2)),
            ask=round(call_greeks.theoretical_price + 0.50, 2),
            ltp=call_greeks.theoretical_price,
            volume=125_000,
            open_interest=1_850_000,
            underlying_spot=spot_px,
            lot_size=25,
        )
    ]
    chain_quality = inspect_option_chain_snapshot(chain_snapshot)
    futures_margin = estimate_span_elm_margin(
        underlying_spot=spot_px, quantity=25, instrument_type="FUTURES"
    )
    expiry_settlement = settle_option_at_expiry(
        symbol=f"NIFTY26NOV{int(atm_strike)}CE",
        option_type="CE",
        side="LONG",
        settlement_spot=atm_strike + 140.0,
        strike=atm_strike,
        quantity=25,
        entry_premium=call_greeks.theoretical_price,
        is_index_option=True,
    )

    # Crypto virtual silo partial exit reconciliation
    crypto = CryptoVirtualAccount(starting_capital=1_000.0, apply_indian_vda_tds=True)
    crypto.execute_crypto_order("BTCUSDT", "BUY", price=70_000.0, quantity=0.004)
    crypto.execute_crypto_order("BTCUSDT", "SELL", price=72_000.0, quantity=0.002)
    crypto.execute_crypto_order("BTCUSDT", "SELL", price=73_000.0, quantity=0.002)
    crypto_rec = crypto.reconcile_crypto()

    safety_evidence = verify_phase7_safety_smoke_checks()
    derivative_golden_evidence = verify_futures_options_accounting_golden()
    futures_options_golden_passed = all(derivative_golden_evidence.values())
    gates_report = evaluate_g0_to_g9_quality_gates(
        tests_passed=test_evidence["passed"],
        tests_total=test_evidence["total"],
        test_run_success=test_evidence["success"],
        test_run_attempted=not args.skip_tests,
        source_api_parity_verified=False,
        golden_accounting_reconciled=verify_partial_fill_accounting_golden(),
        futures_options_golden_fixtures_passed=futures_options_golden_passed,
        shadow_50k_reconciled=shadow_statement.is_reconciled,
        microstructure_golden_fixtures_passed=safety_evidence["microstructure_golden_fixtures_passed"],
        approval_replay_protection_verified=safety_evidence["approval_replay_protection_verified"],
        stale_feed_protection_verified=safety_evidence["stale_feed_protection_verified"],
        kill_switch_verified=safety_evidence["kill_switch_verified"],
        daily_loss_lockout_verified=safety_evidence["daily_loss_lockout_verified"],
        has_licensed_15yr_dataset=False,
        has_external_pentest_signoff=False,
        ops_recovery_verified=False,
        multi_day_shadow_observation_verified=False,
        owner_release_signed=False,
        live_trading_disabled=True,
    )

    full_report = {
        "report_schema_version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "HISTORICAL_AND_SHADOW_RESEARCH_ONLY",
        "source_code_fingerprint": compute_source_code_fingerprint(),
        "strategy_research_scope": {
            "status": "SYNTHETIC_SIGNAL_SMOKE_TEST_ONLY",
            "warning": (
                "The bundled NIFTY daily sample is synthetic and the index itself is not an equity-delivery "
                "instrument. The scorecard's EQUITY_DELIVERY charge setting is a placeholder to exercise the "
                "simulator path, not a valid NIFTY execution model. Do not interpret these rupee-like P&L "
                "figures as tradable performance. Re-run on a verified tradable contract with official "
                "point-in-time metadata and broker/exchange costs."
            ),
            "promotion_allowed": False,
        },
        "dataset_manifest": manifest_report,
        "manifest_verification_notes": list(manifest_notes),
        "manifest_integrity_verified": manifest_ok,
        "test_run_evidence": test_evidence,
        "safety_smoke_evidence": safety_evidence,
        "partial_fill_accounting_golden_passed": verify_partial_fill_accounting_golden(),
        "futures_options_golden_evidence": derivative_golden_evidence,
        "futures_options_golden_fixtures_passed": futures_options_golden_passed,
        "futures_options_fixture_scope": (
            "Hand-calculated model arithmetic only; does not verify official exchange rates, "
            "broker contract notes, actual SPAN/ELM parameters, or stock-option physical delivery."
        ),
        "point_in_time_instrument_master": {
            "catalogue_status": "UNVERIFIED_STATIC_RESEARCH_REFERENCE",
            "production_sizing_allowed": False,
            "verification_note": (
                "Bundled historical lot-size entries are illustrative references, not an attached "
                "official point-in-time exchange contract master. Use resolve_verified_lot_size() "
                "only after independently validating and recording the official source."
            ),
            "BANKNIFTY_lot_2023_reference": lot_2023,
            "BANKNIFTY_lot_2026_reference": lot_2026,
            "NIFTY_lot_2026_reference": nifty_lot_2026,
        },
        "strategies_evaluated": len(strategy_reports),
        "strategy_scorecards": strategy_reports,
        "futures_long_short_backtest": {
            k: v for k, v in asdict(futures_bt).items() if k != "equity_curve"
        },
        "shadow_50k_paper_account": {
            "entry_microstructure": asdict(sim_entry),
            "daily_statement": asdict(shadow_statement),
        },
        "derivatives_analytics_and_settlement": {
            "spot_price": spot_px,
            "atm_strike": atm_strike,
            "call_greeks_with_dividend": asdict(call_greeks),
            "recovered_iv": solved_iv,
            "option_chain_quality": asdict(chain_quality),
            "nifty_futures_span_elm_margin": asdict(futures_margin),
            "itm_expiry_settlement": asdict(expiry_settlement),
        },
        "crypto_virtual_silo_reconciliation": crypto_rec,
        "roadmap_quality_gates_g0_to_g9": gates_report,
    }

    rendered = json.dumps(full_report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"Saved full Phase 7 report to: {out_path}")
    shadow_state.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
