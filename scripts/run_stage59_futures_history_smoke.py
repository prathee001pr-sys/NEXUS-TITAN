"""Stage59: disposable NIFTY/BANKNIFTY futures history preflight demo.

All CSV data is deliberately fabricated. The caller-provided contract,
vendor and calendar references are NOT independently verified. No data
upload, vendor API, user database, broker, trades or promotion.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import nse_equity_derivatives_baseline
from nexus_titan.data.stage59_futures_history import (
    Stage59FuturesCSVDeclaration, Stage59HistoryBlocked,
    preflight_stage59_futures_csv,
)

START = datetime.fromisoformat("2026-11-02T09:15:00+05:30")
FIELDS = ("timestamp", "symbol", "exchange", "segment", "expiry_date", "lot_size",
          "open", "high", "low", "close", "volume", "open_interest")


def _case(root: Path, underlying: str):
    root.mkdir(parents=True, exist_ok=True)
    filename = "synthetic_futures.csv"
    csv_rows = [",".join(FIELDS)]
    for i in range(3):
        row = dict(
            timestamp=(START + timedelta(minutes=i)).isoformat(),
            symbol=underlying + "FUT", exchange="NSE", segment="FUTURES",
            expiry_date="2026-11-05", lot_size="25",
            open="100.00", high="101.00", low="99.00", close="100.05",
            volume="1000", open_interest="2000",
        )
        csv_rows.append(",".join(row[f] for f in FIELDS))
    payload = ("\n".join(csv_rows) + "\n").encode("utf-8")
    path = root / filename
    path.write_bytes(payload)
    contract = PointInTimeContractSpec(
        symbol=underlying + "FUT", underlying=underlying,
        exchange="NSE", segment="FUTURES",
        lot_size=25, tick_size=0.05,
        freeze_quantity=1000, max_lots_per_trade=10,
        effective_from=date(2026, 11, 1),
        effective_to=date(2026, 11, 5),
        expiry_date=date(2026, 11, 5),
        source_verified=True,
        source_reference="qa/unverified-contract-claim",
    )
    declaration = Stage59FuturesCSVDeclaration(
        dataset_id="stage59-" + underlying.lower(),
        filename=filename,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        provider_reference="qa/synthetic-vendor-not-trusted",
        licence_reference="qa/rights-not-authenticated",
        calendar_reference="qa/holiday-calendar-not-authenticated",
        contract_reference="qa/unverified-contract-claim",
        expected_first=START,
        expected_last=START + timedelta(minutes=2),
        dataset_class_claim="SYNTHETIC_SMOKE_FIXTURE",
    )
    return path, contract, declaration, payload


def _summary(result):
    return {
        "dataset_id": result.dataset_id,
        "symbol": result.symbol,
        "count": result.count,
        "expected_slots": result.expected_slots,
        "timeframe": result.timeframe,
        "file_sha256": result.file_sha256,
        "licence_authenticated": result.licence_authenticated,
        "vendor_identity_authenticated": result.vendor_identity_authenticated,
        "exchange_calendar_authenticated": result.exchange_calendar_authenticated,
        "real_orderbook_depth_present": result.real_orderbook_depth_present,
        "approved_for_strategy_promotion": result.approved_for_strategy_promotion,
        "live_orders_transmitted": result.live_orders_transmitted,
        "production_ready": result.production_ready,
    }


def main() -> int:
    with TemporaryDirectory(prefix="titan-stage59-synthetic-history-") as directory:
        root = Path(directory)
        calendar = nse_equity_derivatives_baseline()
        cases = {}
        for underlying in ("NIFTY", "BANKNIFTY"):
            folder = root / underlying.lower()
            path, contract, manifest, original = _case(folder, underlying)
            inspected = preflight_stage59_futures_csv(
                folder, declaration=manifest, contract=contract, calendar=calendar,
            )
            cases[underlying.lower()] = _summary(inspected)
            if underlying == "NIFTY":
                path.write_bytes(original + b"tampered")
                try:
                    preflight_stage59_futures_csv(
                        folder, declaration=manifest, contract=contract,
                        calendar=calendar,
                    )
                    tamper_denied = False
                except Stage59HistoryBlocked:
                    tamper_denied = True
                lines = original.splitlines()
                missing = b"\n".join((lines[0], lines[1], lines[3])) + b"\n"
                path.write_bytes(missing)
                missing_manifest = replace(
                    manifest, expected_sha256=hashlib.sha256(missing).hexdigest(),
                )
                try:
                    preflight_stage59_futures_csv(
                        folder, declaration=missing_manifest, contract=contract,
                        calendar=calendar,
                    )
                    missing_denied = False
                except Stage59HistoryBlocked:
                    missing_denied = True

        data = {
            "mode": "STAGE59_SYNTHETIC_FUTURES_HISTORY_PREFLIGHT_ONLY",
            "nifty": cases["nifty"],
            "banknifty": cases["banknifty"],
            "tampered_file_denied": tamper_denied,
            "missing_minute_denied": missing_denied,
            "option_history_uses_existing_stage26_stage44_preflights": True,
            "live_orders_transmitted": 0,
            "production_ready": False,
        }
        print(json.dumps(data, indent=2, sort_keys=True, allow_nan=False))
        return 0 if all((
            cases["nifty"]["count"] == 3,
            cases["banknifty"]["count"] == 3,
            tamper_denied, missing_denied,
            not cases["nifty"]["licence_authenticated"],
            not cases["banknifty"]["production_ready"],
        )) else 2


if __name__ == "__main__":
    raise SystemExit(main())
