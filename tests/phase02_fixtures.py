"""Only local fabricated 2026-11-10 quotes; NEVER a claim of market data."""
from dataclasses import replace
from hashlib import sha256
from nexus_titan.operations.stage112_fo_contract_master import Stage112Contract,review_stage112_master
from nexus_titan.operations.stage113_fo_source_provenance import Stage113SourceManifest,review_stage113_csv
from nexus_titan.operations.stage114_option_asof_alignment import Stage114Clock,review_stage114_asof
from nexus_titan.operations.stage115_session_coverage import Stage115Session,review_stage115_coverage

DAY="2026-11-10"
EXPIRY="2026-11-24"

def spec(side, *, cid=None, source="SYNTHETIC_TEST_MASTER"):
    return Stage112Contract(cid or f"NIFTY-{EXPIRY}-{side}-2500000",
        "NIFTY","OPTIDX",EXPIRY,side,2500000,50,5,"2026-11-01",EXPIRY,
        source=source)

def future():
    return Stage112Contract(f"NIFTY-{EXPIRY}-FUT","NIFTY","FUTIDX",EXPIRY,"NA",0,
        50,5,"2026-11-01",EXPIRY,source="SYNTHETIC_TEST_MASTER")

def contracts():
    return (spec("CE"),spec("PE"))

def csv_payload(*, minutes=3, drops=(), extras=(), quotes=None, order="forward"):
    head="contract_id,observed_at_ist,bid_paise,ask_paise,volume,open_interest\n"
    if quotes is not None:
        return (head + "\n".join(quotes)+"\n").encode()
    lines=[]
    for i in range(minutes):
        stamp=f"{DAY}T09:{15+i:02d}:00+05:30"
        for c in contracts():
            if (c.option_type,i) in drops:
                continue
            bid=1000 if c.option_type=="CE" else 2000
            lines.append(f"{c.contract_id},{stamp},{bid},{bid+5},100,500")
    lines.extend(extras)
    if order=="reverse":lines=lines[::-1]
    return (head+"\n".join(lines)+"\n").encode()

def manifest(raw,**kw):
    x=Stage113SourceManifest("synthetic-quote-chunk","sim.csv","MOCK_PROVIDER",
       sha256(raw).hexdigest(),len(raw),f"{DAY}T18:00:00+05:30",
       rights_status="SYNTHETIC_TEST_ONLY",source_kind="SYNTHETIC_FIXTURE_ONLY")
    return replace(x,**kw)

def base(raw=None):
    raw=raw if raw is not None else csv_payload()
    items=contracts()
    master=review_stage112_master(items,trading_date=DAY)
    m=manifest(raw)
    data=review_stage113_csv(master,m,raw)
    clock=Stage114Clock(f"{DAY}T09:17:00+05:30",60,60)
    sess=Stage115Session(DAY,f"{DAY}T09:15:00+05:30",f"{DAY}T09:18:00+05:30")
    return items,master,m,raw,data,clock,sess
