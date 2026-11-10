"""Stage114: point-in-time quote selection without future leakage.

Selects the most recent quote at or before the declared decision timestamp;
rejects stale, incomplete or internally asynchronous CE/PE chains. Local-only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from hashlib import sha256
import json

from .stage112_fo_contract_master import Stage112Master
from .stage113_fo_source_provenance import Stage113Dataset, Stage113Quote, _stamp


class Stage114Blocked(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Stage114Clock:
    decision_at_ist: str
    max_quote_age_seconds: int = 180
    max_cross_contract_skew_seconds: int = 60
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage114Snapshot:
    underlying: str
    trading_date: str
    decision_at_ist: str
    master_sha256: str
    dataset_sha256: str
    selected_quotes: tuple[Stage113Quote, ...]
    selected_quote_count: int
    maximum_quote_age_seconds: int
    cross_contract_skew_seconds: int
    snapshot_sha256: str
    independent_time_source_verified: bool = False
    market_quote_authenticity_verified: bool = False
    trade_authorized: bool = False
    live_trading_enabled: bool = False
    verdict: str = "LOCAL_POINT_IN_TIME_ONLY_NO_GO"


def review_stage114_asof(master: Stage112Master, dataset: Stage113Dataset,
                         clock: Stage114Clock) -> Stage114Snapshot:
    if (type(master) is not Stage112Master or type(dataset) is not Stage113Dataset
        or type(clock) is not Stage114Clock):
        raise Stage114Blocked("Exact Stage112/113 objects and decision clock required")
    if (master.verdict != "LOCAL_CONTRACT_STRUCTURE_ONLY_NO_GO"
        or dataset.verdict != "RAW_FILE_STRUCTURAL_INTEGRITY_ONLY_NO_GO"
        or master.underlying != dataset.underlying
        or master.trading_date != dataset.trading_date
        or master.master_sha256 != dataset.master_sha256
        or master.live_trading_enabled is not False
        or dataset.live_trading_enabled is not False
        or dataset.provider_authenticated is not False
        or dataset.market_data_license_verified is not False
        or dataset.quote_origin_verified is not False
        or clock.live_trading_enabled is not False
        or type(clock.max_quote_age_seconds) is not int
        or not 0 <= clock.max_quote_age_seconds <= 180
        or type(clock.max_cross_contract_skew_seconds) is not int
        or not 0 <= clock.max_cross_contract_skew_seconds <= 180):
        raise Stage114Blocked("Predecessor, source authority or clock mismatch")
    try:
        from .stage112_fo_contract_master import review_stage112_master
        if review_stage112_master(master.contracts, trading_date=master.trading_date) != master:
            raise Stage114Blocked("Master fingerprint mismatch")
        decision = _stamp(clock.decision_at_ist)
    except ValueError as exc:
        raise Stage114Blocked("Invalid master or timestamp") from exc
    if decision.date().isoformat() != master.trading_date:
        raise Stage114Blocked("Decision clock outside source trading date")
    latest: dict[str, Stage113Quote] = {}
    for q in dataset.quote_rows:
        if type(q) is not Stage113Quote:
            raise Stage114Blocked("Untrusted quote structure")
        t = _stamp(q.observed_at_ist)
        if t <= decision and (q.contract_id not in latest or
                             q.observed_at_ist > latest[q.contract_id].observed_at_ist):
            latest[q.contract_id] = q
    expected = {x.contract_id for x in master.contracts}
    if set(latest) != expected:
        raise Stage114Blocked("Missing complete point-in-time contract coverage")
    selected = tuple(latest[k] for k in sorted(expected))
    times = [_stamp(q.observed_at_ist) for q in selected]
    age = max(int((decision-t).total_seconds()) for t in times)
    skew = int((max(times)-min(times)).total_seconds())
    if age < 0 or age > clock.max_quote_age_seconds or skew > clock.max_cross_contract_skew_seconds:
        raise Stage114Blocked("Stale or asynchronous quote chain")
    by_strike: dict[tuple[str,int],set[str]] = {}
    for spec in master.contracts:
        if spec.instrument == "OPTIDX":
            by_strike.setdefault((spec.expiry_date,spec.strike_paise),set()).add(spec.option_type)
    if not by_strike or any(sides!={"CE","PE"} for sides in by_strike.values()):
        raise Stage114Blocked("Incomplete CE/PE pairs at declared strikes")
    payload = ["STAGE114_ASOF_NO_LOOKAHEAD_V1", master.master_sha256,
               dataset.dataset_sha256, clock.decision_at_ist,age,skew,
               [asdict(q) for q in selected]]
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return Stage114Snapshot(master.underlying,master.trading_date,clock.decision_at_ist,
        master.master_sha256,dataset.dataset_sha256,selected,len(selected),age,skew,digest)
