"""Stage112: date-effective local F&O contract-master structural preflight.

A contract list can be self-consistent without being an exchange-authenticated
master. No implicit lot size, strike interval, expiry weekday or session hours.
No network, broker orders, persistent writes, or live-trading authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from hashlib import sha256
import json
import re


class Stage112Blocked(ValueError):
    pass


_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{1,119}\Z", re.ASCII)
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX = 10**12


@dataclass(frozen=True, slots=True)
class Stage112Contract:
    contract_id: str
    underlying: str
    instrument: str  # FUTIDX, OPTIDX
    expiry_date: str
    option_type: str  # NA, CE, PE
    strike_paise: int  # 0 for futures, positive for options
    lot_size: int
    tick_size_paise: int
    effective_from: str
    effective_through: str
    currency: str = "INR"
    source: str = "LOCAL_UNVERIFIED_MASTER"
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage112Master:
    underlying: str
    trading_date: str
    currency: str
    contracts: tuple[Stage112Contract, ...]
    master_sha256: str
    contract_count: int
    official_contract_master_verified: bool = False
    exchange_expiry_verified: bool = False
    official_lot_history_verified: bool = False
    live_trading_enabled: bool = False
    verdict: str = "LOCAL_CONTRACT_STRUCTURE_ONLY_NO_GO"


def _date(value: object) -> date:
    if type(value) is not str or len(value) != 10:
        raise Stage112Blocked("Expected canonical YYYY-MM-DD date")
    try:
        d = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise Stage112Blocked("Invalid contract date") from exc
    if d.isoformat() != value or not 2000 <= d.year <= 2100:
        raise Stage112Blocked("Contract date outside supported bounds")
    return d


def _positive(value: object, limit: int = _MAX, zero: bool = False) -> bool:
    return type(value) is int and (0 if zero else 1) <= value <= limit


def review_stage112_master(
    contracts: tuple[Stage112Contract, ...] | list[Stage112Contract],
    *, trading_date: str,
) -> Stage112Master:
    if type(contracts) not in (tuple, list) or not 1 <= len(contracts) <= 200:
        raise Stage112Blocked("Expected 1 to 200 explicit contract specifications")
    day = _date(trading_date)
    # Weekends are not assumed closed: special-session evidence needs a separate
    # official calendar gate, and this structural report stays NO-GO regardless.
    underlying = None
    ids: set[str] = set()
    terms: set[tuple[str, str, int]] = set()
    for item in contracts:
        if type(item) is not Stage112Contract:
            raise Stage112Blocked("Exact immutable contract type required")
        if (type(item.contract_id) is not str or not _ID.fullmatch(item.contract_id)
            or type(item.underlying) is not str or item.underlying not in ("NIFTY", "BANKNIFTY")
            or item.currency != "INR" or item.source not in (
                "LOCAL_UNVERIFIED_MASTER", "SYNTHETIC_TEST_MASTER")
            or item.live_trading_enabled is not False):
            raise Stage112Blocked("Untrusted contract identity, currency or authority")
        if underlying is None:
            underlying = item.underlying
        if item.underlying != underlying:
            raise Stage112Blocked("Mixed underlying master is not one bounded unit")
        expiry = _date(item.expiry_date)
        start, end = _date(item.effective_from), _date(item.effective_through)
        if not start <= day <= end or expiry < day or start > end:
            raise Stage112Blocked("Contract not effective at trading date or already expired")
        if not _positive(item.lot_size, 100_000) or not _positive(item.tick_size_paise, 100_000):
            raise Stage112Blocked("Unbounded or missing lot and tick size")
        if item.instrument == "FUTIDX":
            if item.option_type != "NA" or item.strike_paise != 0:
                raise Stage112Blocked("Futures cannot contain option strike/type")
        elif item.instrument == "OPTIDX":
            if item.option_type not in ("CE", "PE") or not _positive(item.strike_paise):
                raise Stage112Blocked("Index option needs CE/PE and positive strike")
        else:
            raise Stage112Blocked("Only explicit index futures/options supported")
        if item.contract_id in ids:
            raise Stage112Blocked("Duplicate vendor contract key")
        identity = (item.expiry_date, item.option_type,
                    item.strike_paise if item.instrument == "OPTIDX" else -1)
        if identity in terms:
            raise Stage112Blocked("Duplicate expiry/strike/option-side in one master")
        ids.add(item.contract_id)
        terms.add(identity)
    assert underlying is not None
    ordered = tuple(sorted(contracts, key=lambda x: x.contract_id))
    payload = ["STAGE112_UNVERIFIED_CONTRACT_MASTER_V1", trading_date,
               [asdict(item) for item in ordered]]
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                               allow_nan=False).encode()).hexdigest()
    return Stage112Master(underlying, trading_date, "INR", ordered, digest,
                          len(ordered))
