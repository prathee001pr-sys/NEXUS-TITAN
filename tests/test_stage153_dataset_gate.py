from __future__ import annotations

import hashlib

import pytest

from nexus_titan.data.stage153_dataset_gate import inspect_historical_csv

HEADER = 'timestamp,open,high,low,close,volume\n'
ROW = '2026-01-01T09:15:00+05:30,100,105,99,102,200\n'


def test_valid_dataset_receipt(tmp_path):
    p = tmp_path / 'candles.csv'
    payload = (HEADER + ROW).encode()
    p.write_bytes(payload)
    result = inspect_historical_csv(p)
    assert result.accepted
    assert result.rows_checked == 1
    assert result.bytes_checked == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()


def test_invalid_ohlc_rejected(tmp_path):
    p = tmp_path / 'bad.csv'
    p.write_text(HEADER + '2026-01-01T09:15:00+05:30,100,90,99,102,200\n')
    result = inspect_historical_csv(p)
    assert not result.accepted
    assert result.errors


def test_duplicate_timestamp_rejected(tmp_path):
    p = tmp_path / 'duplicate.csv'
    p.write_text(HEADER + ROW + ROW)
    assert not inspect_historical_csv(p).accepted


def test_missing_file_rejected(tmp_path):
    assert not inspect_historical_csv(tmp_path / 'missing.csv').accepted


def test_empty_file_rejected(tmp_path):
    p = tmp_path / 'empty.csv'
    p.touch()
    assert not inspect_historical_csv(p).accepted


def test_oversize_file_rejected(tmp_path):
    p = tmp_path / 'large.csv'
    p.write_text(HEADER + ROW)
    assert not inspect_historical_csv(p, max_bytes=10).accepted


def test_symlink_rejected(tmp_path):
    p = tmp_path / 'real.csv'
    p.write_text(HEADER + ROW)
    link = tmp_path / 'link.csv'
    link.symlink_to(p)
    assert not inspect_historical_csv(link).accepted


@pytest.mark.parametrize('max_bytes', [0, -1, True])
def test_invalid_size_limit(tmp_path, max_bytes):
    with pytest.raises(ValueError):
        inspect_historical_csv(tmp_path / 'anything', max_bytes=max_bytes)
