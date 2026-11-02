"""Stage 22: real-module, synthetic-data, end-to-end offline research smoke.

Run from repository root:
    python scripts/run_stage22_research_smoke.py

No real market records, broker credentials, live orders or production risk
permissions are used. Files are written ONLY to a fresh temporary workspace.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, time
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
# Allow a beginner to execute the script before installing the package.
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import COLUMNS, load_research_option_chain_csv
from nexus_titan.data.option_chain_history import assemble_research_option_chain_history
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger, ResearchLedgerError,
)
from nexus_titan.shadow.research_recovery_validation import (
    DailyResearchShadowRecord, inspect_multiday_shadow_evidence,
    run_research_shadow_recovery_drill,
)
from nexus_titan.shadow.unified_readiness import prepare_unified_shadow_readiness
from nexus_titan.simulation.options_order_reconciliation import ResearchFillEvent
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)

OBS = datetime.fromisoformat("2026-11-02T09:16:00+05:30")
ACCOUNT = "STAGE22-SYNTHETIC-RESEARCH"


def _contract() -> PointInTimeContractSpec:
    # These fields have operator-*declared* verification; they are NOT actual
    # NSE instrument specifications or licensed contract metadata.
    return PointInTimeContractSpec(
        symbol="NIFTYOPT", underlying="NIFTY", exchange="NSE", segment="OPTIONS",
        lot_size=25, tick_size=0.05, freeze_quantity=1000,
        max_lots_per_trade=10, strike_step=50.0,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_reference="synthetic/manual-contract-fixture",
        source_verified=True,
    )


def _snapshot_csv() -> bytes:
    qtime = "2026-11-02T09:15:59+05:30"
    rows: list[dict[str, str]] = []
    for option_type in ("CE", "PE"):
        rows.append({
            "timestamp": qtime, "symbol": "NIFTYOPT", "underlying": "NIFTY",
            "expiry_date": "2026-11-05", "strike": "100",
            "option_type": option_type, "bid": "5.00", "ask": "5.50",
            "ltp": "5.25", "volume": "1000", "open_interest": "1500",
            "underlying_spot": "100.0", "lot_size": "25",
        })
    return (
        ",".join(COLUMNS) + "\n" +
        "".join(",".join(item[col] for col in COLUMNS) + "\n" for item in rows)
    ).encode("utf-8")


def run_offline_smoke(
    workspace: Path,
    *,
    starting_capital: float = 50_000.0,
    displayed_ask_quantity: int = 400,
    expected_sha256_override: str | None = None,
) -> dict[str, object]:
    """Connect existing stages 7–21 in a separate synthetic research account.

    A checksum or capital failure exits before a simulated order is settled.
    Existing local files will not be overwritten. No real trading is possible.
    """
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)
    csv_path = workspace / "synthetic_options_snapshot.csv"
    db_path = workspace / "synthetic_research_ledger.sqlite3"
    backup_path = workspace / "synthetic_recovery.sqlite3"
    if any(path.exists() for path in (csv_path, db_path, backup_path)):
        raise ValueError("Stage22 needs a fresh workspace; existing files are never overwritten")

    contract = _contract()
    calendar = nse_equity_derivatives_baseline()
    payload = _snapshot_csv()
    csv_path.write_bytes(payload)
    snapshot = load_research_option_chain_csv(
        csv_path,
        expected_sha256=(
            expected_sha256_override if expected_sha256_override is not None
            else hashlib.sha256(payload).hexdigest()
        ),
        contract=contract, observed_at=OBS, calendar=calendar,
        provider_reference="synthetic/test-provider-only",
        licence_evidence_reference="synthetic/no-verified-licence",
        calendar_evidence_reference="synthetic/unverified-calendar",
    )
    history = assemble_research_option_chain_history(
        [snapshot], contract=contract, calendar=calendar,
    )
    depth = OptionDisplayedDepth(
        as_of=OBS, bid_quantity=400, ask_quantity=displayed_ask_quantity,
        source_reference="synthetic/not-a-licensed-depth-feed",
        source_declared_verified=True,
    )
    fragment = simulate_historical_option_fill(
        history, contract=contract, calendar=calendar, observed_at=OBS,
        strike=100.0, option_type="CE", side="BUY", lots=2, depth=depth,
    )
    ledger = DurableResearchShadowLedger(
        db_path, account_id=ACCOUNT, starting_capital=starting_capital,
    )
    opening = ledger.status()
    ledger.reserve_buy(
        order_id="SYNTHETIC-ORDER-001", contract=contract, strike=100.0,
        option_type="CE", lots=2, as_of=OBS,
        max_unit_premium=6.0, fee_buffer=25.0,
    )
    reserved = ledger.status()
    assert reserved.reserved_cash > 0 and reserved.cash_balance == opening.cash_balance

    statement = ledger.settle_buy(
        order_id="SYNTHETIC-ORDER-001", contract=contract,
        strike=100.0, option_type="CE",
        events=[ResearchFillEvent(
            event_id="SYNTHETIC-FRAGMENT-001", observed_at=OBS,
            fragment=fragment,
        )],
    )
    after = ledger.status()
    if after.reserved_cash != 0 or after.open_order_count or (
        after.cash_balance > opening.cash_balance
    ):
        raise AssertionError("Offline research ledger conservation failed")
    if statement.filled_quantity != fragment.filled_quantity:
        raise AssertionError("Stage17 → Stage18 → Stage19 filled-quantity mismatch")
    if sum(qty for _, qty in after.option_inventory) != statement.filled_quantity:
        raise AssertionError("Stage19 synthetic inventory does not match simulated fill")

    restarted = DurableResearchShadowLedger(
        db_path, account_id=ACCOUNT, starting_capital=starting_capital,
    )
    if restarted.status() != after:
        raise AssertionError("Stage19 research state was not recovered on restart")
    try:
        restarted.reserve_buy(
            order_id="SYNTHETIC-ORDER-001", contract=contract,
            strike=100.0, option_type="CE", lots=2, as_of=OBS,
            max_unit_premium=6.0, fee_buffer=25.0,
        )
    except ResearchLedgerError as exc:
        if "Duplicate/replayed order_id" not in str(exc):
            raise
        replay_blocked = True
    else:
        raise AssertionError("Durable duplicate-order prevention failed")

    recovery = run_research_shadow_recovery_drill(
        restarted, backup_path=backup_path,
    )
    day_close = DailyResearchShadowRecord(
        session_date=OBS.date(),
        observed_at=datetime.combine(
            OBS.date(), time(15, 31), tzinfo=ZoneInfo("Asia/Kolkata")
        ),
        status=after,
        expected_cash_change=round(after.cash_balance - opening.cash_balance, 2),
        evidence_reference="synthetic/day-close-only",
    )
    continuity = inspect_multiday_shadow_evidence(
        [day_close], calendar=calendar,
    )
    if not continuity.is_structurally_valid or not recovery.passed:
        raise AssertionError("Stage20 offline continuity/recovery test failed")

    readiness = prepare_unified_shadow_readiness(
        ledger=restarted, daily_records=[day_close], calendar=calendar,
        recovery=recovery, evidence_submissions=[], claimed_closed_trades=0,
        as_of=datetime.combine(
            OBS.date(), time(16, 0), tzinfo=ZoneInfo("Asia/Kolkata")
        ),
    )
    if readiness.release_decision != "BLOCKED_STRUCTURAL_VALIDATION":
        raise AssertionError("Synthetic one-day BUY-only smoke must not pass release gate")
    if any((
        readiness.live_trading_enabled, readiness.automatic_strategy_promotion,
        readiness.external_authenticity_verified, readiness.official_market_data_verified,
        fragment.live_orders_transmitted, statement.live_orders_transmitted,
        after.live_orders_transmitted,
    )):
        raise AssertionError("Offline research result crossed a live/approval boundary")

    return {
        "dataset": "SYNTHETIC_ONLY_NOT_NSE_DATA",
        "workflow": "CSV_SHA256 → chain_integrity → history → execution → reconciliation → SQLite → restart → recovery → day_close → readiness",
        "snapshot_count": len(history.snapshots),
        "quote_count": len(snapshot.quotes),
        "requested_quantity": statement.requested_quantity,
        "filled_quantity": statement.filled_quantity,
        "simulated_fill_status": statement.status,
        "virtual_capital": opening.starting_capital,
        "projected_cash": after.cash_balance,
        "reserved_cash_after_settlement": after.reserved_cash,
        "simulated_fee_reserve": statement.conservative_fee_reserve,
        "restart_state_match": restarted.status() == after,
        "duplicate_order_rejected_after_restart": replay_blocked,
        "sqlite_backup_verified_locally": recovery.passed,
        "day_close_structure_valid": continuity.is_structurally_valid,
        "readiness_decision": readiness.release_decision,
        "external_evidence_verified": False,
        "live_trading_enabled": False,
        "automatic_strategy_promotion": False,
    }


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage22-offline-") as directory:
        report = run_offline_smoke(Path(directory))
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
