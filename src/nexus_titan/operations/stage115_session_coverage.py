"""Stage115: bounded quote-by-minute coverage against *declared* session hours.

Trading calendars, holidays, special sessions and expiry timing are NOT
inferred or authenticated. Coverage of a file chunk is not historical coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
import json

from .stage112_fo_contract_master import Stage112Master
from .stage113_fo_source_provenance import Stage113Dataset, _stamp


class Stage115Blocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Stage115Session:
    trading_date: str
    expected_open_ist: str
    expected_close_ist: str  # exclusive; date-effective and caller declared
    calendar_source: str = "LOCAL_UNVERIFIED_SCHEDULE"
    official_calendar_verified: bool = False
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage115Coverage:
    underlying: str
    trading_date: str
    master_sha256: str
    dataset_sha256: str
    expected_quote_minutes: int
    actual_in_session_quote_minutes: int
    missing_quote_minutes: int
    outside_session_rows: int
    sample_missing: tuple[str,...]
    chunk_coverage_complete: bool
    coverage_sha256: str
    official_calendar_verified: bool = False
    fifteen_year_minute_coverage_verified: bool = False
    independent_data_provider_verified: bool = False
    live_trading_enabled: bool = False
    verdict: str = "UNVERIFIED_SINGLE_CHUNK_COVERAGE_ONLY_NO_GO"


def review_stage115_coverage(master: Stage112Master,dataset: Stage113Dataset,
                             session: Stage115Session) -> Stage115Coverage:
    if (type(master) is not Stage112Master or type(dataset) is not Stage113Dataset
        or type(session) is not Stage115Session):
        raise Stage115Blocked("Exact contract, chunk and session inputs required")
    if (master.verdict != "LOCAL_CONTRACT_STRUCTURE_ONLY_NO_GO"
        or dataset.verdict != "RAW_FILE_STRUCTURAL_INTEGRITY_ONLY_NO_GO"
        or master.master_sha256 != dataset.master_sha256
        or master.trading_date != dataset.trading_date
        or session.trading_date != dataset.trading_date
        or session.calendar_source != "LOCAL_UNVERIFIED_SCHEDULE"
        or session.official_calendar_verified is not False
        or session.live_trading_enabled is not False
        or master.live_trading_enabled is not False or dataset.live_trading_enabled is not False
        or master.official_contract_master_verified is not False
        or master.exchange_expiry_verified is not False
        or master.official_lot_history_verified is not False
        or dataset.provider_authenticated is not False
        or dataset.market_data_license_verified is not False
        or dataset.quote_origin_verified is not False):
        raise Stage115Blocked("Cross-source calendar or authority boundary mismatch")
    try:
        from .stage112_fo_contract_master import review_stage112_master
        if review_stage112_master(master.contracts,trading_date=master.trading_date)!=master:
            raise Stage115Blocked("Master fingerprint mismatch")
        start,end=_stamp(session.expected_open_ist),_stamp(session.expected_close_ist)
    except ValueError as exc:
        raise Stage115Blocked("Bad expected session clock") from exc
    if (start.date().isoformat()!=session.trading_date
        or end.date().isoformat()!=session.trading_date
        or not 0 < (end-start).total_seconds() <= 8*3600):
        raise Stage115Blocked("Expected one-day bounded session with exclusive close")
    expected_minutes=int((end-start).total_seconds()//60)
    ids={c.contract_id for c in master.contracts}
    seen=set()
    outside=0
    for q in dataset.quote_rows:
        if q.contract_id not in ids:
            raise Stage115Blocked("Unexpected contract in quote data")
        t=_stamp(q.observed_at_ist)
        if start<=t<end:
            key=(q.contract_id,t)
            if key in seen:
                raise Stage115Blocked("Duplicate quote minute in data chunk")
            seen.add(key)
        else:
            outside+=1
    missing=[]
    total_expected=expected_minutes*len(ids)
    missing_count=total_expected-len(seen)
    for cid in sorted(ids):
        for i in range(expected_minutes):
            t=start+timedelta(minutes=i)
            if (cid,t) not in seen and len(missing)<12:
                missing.append(f"{cid}@{t.isoformat()}")
    good=missing_count==0 and outside==0
    payload=["STAGE115_UNVERIFIED_SESSION_COVERAGE_V1",master.master_sha256,
             dataset.dataset_sha256,session.expected_open_ist,session.expected_close_ist,
             total_expected,len(seen),missing_count,outside,missing]
    digest=sha256(json.dumps(payload,separators=(",", ":")).encode()).hexdigest()
    return Stage115Coverage(master.underlying,master.trading_date,master.master_sha256,
        dataset.dataset_sha256,total_expected,len(seen),missing_count,outside,
        tuple(missing),good,digest)
