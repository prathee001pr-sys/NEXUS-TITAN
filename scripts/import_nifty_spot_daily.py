"""Stage27: research-only import of a user-supplied NSE-style NIFTY spot daily CSV.

Example:
  python scripts/import_nifty_spot_daily.py --csv /path/to/NIFTY.csv \
    --special-session 2026-02-01 --normalized-out /tmp/nifty_spot_canonical.csv

No input is uploaded to GitHub and no broker, real-time data, options P&L or
trading authorization is provided by this converter.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0,str(ROOT / "src"))

from nexus_titan.data.nifty_spot_daily import (
    NiftySpotDailyImportError, import_nifty_spot_daily_csv,
)


def _write_new_csv(out: Path, dataset) -> None:
    if not out.parent.is_dir() or out.is_symlink():
        raise NiftySpotDailyImportError("Normalized CSV output parent must exist and not be a symlink")
    with out.open("x",encoding="utf-8",newline="") as f:
        writer=csv.writer(f)
        writer.writerow(("timestamp","open","high","low","close","volume"))
        for candle in dataset.canonical_candles:
            writer.writerow((
                candle.timestamp,candle.open,candle.high,candle.low,
                candle.close,int(candle.volume),
            ))


def main() -> int:
    parser=argparse.ArgumentParser(description="NEXUS TITAN NIFTY daily spot data structural preflight")
    parser.add_argument("--csv",required=True)
    parser.add_argument("--sha256",default=None,help="Optional independently obtained source checksum")
    parser.add_argument("--special-session",action="append",default=[],
                        help="Operator-declared weekend session YYYY-MM-DD; doesn't authenticate official calendar")
    parser.add_argument("--normalized-out",default=None,help="Optional NEW canonical CSV path; never overwrites")
    args=parser.parse_args()
    try:
        special=frozenset(date.fromisoformat(d) for d in args.special_session)
        dataset=import_nifty_spot_daily_csv(
            args.csv,expected_sha256=args.sha256,declared_weekend_sessions=special,
        )
        # Do not attempt to backtest the index as a cash-settled equity.
        # A compatible and verifiably tradable contract requires separate
        # point-in-time futures/options data and costs.
        if args.normalized_out:
            dest=Path(args.normalized_out)
            if dest.resolve()==Path(args.csv).resolve():
                raise NiftySpotDailyImportError("Output cannot replace input source")
            _write_new_csv(dest,dataset)
        start_close=dataset.rows[0].close
        end_close=dataset.rows[-1].close
        report={
            "mode":"NIFTY_SPOT_DAILY_RESEARCH_ONLY",
            "rows":dataset.raw_row_count,
            "input_source_sha256":dataset.input_sha256,
            "input_order":dataset.input_order,
            "normalized_order":"oldest_first",
            "first_session":dataset.earliest_date.isoformat(),
            "last_session":dataset.latest_date.isoformat(),
            "first_close":start_close,"last_close":end_close,
            "spot_index_close_to_close_return_percent":round((end_close/start_close-1)*100,6),
            "declared_weekend_sessions":[d.isoformat() for d in dataset.explicitly_declared_weekend_sessions],
            "missing_weekdays_not_verified_as_holidays":dataset.missing_weekdays_without_official_calendar,
            "volume_semantics":"aggregate_shares_traded_proxy_NOT_FO_contract_volume",
            "reported_turnover_unit":"INR_crore_NOT_trading_strategy_turnover",
            "source_provenance_authenticated":False,
            "official_holiday_calendar_verified":False,
            "not_a_tradable_index_execution_backtest":True,
            "valid_options_or_futures_history":False,
            "strategy_promotion_allowed":False,"live_orders_transmitted":0,
        }
        print(json.dumps(report,indent=2,sort_keys=True))
        return 0
    except (NiftySpotDailyImportError, ValueError, TypeError, OSError) as e:
        print(f"NIFTY SPOT IMPORT BLOCKED: {type(e).__name__}: {e}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
