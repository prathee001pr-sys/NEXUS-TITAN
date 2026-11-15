"""Stage27 synthetic-only tests for user-style NIFTY 50 daily CSV ingestion."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from nexus_titan.data.nifty_spot_daily import (
    NiftySpotDailyImportError, import_nifty_spot_daily_csv,
)
from nexus_titan.data.canonical import load_canonical_data

ROOT = Path(__file__).resolve().parents[1]
HEADER = "Date ,Open ,High ,Low ,Close ,Shares Traded ,Turnover (₹ Cr)\n"
# Not user-uploaded data; all 3 prices are regression-only arbitrary examples.
ROWS = (
    "03-FEB-2026,100,103,99,102,100000,200.40\n",
    "02-FEB-2026,101,103,99,100,90000,150.00\n",
    "01-FEB-2026,99,102,98,101,80000,190.25\n",
)
SPECIAL = frozenset({date(2026,2,1)})


def _source(tmp_path, *, data=None):
    path=tmp_path/"synthetic-nifty-daily.csv"
    path.write_text(data if data is not None else HEADER+"".join(ROWS),encoding="utf-8-sig")
    return path


def _load(path,**kwargs):
    return import_nifty_spot_daily_csv(path,declared_weekend_sessions=SPECIAL,**kwargs)


def _run_cli(csv_path,*args):
    return subprocess.run(
        [sys.executable,str(ROOT/"scripts"/"import_nifty_spot_daily.py"),
         "--csv",str(csv_path),*args],
        cwd=ROOT,text=True,capture_output=True,timeout=30,check=False,
    )


def test_descending_source_normalizes_to_chronological_utc_aware_candles(tmp_path):
    src=_source(tmp_path)
    data=_load(src)
    assert data.raw_row_count==3
    assert data.input_order=="newest_first"
    assert data.earliest_date.isoformat()=="2026-02-01"
    assert data.latest_date.isoformat()=="2026-02-03"
    assert tuple(c.close for c in data.canonical_candles)==(101.0,100.0,102.0)
    assert data.canonical_candles[0].timestamp=="2026-02-01T15:30:00+05:30"
    assert data.canonical_candles[0].symbol=="NIFTY"
    assert data.canonical_candles[0].interval=="1d"
    assert data.canonical_candles[0].volume==80000.0
    assert data.explicitly_declared_weekend_sessions == (date(2026,2,1),)
    assert data.missing_weekdays_without_official_calendar == 0
    assert data.source_provenance_authenticated is False
    assert data.option_chain_coverage_verified is False
    assert data.futures_contract_coverage_verified is False
    assert data.strategy_promotion_allowed is False
    assert data.live_orders_transmitted == 0


def test_chronological_file_is_accepted_without_reversal(tmp_path):
    src=_source(tmp_path,data=HEADER+"".join(reversed(ROWS)))
    data=_load(src)
    assert data.input_order=="oldest_first"
    assert tuple(c.close for c in data.canonical_candles)==(101,100,102)


def test_default_weekend_is_fail_closed_not_auto_whitelisted(tmp_path):
    src=_source(tmp_path)
    with pytest.raises(NiftySpotDailyImportError,match="weekend session"):
        import_nifty_spot_daily_csv(src)


def test_declared_weekend_does_not_claim_verified_calendar(tmp_path):
    data=_load(_source(tmp_path))
    assert not data.source_provenance_authenticated
    assert data.explicitly_declared_weekend_sessions==(date(2026,2,1),)


def test_source_file_is_not_changed_or_committed_by_ingestion(tmp_path):
    src=_source(tmp_path)
    before=src.read_bytes()
    first=_load(src)
    second=_load(src)
    assert first==second
    assert src.read_bytes()==before
    assert first.input_sha256==hashlib.sha256(before).hexdigest()


def test_expected_sha_mismatch_blocks_all_rows(tmp_path):
    src=_source(tmp_path)
    with pytest.raises(NiftySpotDailyImportError,match="checksum mismatch"):
        _load(src,expected_sha256="0"*64)


@pytest.mark.parametrize("wrong_line,phrase", [
    ("03-FEB-2026,100,99,98,102,100000,200.40\n","invalid OHLC"),
    ("03-FEB-2026,100,103,99,inf,100000,200.40\n","nonfinite"),
    ("03-FEB-2026,100,103,99,-2,100000,200.40\n","negative"),
    ("03-FEB-2026,100,103,99,102,-10,200.40\n","Shares Traded"),
    ("03-FEB-2026,100,103,99,102,100000,-10\n","negative"),
    ("03-FEB-2026,100,103,99,102,100000,\n","invalid Turnover"),
    ("03-FEB-2026,100,103,99,102,100000,200.40,extra\n","extra CSV"),
    ("invalid,100,103,99,102,100000,200.40\n","expected DD-MON"),
])
def test_bad_price_or_source_record_rejected(tmp_path,wrong_line,phrase):
    src=_source(tmp_path,data=HEADER+wrong_line+"".join(ROWS[1:]))
    with pytest.raises(NiftySpotDailyImportError,match=phrase):
        _load(src)


def test_duplicate_date_rejected(tmp_path):
    src=_source(tmp_path,data=HEADER+ROWS[0]+ROWS[0]+ROWS[2])
    with pytest.raises(NiftySpotDailyImportError,match="duplicate"):
        _load(src)


def test_jumbled_date_order_is_rejected(tmp_path):
    src=_source(tmp_path,data=HEADER+ROWS[1]+ROWS[0]+ROWS[2])
    with pytest.raises(NiftySpotDailyImportError,match="strictly increasing or strictly decreasing"):
        _load(src)


def test_unexpected_duplicate_or_missing_header_blocks(tmp_path):
    src=_source(tmp_path,data=HEADER.replace("Low ","High ")+"".join(ROWS))
    with pytest.raises(NiftySpotDailyImportError,match="exactly seven"):
        _load(src)
    src.write_text("Date,Open,High,Low,Close,Shares Traded\n"+"".join(ROWS),encoding="utf-8")
    with pytest.raises(NiftySpotDailyImportError,match="exactly seven"):
        _load(src)


def test_no_candle_or_only_one_rejected(tmp_path):
    src=_source(tmp_path,data=HEADER+ROWS[0])
    with pytest.raises(NiftySpotDailyImportError,match="At least two"):
        _load(src)
    src.write_text(HEADER,encoding="utf-8")
    with pytest.raises(NiftySpotDailyImportError,match="At least two"):
        _load(src)


def test_symlink_source_disallowed(tmp_path):
    src=_source(tmp_path)
    link=tmp_path/"linked.csv"
    link.symlink_to(src)
    with pytest.raises(NiftySpotDailyImportError,match="non-symlink"):
        _load(link)


def test_reject_bad_resource_limits(tmp_path):
    src=_source(tmp_path)
    for size in (0,1,True,-1,50001):
        with pytest.raises(NiftySpotDailyImportError,match="max_rows"):
            _load(src,max_rows=size)
    with pytest.raises(NiftySpotDailyImportError,match="max_rows"):
        _load(src,max_rows=2)


def test_date_gaps_are_counted_but_not_mistaken_for_verified_holidays(tmp_path):
    rows=(
      "09-FEB-2026,105,106,103,104,1000,10\n",
      "03-FEB-2026,100,102,99,101,1000,10\n"
    )
    src=_source(tmp_path,data=HEADER+"".join(rows))
    data=import_nifty_spot_daily_csv(src)
    assert data.missing_weekdays_without_official_calendar==3
    assert not data.source_provenance_authenticated


def test_cli_accepts_declared_weekend_and_safe_exclusive_normalized_csv(tmp_path):
    src=_source(tmp_path)
    normalized=tmp_path/"canonical.csv"
    proc=_run_cli(src,"--special-session","2026-02-01","--normalized-out",str(normalized))
    assert proc.returncode==0,proc.stderr
    report=json.loads(proc.stdout)
    assert report["mode"]=="NIFTY_SPOT_DAILY_RESEARCH_ONLY"
    assert report["rows"]==3
    assert report["input_order"]=="newest_first"
    assert report["not_a_tradable_index_execution_backtest"]
    assert report["valid_options_or_futures_history"] is False
    assert report["source_provenance_authenticated"] is False
    assert report["live_orders_transmitted"] == 0
    candles,check=load_canonical_data(normalized,symbol="NIFTY",interval="1d")
    assert check.is_valid
    assert tuple(x.close for x in candles)==(101.0,100.0,102.0)
    assert candles[0].timestamp.endswith("+00:00")


def test_cli_never_overwrites_existing_output_or_original_source(tmp_path):
    src=_source(tmp_path)
    out=tmp_path/"exist.csv"
    out.write_text("KEEP ME",encoding="utf-8")
    proc=_run_cli(src,"--special-session","2026-02-01","--normalized-out",str(out))
    assert proc.returncode==2
    assert out.read_text(encoding="utf-8")=="KEEP ME"
    assert proc.stdout==""
    src_original=src.read_bytes()
    proc=_run_cli(src,"--special-session","2026-02-01","--normalized-out",str(src))
    assert proc.returncode==2
    assert src.read_bytes()==src_original


def test_cli_denies_weekend_without_operator_declaration(tmp_path):
    proc=_run_cli(_source(tmp_path))
    assert proc.returncode==2
    assert "weekend" in proc.stderr
    assert proc.stdout==""


def test_cli_fails_for_forged_digest(tmp_path):
    proc=_run_cli(_source(tmp_path),"--special-session","2026-02-01","--sha256","0"*64)
    assert proc.returncode==2
    assert "checksum mismatch" in proc.stderr
