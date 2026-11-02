"""Run a historical-only NEXUS TITAN Phase 6 strategy backtest.

Example:
  PYTHONPATH=src python scripts/run_backtest.py --csv data/market_sample.csv --strategy all

The bundled/sample CSV is illustrative. No live prices, exchange orders or broker calls occur.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.research.backtest import load_candles, run_backtest
from nexus_titan.research.v6_strategies import AVAILABLE_STRATEGIES


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN historical Phase 6 backtest")
    parser.add_argument("--csv", required=True, help="Validated OHLCV CSV file")
    parser.add_argument("--strategy", default="all", choices=[*AVAILABLE_STRATEGIES, "all"])
    parser.add_argument("--capital", type=float, default=50_000.0)
    parser.add_argument("--quantity", type=float, default=1.0)
    parser.add_argument("--fee-per-side", type=float, default=20.0)
    parser.add_argument("--slippage-per-side", type=float, default=2.0)
    parser.add_argument("--instrument", default="EQUITY_DELIVERY",
                        choices=["EQUITY_DELIVERY", "EQUITY_INTRADAY", "FUTURES", "OPTIONS"])
    parser.add_argument("--indian-costs", action="store_true",
                        help="Use the configurable indicative Indian cost schedule.")
    parser.add_argument("--stop-loss", type=float, default=None)
    parser.add_argument("--target", type=float, default=None)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    try:
        candles = load_candles(csv_path)
        selected = list(AVAILABLE_STRATEGIES) if args.strategy == "all" else [args.strategy]
        results = []
        for key in selected:
            strategy = AVAILABLE_STRATEGIES[key]()
            result = run_backtest(
                candles, starting_capital=args.capital, quantity=args.quantity,
                fee_per_side=args.fee_per_side, slippage_per_side=args.slippage_per_side,
                signal=strategy.get_signal, stop_loss_pct=args.stop_loss,
                target_pct=args.target, use_indian_statutory_costs=args.indian_costs,
                instrument_type=args.instrument,
            )
            results.append({"strategy_key": key, "strategy_name": strategy.name, **asdict(result)})
        report = {
            "mode": "HISTORICAL_RESEARCH_ONLY",
            "dataset": str(csv_path),
            "candles": len(candles),
            "methodology_warning": (
                "Backtest results are research estimates only. They are not executable P&L, "
                "and sample data must not be treated as verified exchange history."
            ),
            "results": results,
        }
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        print(rendered)
        if args.json_out:
            output = Path(args.json_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            print(f"Saved report: {output}")
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Backtest rejected or failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
