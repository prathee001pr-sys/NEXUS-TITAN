from __future__ import annotations

import hashlib
import pytest
from nexus_titan.data.stage154_real_data_validation import inspect_real_market_csv

HEADER = 'timestamp,open,high,low,close,volume\n'
ROW = '2026-11-12T09:15:00+05:30,100,105,99,102,200\n'


def test_valid_snapshot(tmp_path):
    p = tmp_path / 'market.csv'
    data = (HEADER + ROW).encode()
    p.write_bytes(data)
    receipt = inspect_real_market_csv(p)
    assert receipt.accepted
    assert receipt.sha256 == hashlib.sha256(data).hexdigest()
    assert receipt.rows_checked == 1
    assert receipt.warnings


def test_naive_timestamp_uses_ist(tmp_path):
    p = tmp_path / 'market.csv'
    p.write_text(HEADER + ROW.replace('+05:30', ''))
    assert inspect_real_market_csv(p).accepted


@pytest.mark.parametrize('timestamp', [
    '2026-11-12T08:59:00+05:30', '2026-11-12T15:30:00+05:30',
    '2026-11-14T10:00:00+05:30',
])
def test_outside_cash_session_rejected(tmp_path, timestamp):
    p = tmp_path / 'market.csv'
    p.write_text(HEADER + ROW.replace('2026-11-12T09:15:00+05:30', timestamp))
    assert not inspect_real_market_csv(p).accepted


def test_symlink_rejected(tmp_path):
    p = tmp_path / 'market.csv'
    p.write_text(HEADER + ROW)
    link = tmp_path / 'link.csv'
    link.symlink_to(p)
    assert not inspect_real_market_csv(link).accepted


def test_invalid_ohlc_rejected(tmp_path):
    p = tmp_path / 'market.csv'
    p.write_text(HEADER + ROW.replace(',105,', ',90,'))
    assert not inspect_real_market_csv(p).accepted


def test_empty_and_missing_rejected(tmp_path):
    p = tmp_path / 'empty.csv'
    p.touch()
    assert not inspect_real_market_csv(p).accepted
    assert not inspect_real_market_csv(tmp_path / 'missing.csv').accepted


def test_oversized_rejected(tmp_path):
    p = tmp_path / 'market.csv'
    p.write_text(HEADER + ROW)
    assert not inspect_real_market_csv(p, max_bytes=10).accepted


@pytest.mark.parametrize('limit', [0, -1, True])
def test_invalid_max_bytes(tmp_path, limit):
    with pytest.raises(ValueError):
        inspect_real_market_csv(tmp_path / 'market.csv', max_bytes=limit)
