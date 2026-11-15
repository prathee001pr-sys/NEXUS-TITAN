"""Stage60 no-broker demonstration of purged out-of-sample directional QA.

Fixtures are fabricated intraday index FUTURES, not authentic NSE data.
Results are forecast hit-rate diagnostics, NEVER traded fills, P&L,
execution costs, futures margin, real backtest or promotion evidence.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.stage59_futures_history import (
    Stage59FuturesCSVDeclaration, preflight_stage59_futures_csv,
)
from nexus_titan.research.stage60_purged_oos import (
    inspect_stage60_purged_oos,
)

START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
_HEADER = ("timestamp", "symbol", "exchange", "segment", "expiry_date", "lot_size",
           "open", "high", "low", "close", "volume", "open_interest")


def _case(folder: Path, underlying: str) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    contract = PointInTimeContractSpec(
        symbol=underlying + "FUT", underlying=underlying,
        exchange="NSE", segment="FUTURES",
        lot_size=25, tick_size=0.05, freeze_quantity=1000,
        max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5), expiry_date=date(2026, 11, 5),
        source_verified=True,
        source_reference="qa/fabricated-contract-source",
    )
    csv_lines = [",".join(_HEADER)]
    for i in range(46):
        price_cents = 10000 + (i % 9) * 5
        price = f"{price_cents // 100}.{price_cents % 100:02d}"
        row = (
            (START + timedelta(minutes=i)).isoformat(),
            contract.symbol, "NSE", "FUTURES", "2026-11-05",
            "25", "100.00", "105.00", "95.00", price, "1000", "2000",
        )
        csv_lines.append(",".join(row))
    payload = ("\n".join(csv_lines) + "\n").encode()
    path = folder / "synthetic_futures.csv"
    path.write_bytes(payload)
    manifest = Stage59FuturesCSVDeclaration(
        dataset_id="stage60-" + underlying,
        filename=path.name, expected_sha256=hashlib.sha256(payload).hexdigest(),
        provider_reference="qa/unverified-provider",
        licence_reference="qa/unverified-licence",
        calendar_reference="qa/unverified-calendar",
        contract_reference=contract.source_reference,
        expected_first=START,
        expected_last=START + timedelta(minutes=45),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    calendar = nse_equity_derivatives_baseline()
    history = preflight_stage59_futures_csv(
        folder, declaration=manifest, contract=contract, calendar=calendar,
    )
    report = inspect_stage60_purged_oos(
        history, contract=contract, calendar=calendar,
    )
    return {
        "dataset_id": report.dataset_id,
        "folds": len(report.folds),
        "candidate_labels": report.total_candidate_labels,
        "directional_predictions": report.total_directional_predictions,
        "directional_correct": report.total_correct_directions,
        "hit_rate": str(report.overall_directional_hit_rate)
            if report.overall_directional_hit_rate is not None else None,
        "evidence_verdict": report.evidence_verdict,
        "research_scope": report.implementation_scope,
        "digest": report.local_evidence_digest,
        "source_authenticated": report.dataset_source_authenticated,
        "real_fo_backtest_performance_verified": report.real_fo_backtest_performance_verified,
        "strategy_promotion_authorized": report.strategy_promotion_authorized,
        "live_orders_transmitted": report.live_orders_transmitted,
        "production_ready": report.production_ready,
    }


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage60-fixed-ma-oos-") as directory:
        root = Path(directory)
        cases = {
            name.lower(): _case(root / name.lower(), name)
            for name in ("NIFTY", "BANKNIFTY")
        }
        output = {
            "mode": "STAGE60_FIXED_MA_PURGED_OOS_DIRECTIONAL_QA_ONLY",
            "nifty": cases["nifty"],
            "banknifty": cases["banknifty"],
            "real_order_book_depth_verified": False,
            "actual_execution_costs_verified": False,
            "actual_futures_pnl_verified": False,
            "live_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(output, indent=2, sort_keys=True, allow_nan=False))
        return 0 if all((
            cases["nifty"]["folds"] == 3,
            cases["banknifty"]["folds"] == 3,
            cases["nifty"]["candidate_labels"] == 21,
            cases["banknifty"]["candidate_labels"] == 21,
            not cases["nifty"]["real_fo_backtest_performance_verified"],
            not cases["banknifty"]["strategy_promotion_authorized"],
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
