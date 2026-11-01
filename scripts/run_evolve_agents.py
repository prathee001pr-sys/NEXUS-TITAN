"""Run TITAN EVOLVE's supervised local specialist cycle.

This runner does not enable live trading, execute generated code, or automatically
promote skills. Configure LLM access explicitly through environment secrets only
when model-assisted research is intended.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.research.backtest import load_candles, run_backtest
from nexus_titan.research.v6_strategies import AVAILABLE_STRATEGIES
from nexus_titan.self_improvement import (
    LearningStore, ResearchDocument, TitanEvolveEngine,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="NEXUS TITAN EVOLVE supervised agent cycle")
    parser.add_argument("--csv", default=None, help="Optional OHLCV data for local self-analysis")
    parser.add_argument("--db", default=str(ROOT / "data" / "titan_evolve_runtime.db"))
    parser.add_argument("--capital", type=float, default=50_000.0)
    parser.add_argument("--strategy", default="ema", choices=sorted(AVAILABLE_STRATEGIES))
    parser.add_argument("--llm-disabled", action="store_true",
                        help="Force deterministic local specialists even when LLM secrets are configured.")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    try:
        engine = TitanEvolveEngine(LearningStore(Path(args.db).resolve()))
        payload = {"memory_query": "backtest", "research_documents": []}
        if args.csv:
            candles = load_candles(args.csv)
            strategy = AVAILABLE_STRATEGIES[args.strategy]()
            backtest = run_backtest(
                candles, starting_capital=args.capital, signal=strategy.get_signal,
                fee_per_side=20.0, slippage_per_side=2.0,
            )
            payload.update({
                "candles": candles,
                "performance_metrics": {
                    "profit_factor": backtest.profit_factor,
                    "max_drawdown_pct": backtest.max_drawdown_percent,
                    "expectancy": backtest.expectancy,
                    "alpha_pct": backtest.alpha_percent,
                    "total_trades": backtest.total_trades,
                },
                "learning_record": {
                    "topic": "sample-backtest-observation",
                    "content": f"{strategy.name}: {backtest.return_percent:.3f}% on supplied sample.",
                    "source": Path(args.csv).name,
                    "evidence": "Exploratory sample only; not verified market history.",
                    "confidence": 0.30,
                    "tags": ["historical", "exploratory"],
                },
                "research_documents": [ResearchDocument(
                    title="Backtest provenance",
                    text=f"Supplied CSV contains {len(candles)} rows. Its external provenance/licence is not verified.",
                    source=f"local-csv:{Path(args.csv).name}", topic="data-quality",
                )],
            })
        coordinator = engine.create_agent_coordinator()
        if args.llm_disabled:
            coordinator.llm_provider = None
        outcomes = coordinator.run_cycle(payload, ROOT)
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agent_count": len(outcomes),
            "agent_results": [
                {"agent_id": item.agent_id, "status": item.status, "summary": item.summary,
                 "evidence": list(item.evidence), "artifacts": dict(item.artifacts),
                 "duration_ms": item.duration_ms}
                for item in outcomes
            ],
            "storage": engine.get_status(),
            "safety": {"live_trading_enabled": False, "generated_code_executed": False,
                       "production_changes_applied": False, "promotion_requires_human_approval": True},
        }
        rendered = json.dumps(report, indent=2, ensure_ascii=False, default=str)
        print(rendered)
        if args.json_out:
            output = Path(args.json_out)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if all(item.status != "ERROR" for item in outcomes) else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"EVOLVE cycle rejected or failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
