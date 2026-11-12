from datetime import date, datetime, timezone, timedelta
import hashlib
import pytest
from nexus_titan.data.stage156_snapshot_integrity import verify_snapshot
from nexus_titan.data.stage157_fo_contract_quality import validate_fo_contract
from nexus_titan.data.stage158_source_provenance import validate_provenance
from nexus_titan.data.stage159_backtest_readiness import assess_readiness
from nexus_titan.data.stage160_batch_gate import evaluate_batch

def test_156_valid(tmp_path):
    p=tmp_path/'a.csv'; p.write_bytes(b'hello')
    r=verify_snapshot(p)
    assert r.accepted and r.sha256==hashlib.sha256(b'hello').hexdigest()

def test_156_symlink(tmp_path):
    p=tmp_path/'a'; p.write_bytes(b'hello'); s=tmp_path/'b'; s.symlink_to(p)
    assert not verify_snapshot(s).accepted

def test_156_missing_and_limits(tmp_path):
    assert not verify_snapshot(tmp_path/'missing').accepted
    with pytest.raises(ValueError): verify_snapshot(tmp_path/'missing',max_bytes=True)

def test_157_valid_option():
    assert validate_fo_contract(symbol='NIFTY',instrument='OPT',expiry=date(2026,11,26),asof=date(2026,11,12),strike=25000,option_type='CE',lot_size=65).accepted

def test_157_invalid_option():
    r=validate_fo_contract(symbol='NIFTY',instrument='OPT',expiry=date(2026,11,1),asof=date(2026,11,12),strike=float('nan'),option_type='XX')
    assert not r.accepted and len(r.errors)>=3

def test_157_invalid_future():
    assert not validate_fo_contract(symbol='BANKNIFTY',instrument='FUT',expiry=date(2026,11,26),asof=date(2026,11,12),strike=100).accepted

def test_158_valid():
    r=validate_provenance(provider='source',dataset_id='id',retrieved_at=datetime(2025,1,1,tzinfo=timezone.utc),sha256='a'*64,license_confirmed=True)
    assert r.accepted and r.warnings

def test_158_invalid():
    r=validate_provenance(provider='',dataset_id='',retrieved_at=datetime.now(),sha256='bad')
    assert not r.accepted

def test_159_all_pass():
    r=assess_readiness(snapshot_valid=True,candles_valid=True,session_complete=True,provenance_valid=True,costs_configured=True,lookahead_checked=True)
    assert r.ready

def test_159_fail_closed():
    r=assess_readiness(snapshot_valid=1,candles_valid=True,session_complete=True,provenance_valid=True,costs_configured=True,lookahead_checked=True)
    assert not r.ready and 'snapshot' in r.blockers

def test_160_research_gate():
    r=assess_readiness(snapshot_valid=True,candles_valid=True,session_complete=True,provenance_valid=True,costs_configured=True,lookahead_checked=True)
    assert evaluate_batch(readiness=r,contract_valid=True,source_license_confirmed=True).accepted_for_research
    assert not evaluate_batch(readiness=r,contract_valid=True,source_license_confirmed=True,live_trading_requested=True).accepted_for_research

def test_160_fail_closed():
    r=assess_readiness(snapshot_valid=False,candles_valid=True,session_complete=True,provenance_valid=True,costs_configured=True,lookahead_checked=True)
    assert not evaluate_batch(readiness=r,contract_valid=True,source_license_confirmed=True).accepted_for_research
