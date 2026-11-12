from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import pytest
from nexus_titan.data.stage155_session_quality import audit_nse_minute_csv

IST = ZoneInfo('Asia/Kolkata')
DAY = date(2026, 11, 12)

def sample(tmp_path, *, missing=False, duplicate=False):
    p = tmp_path / 'market.csv'
    t = datetime(2026, 11, 12, 9, 15, tzinfo=IST)
    lines = ['timestamp,open,high,low,close,volume']
    for n in range(375):
        if missing and n == 12:
            continue
        lines.append(f'{(t + timedelta(minutes=n)).isoformat()},100,101,99,100,10')
    if duplicate:
        lines.append(lines[-1])
    p.write_text('\n'.join(lines) + '\n')
    return p

def test_full_session(tmp_path):
    r = audit_nse_minute_csv(sample(tmp_path), start=DAY, end=DAY)
    assert r.accepted and r.rows == 375 and r.missing_minutes == 0

def test_missing_minute(tmp_path):
    r = audit_nse_minute_csv(sample(tmp_path, missing=True), start=DAY, end=DAY)
    assert not r.accepted and r.missing_minutes == 1 and r.missing_sessions == ('2026-11-12',)

def test_duplicate(tmp_path):
    assert not audit_nse_minute_csv(sample(tmp_path, duplicate=True), start=DAY, end=DAY).accepted

def test_holiday_override(tmp_path):
    r = audit_nse_minute_csv(sample(tmp_path), start=DAY, end=DAY, holidays=frozenset({DAY}))
    assert not r.accepted and any('outside' in x for x in r.errors)

def test_special_session(tmp_path):
    p = tmp_path / 'special.csv'
    p.write_text('timestamp\n2026-11-12T09:15:00+05:30\n')
    r = audit_nse_minute_csv(p, start=DAY, end=DAY, special_sessions={DAY:(time(9,15),time(9,16))})
    assert r.accepted

def test_invalid_bounds(tmp_path):
    with pytest.raises(ValueError):
        audit_nse_minute_csv(sample(tmp_path), start=DAY, end=date(2026,11,11))
