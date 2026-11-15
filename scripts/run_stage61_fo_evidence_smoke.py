"""Stage61 disposable, brokerless synthetic F&O evidence scorecard demo.

All history, top-of-book depth and contract metadata are fabricated and
self-declared. The fee model is an independent illustration, not bound
to any Stage60 forecast. This demo DOES NOT calculate trading P&L.
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

from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.stage59_futures_history import (
    Stage59FuturesCSVDeclaration, preflight_stage59_futures_csv,
)
from nexus_titan.research.stage60_purged_oos import inspect_stage60_purged_oos
from nexus_titan.research.stage61_evidence_scorecard import inspect_stage61_fo_evidence
from nexus_titan.simulation.stage58_execution_stress import (
    Stage58DisplayedObservation, simulate_stage58_synthetic_execution,
)
from nexus_titan.virtual.microstructure import OrderBookSnapshot

START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
_HEADER = ("timestamp", "symbol", "exchange", "segment", "expiry_date",
           "lot_size", "open", "high", "low", "close", "volume", "open_interest")


def _inputs(folder: Path, underlying: str = "NIFTY"):
    """Construct actual Stage59/60/58 objects from temporary synthetic inputs."""
    folder.mkdir(parents=True, exist_ok=True)
    contract = PointInTimeContractSpec(
        symbol=underlying + "FUT", underlying=underlying,
        exchange="NSE", segment="FUTURES", lot_size=25,
        tick_size=0.05, freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_reference="qa/not-authenticated-point-in-time-contract",
        source_verified=True,  # LOCAL DECLARATION ONLY
    )
    lines = [",".join(_HEADER)]
    for i in range(46):
        value = 10000 + (i % 9) * 5
        lines.append(",".join((
            (START + timedelta(minutes=i)).isoformat(), contract.symbol,
            "NSE", "FUTURES", "2026-11-05", "25",
            "100.00", "105.00", "95.00",
            f"{value // 100}.{value % 100:02d}", "1000", "2000",
        )))
    raw = ("\n".join(lines) + "\n").encode("utf-8")
    (folder / "futures.csv").write_bytes(raw)
    manifest = Stage59FuturesCSVDeclaration(
        dataset_id="stage61-qa-" + underlying.lower(),
        filename="futures.csv",
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        provider_reference="qa/fabricated-no-vendor-auth",
        licence_reference="qa/not-reviewed-licence",
        calendar_reference="qa/not-verified-official-calendar",
        contract_reference=contract.source_reference,
        expected_first=START,
        expected_last=START + timedelta(minutes=45),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    calendar = nse_equity_derivatives_baseline()
    history = preflight_stage59_futures_csv(
        folder, declaration=manifest, contract=contract, calendar=calendar,
    )
    oos = inspect_stage60_purged_oos(
        history, contract=contract, calendar=calendar,
    )
    # This is a separate fabricated order-book scenario, NOT matched
    # to any future origin/label in the Stage60 OOS fold.
    snapshots = []
    for index in range(2):
        now = START + timedelta(minutes=1, seconds=index)
        book = OrderBookSnapshot(
            symbol=contract.symbol, timestamp=now.isoformat(),
            bid_price=100, ask_price=100.05,
            bid_qty=200, ask_qty=200,
            last_traded_price=100.05, quote_age_ms=100,
            tick_size=0.05,
        )
        snapshots.append(Stage58DisplayedObservation(
            event_id="QA-BOOK-" + str(index), observed_at=now,
            book=book, depth_source_reference="qa/fabricated-book",
            depth_source_declared_verified=True,
        ))
    execution = simulate_stage58_synthetic_execution(
        tuple(snapshots), contract=contract, calendar=calendar,
        side="BUY", requested_lots=4, costs=IndianCostConfig(),
    )
    return history, oos, execution


def _summary(history, oos, execution):
    result = inspect_stage61_fo_evidence(
        history, oos, execution=execution,
    )
    return {
        "underlying": result.underlying,
        "candles": result.inspected_candles,
        "oos_folds": result.oos_folds,
        "oos_predictions": result.oos_predictions,
        "synthetic_execution_fragments": result.synthetic_execution_fragment_count,
        "synthetic_execution_fee_reserve": result.synthetic_execution_fee_reserve,
        "missing_evidence": list(result.missing_evidence),
        "mandatory_release_blockers": list(result.mandatory_release_blockers),
        "local_inputs_structurally_consistent": result.local_inputs_structurally_consistent,
        "local_evidence_sha256": result.local_evidence_sha256,
        "execution_scenario_bound_to_holdout": result.execution_scenario_bound_to_holdout,
        "genuine_futures_options_backtest_verified":
            result.genuine_futures_options_backtest_verified,
        "strategy_promotion_authorized": result.strategy_promotion_authorized,
        "production_ready": result.production_ready,
        "broker_orders_transmitted": result.broker_orders_transmitted,
    }


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage61-evidence-qa-") as directory:
        root = Path(directory)
        samples = {}
        for underlying in ("NIFTY", "BANKNIFTY"):
            inputs = _inputs(root / underlying.lower(), underlying)
            samples[underlying.lower()] = _summary(*inputs)
        payload = {
            "mode": "STAGE61_SYNTHETIC_EVIDENCE_NO_GO_SCORECARD_ONLY",
            **samples,
            "real_vendor_data_present": False,
            "actual_fo_pnl_verified": False,
            "global_risk_and_execution_ready": False,
            "broker_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False))
        return 0 if all(
            item["local_inputs_structurally_consistent"]
            and not item["execution_scenario_bound_to_holdout"]
            and not item["genuine_futures_options_backtest_verified"]
            and not item["strategy_promotion_authorized"]
            and not item["production_ready"]
            and len(item["mandatory_release_blockers"]) >= 8
            for item in samples.values()
        ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
