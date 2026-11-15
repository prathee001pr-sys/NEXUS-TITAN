from dataclasses import replace
from hashlib import sha256
import pytest
from test_stage125_nse_option_chain_snapshot import sample
from nexus_titan.operations.stage125_nse_option_chain_snapshot import inspect_stage125_snapshot
from nexus_titan.operations.stage126_snapshot_provenance import Stage126CaptureDeclaration, Stage126Blocked, review_stage126
from nexus_titan.operations.stage127_quote_quality import Stage127Blocked, review_stage127
from nexus_titan.operations.stage128_snapshot_acceptance import inspect_stage128

def declaration(raw, **kw):
    return replace(Stage126CaptureDeclaration('sample.csv',sha256(raw).hexdigest(),None,'LOCAL_UNVERIFIED_FILE'),**kw)

def test_end_to_end_no_go():
    raw=sample()
    a=inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw))
    assert a.quality.quote_count==2 and a.quality.strike_count==1
    assert a.provenance.timestamp_status=='MISSING_CAPTURE_TIMESTAMP'
    assert not a.historical_backtest_approved and not a.paper_trading_approved and not a.live_trading_enabled
    assert a.verdict.endswith('NO_GO')

def test_user_timestamp_not_authenticated():
    raw=sample()
    a=inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw,captured_at_ist='2026-11-09T10:00:00+05:30'))
    assert a.provenance.timestamp_status=='USER_DECLARED_UNVERIFIED_TIMESTAMP'
    assert a.verdict.endswith('NO_GO')

@pytest.mark.parametrize('stamp',['2026-11-09T10:00:00','2026-11-09T10:00:00+00:00','2026-11-10T10:00:00+05:30','bad','2026-11-09T10:00:00.000000+05:30'])
def test_bad_timestamp_rejected(stamp):
    raw=sample()
    with pytest.raises(Stage126Blocked):
        inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw,captured_at_ist=stamp))

def test_mismatch_rejected():
    raw=sample()
    with pytest.raises(Stage126Blocked):
        inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw,declared_sha256='0'*64))

def test_untrusted_claims_rejected():
    raw=sample()
    for kw in ({'independent_authentication':True},{'rights_status':'VERIFIED'},{'live_trading_enabled':True},{'file_basename':'../evil.csv'}):
        with pytest.raises(Stage126Blocked):
            inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw,**kw))

def test_crossed_quote_quality_flag():
    raw=sample(bid='105.00',ask='100.00')
    a=inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw))
    assert ('CROSSED_MARKET',1) in a.quality.flags
    assert a.quality.flagged_quotes>=1

def test_missing_quote_quality_count():
    raw=sample(bid='-',ask='-')
    a=inspect_stage128(raw,underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw))
    assert a.quality.incomplete_quotes==1

def test_mutated_snapshot_rejected():
    raw=sample()
    s=inspect_stage125_snapshot(raw,underlying='NIFTY',expiry_date='2026-11-09')
    p=review_stage126(s,raw,declaration(raw))
    with pytest.raises(Stage127Blocked):
        review_stage127(replace(s,strike_count=2),p)

def test_deterministic_output():
    raw=sample()
    kwargs=dict(underlying='NIFTY',expiry_date='2026-11-09',declaration=declaration(raw))
    assert inspect_stage128(raw,**kwargs)==inspect_stage128(raw,**kwargs)
