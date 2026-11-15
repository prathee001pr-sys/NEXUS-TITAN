"""Stage25 project-wide *offline* backtest/audit orchestrator.

This exercises the already implemented historical strategies, Phase7 research
suite, and Stage22 options research smoke. It is NOT real NIFTY/BANKNIFTY F&O
backtesting: the bundled data are synthetic and lack official provenance,
point-in-time contracts and genuine option-chain depth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_NAMES = ("market_sample.csv", "nifty_daily_sample.csv")


def _exec(args: list[str], *, timeout: int = 150) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if result.returncode:
        detail = ((result.stderr or "") + "\n" + (result.stdout or ""))[-2200:]
        raise RuntimeError(f"Offline audit subprocess failed ({Path(args[0]).name}): {detail}")
    return result


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_full_offline_research_audit() -> dict[str, object]:
    """Run all declared *synthetic* backtest surfaces, fail on broken subprocess."""
    with tempfile.TemporaryDirectory(prefix="titan-stage25-audit-") as folder:
        temp = Path(folder)
        basic: list[dict] = []
        for name in SAMPLE_NAMES:
            src = ROOT / "data" / name
            out = temp / ("basic-" + name + ".json")
            _exec([
                "scripts/run_backtest.py", "--csv", str(src),
                "--strategy", "all", "--capital", "50000",
                "--quantity", "1", "--fee-per-side", "20",
                "--slippage-per-side", "2", "--json-out", str(out),
            ])
            report = json.loads(out.read_text(encoding="utf-8"))
            results = report.get("results", [])
            if not results or report["mode"] != "HISTORICAL_RESEARCH_ONLY":
                raise RuntimeError("Historical strategy suite returned no valid scorecards")
            for score in results:
                if "net_profit" not in score or "max_drawdown_percent" not in score:
                    raise RuntimeError("Missing historical P&L/drawdown metric")
            basic.append({
                "dataset_file": name,
                "sha256": _sha(src),
                "data_class": "BUNDLED_SYNTHETIC_SAMPLE_NOT_AUTHENTICATED_NSE",
                "candles": report["candles"],
                "strategies": len(results),
                "completed_trades": sum(int(x["total_trades"]) for x in results),
                "estimated_strategy_pnls": {
                    x["strategy_key"]: x["net_profit"] for x in results
                },
                "market_realism_verified": False,
            })
        advanced_out = temp / "advanced.json"
        _exec([
            "scripts/run_advanced_backtest_suite.py",
            "--csv", str(ROOT / "data" / "nifty_daily_sample.csv"),
            "--capital", "50000", "--skip-tests",
            "--json-out", str(advanced_out),
        ])
        advanced = json.loads(advanced_out.read_text(encoding="utf-8"))
        if advanced["mode"] != "HISTORICAL_AND_SHADOW_RESEARCH_ONLY":
            raise RuntimeError("Advanced suite unexpectedly claims a production mode")
        if advanced["strategy_research_scope"]["promotion_allowed"] is not False:
            raise RuntimeError("Advanced suite claimed unapproved strategy promotion")
        if advanced["strategy_research_scope"]["status"] != "SYNTHETIC_SIGNAL_SMOKE_TEST_ONLY":
            raise RuntimeError("Advanced suite did not identify synthetic research scope")
        # Synthetic QA source hashes are reproducible, but a source hash
        # NEVER establishes licensing or an official exchange calendar. The
        # Phase7 independent manifest reviewer correctly blocks production.
        if advanced["manifest_integrity_verified"] is not False:
            raise RuntimeError("Synthetic sample unexpectedly classified as verified exchange history")
        if not advanced["partial_fill_accounting_golden_passed"]:
            raise RuntimeError("Existing Phase7 partial fill accounting fixture failed")
        if not advanced["futures_options_golden_fixtures_passed"]:
            raise RuntimeError("Existing derivatives arithmetic golden fixtures failed")
        shadow = advanced["shadow_50k_paper_account"]["daily_statement"]
        if shadow.get("live_orders_transmitted") != 0:
            raise RuntimeError("Advanced shadow unexpectedly transmitted a live order")

        # Stage22 exercises option chain → fill → FIFO-unaware Stage19 legacy
        # research ledger → restart/recovery → blocked readiness.
        smoke = _exec(["scripts/run_stage22_research_smoke.py"])
        options = json.loads(smoke.stdout)
        if (options["live_trading_enabled"] or options["automatic_strategy_promotion"]
                or options["readiness_decision"] != "BLOCKED_STRUCTURAL_VALIDATION"):
            raise RuntimeError("Options research smoke crossed production release boundary")

        return {
            "report_schema_version": "stage25-offline-v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "OFFLINE_SYNTHETIC_RESEARCH_ONLY",
            "full_system_real_market_backtest_completed": False,
            "real_nse_or_banknifty_data_authenticated": False,
            "production_ready": False,
            "live_orders_transmitted": 0,
            "synthetic_historical_backtests": basic,
            "phase7_advanced_suite": {
                "strategies_evaluated": advanced["strategies_evaluated"],
                "manifest_sha256": advanced["dataset_manifest"].get("sha256_checksum"),
                "source_evidence_blockers": advanced["manifest_verification_notes"],
                "manifest_integrity_verified": advanced["manifest_integrity_verified"],
                "partial_fill_accounting_golden_passed": advanced["partial_fill_accounting_golden_passed"],
                "futures_options_golden_fixtures_passed": advanced["futures_options_golden_fixtures_passed"],
                "quality_gates": advanced["roadmap_quality_gates_g0_to_g9"],
                "test_run_intentionally_skipped_to_avoid_nested_pytest": True,
                "strategy_promotion_allowed": False,
            },
            "stage22_option_smoke": {
                "restart_state_match": options["restart_state_match"],
                "research_readiness_decision": options["readiness_decision"],
                "filled_quantity": options["filled_quantity"],
                "external_evidence_verified": options["external_evidence_verified"],
            },
            "stage25_sell_aware_multiday_covered_by_pytest": True,
            "limitations": [
                "Synthetic files contain no verified licensed NSE/BANKNIFTY history or real option-chain/depth.",
                "Several Phase7 strategy scorecards use placeholder index/equity-delivery assumptions.",
                "No genuine multi-day live-feed shadow evidence, risk-authorized production runtime or dashboard E2E.",
                "No verified broker contract-note fees, tax, SPAN/ELM or option exercise/assignment outcomes.",
                "No real-money or authenticated broker execution was performed.",
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN staged synthetic end-to-end audit")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()
    try:
        report = run_full_offline_research_audit()
        rendered = json.dumps(report, indent=2, sort_keys=True, allow_nan=False)
        if args.json_out:
            target = Path(args.json_out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"OFFLINE AUDIT FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
