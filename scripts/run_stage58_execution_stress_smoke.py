"""Stage58 disposable, deterministic, brokerless NSE F&O execution stress QA.

Contracts, displayed depth, order books and fee schedule here are ONLY
synthetic/operator-declared; not exchange-authenticated or brokerage bills.
No files, user databases, capital reservations, orders or broker calls.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.cost.charges import IndianCostConfig
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.simulation.stage58_execution_stress import (
    Stage58DisplayedObservation, simulate_stage58_synthetic_execution,
)
from nexus_titan.virtual.microstructure import (
    MicrostructureConfig, OrderBookSnapshot,
)

NOW = datetime.fromisoformat("2026-11-02T09:16:00+05:30")


def _obs(time: datetime, label: str, displayed_ask_qty: int) -> Stage58DisplayedObservation:
    return Stage58DisplayedObservation(
        event_id=label,
        observed_at=time,
        book=OrderBookSnapshot(
            symbol="SYNTHNIFTYOPT", timestamp=time.isoformat(),
            bid_price=5.45, ask_price=5.5, bid_qty=200,
            ask_qty=displayed_ask_qty, last_traded_price=5.475,
            quote_age_ms=100, tick_size=0.05,
        ),
        depth_source_reference="QA-only/fabricated-displayed-depth",
        depth_source_declared_verified=True,
    )


def main() -> int:
    contract = PointInTimeContractSpec(
        symbol="SYNTHNIFTYOPT", underlying="NIFTY",
        exchange="NSE", segment="OPTIONS", lot_size=25,
        tick_size=0.05, freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_reference="QA-only/fabricated-point-in-time-contract",
        source_verified=True,
    )
    params = dict(
        contract=contract,
        calendar=nse_equity_derivatives_baseline(),
        side="BUY", requested_lots=4,
        costs=IndianCostConfig(),
    )
    snapshots = (
        _obs(NOW, "Q-1", 200),
        _obs(NOW + timedelta(seconds=1), "Q-2", 200),
    )
    baseline = simulate_stage58_synthetic_execution(snapshots, **params)
    stress = simulate_stage58_synthetic_execution(
        snapshots,
        **params,
        microstructure=MicrostructureConfig(
            max_participation_rate=0.10,
            impact_coefficient_bps=250,
            arrival_latency_ms=500,
        ),
    )
    unfilled = simulate_stage58_synthetic_execution(
        (_obs(NOW, "Q-NO-DEPTH", 0),), **params,
    )
    payload = dict(
        mode="STAGE58_LOCAL_FO_EXECUTION_STRESS_ONLY",
        baseline=asdict(baseline),
        stress=asdict(stress),
        unfilled=asdict(unfilled),
    )
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False, default=str))
    return 0 if all((
        baseline.status == "FILLED",
        baseline.filled_quantity == 100,
        baseline.fragment_fees_sum > 0,
        stress.filled_quantity <= baseline.filled_quantity,
        unfilled.filled_quantity == 0,
        unfilled.conservative_fee_reserve == 0,
        not baseline.production_ready,
        baseline.live_orders_transmitted == 0,
    )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
