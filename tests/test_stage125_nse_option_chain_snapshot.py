import csv
import io
import pytest
from nexus_titan.operations.stage125_nse_option_chain_snapshot import inspect_stage125_snapshot, Stage125Blocked

HEADER = "NO TEXT,OI,CHNG IN OI,VOLUME,IV,LTP,CHNG,BID QTY,BID,ASK,ASK QTY,STRIKE,BID QTY,BID,ASK,ASK QTY,CHNG,LTP,IV,VOLUME,CHNG IN OI,OI,NO TEXT"

def sample(strike="25,000.00", bid="100.00", ask="102.00", ltp="101.00"):
    out=io.StringIO(newline="")
    w=csv.writer(out)
    w.writerow(["CALLS","NO TEXT","PUTS"])
    w.writerow(next(csv.reader([HEADER])))
    w.writerow(["", "100", "-", "2", "12", ltp, "-", "20", bid, ask, "20", strike, "20", "90.00", "91.00", "20", "-", "90.50", "12", "4", "-", "150", ""])
    return out.getvalue().encode()

def test_valid_snapshot_is_unverified_no_go():
    x=inspect_stage125_snapshot(sample(),underlying="NIFTY",expiry_date="2026-11-09")
    assert x.strike_count==1 and len(x.quotes)==2
    assert x.observed_at_ist is None and not x.live_trading_enabled
    assert x.verdict.endswith("NO_GO")
    assert x.quotes[0].bid_paise==10000

def test_missing_and_outside_quote_flags():
    x=inspect_stage125_snapshot(sample(bid="-",ask="-"),underlying="NIFTY",expiry_date="2026-11-09")
    assert "MISSING_BID_OR_ASK" in x.quotes[0].quote_flags
    y=inspect_stage125_snapshot(sample(ltp="120.00"),underlying="NIFTY",expiry_date="2026-11-09")
    assert "LTP_OUTSIDE_BID_ASK_NOT_SYNCHRONIZED" in y.quotes[0].quote_flags

@pytest.mark.parametrize("payload", [b"garbage",sample()+b"\nextra",sample().replace(b"25,000.00",b"-"),sample().replace(b"25,000.00",b"-100.00"),sample().replace(b"25,000.00",b"25,000.00\x00")])
def test_bad_input_blocked(payload):
    with pytest.raises(Stage125Blocked):
        inspect_stage125_snapshot(payload,underlying="NIFTY",expiry_date="2026-11-09")

def test_duplicate_strike_blocked():
    p=sample();withrow=p.splitlines(keepends=True)[-1]
    with pytest.raises(Stage125Blocked):
        inspect_stage125_snapshot(p+withrow,underlying="NIFTY",expiry_date="2026-11-09")

@pytest.mark.parametrize("symbol,expiry",[("SENSEX","2026-11-09"),("NIFTY","2026-13-01"),("NIFTY","2026-02-30")])
def test_invalid_metadata_blocked(symbol,expiry):
    with pytest.raises(Stage125Blocked):
        inspect_stage125_snapshot(sample(),underlying=symbol,expiry_date=expiry)
