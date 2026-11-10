"""Stage113: in-memory, bounded CSV quote-chunk integrity and provenance QA.

SHA-256 proves a payload matches a caller-declared digest, NOT that its source,
license, historical completeness or market quotes are independently verified.
Never opens a path, executes CSV formulas, makes network requests or writes data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import csv
import io
import json
import re

from .stage112_fo_contract_master import Stage112Master, Stage112Blocked


class Stage113Blocked(ValueError):
    pass


_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{1,119}\Z", re.ASCII)
_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.csv\Z", re.ASCII)
_INT = re.compile(r"[0-9]{1,13}\Z", re.ASCII)
_FIELDS = ("contract_id", "observed_at_ist", "bid_paise", "ask_paise", "volume", "open_interest")
_MAX_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Stage113SourceManifest:
    dataset_id: str
    file_basename: str
    declared_provider: str
    raw_sha256: str
    declared_byte_count: int
    recorded_at_ist: str
    rights_status: str = "RIGHTS_UNVERIFIED"
    source_kind: str = "LOCAL_UNVERIFIED_FILE"  # or SYNTHETIC_FIXTURE_ONLY
    independently_authenticated: bool = False
    redistribution_permitted_verified: bool = False
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Stage113Quote:
    contract_id: str
    observed_at_ist: str
    bid_paise: int
    ask_paise: int
    volume: int
    open_interest: int


@dataclass(frozen=True, slots=True)
class Stage113Dataset:
    underlying: str
    trading_date: str
    master_sha256: str
    dataset_id: str
    provider_declared: str
    source_kind: str
    raw_sha256: str
    quote_rows: tuple[Stage113Quote, ...]
    row_count: int
    first_asof_ist: str
    last_asof_ist: str
    dataset_sha256: str
    provider_authenticated: bool = False
    market_data_license_verified: bool = False
    quote_origin_verified: bool = False
    live_trading_enabled: bool = False
    verdict: str = "RAW_FILE_STRUCTURAL_INTEGRITY_ONLY_NO_GO"


def _stamp(s: object) -> datetime:
    if type(s) is not str or len(s) > 40:
        raise Stage113Blocked("Missing bounded canonical IST timestamp")
    try:
        t = datetime.fromisoformat(s)
    except (TypeError, ValueError) as exc:
        raise Stage113Blocked("Invalid quote timestamp") from exc
    if (t.tzinfo is None or t.utcoffset() != timedelta(hours=5, minutes=30)
        or t.isoformat() != s or t.second != 0 or t.microsecond != 0):
        raise Stage113Blocked("Quote timestamp must be exact IST minute")
    return t


def _number(s: object, *, positive=False) -> int:
    if type(s) is not str or not _INT.fullmatch(s):
        raise Stage113Blocked("Only canonical nonnegative integer cells allowed")
    n = int(s)
    if (n == 0 and positive) or n > 10**12:
        raise Stage113Blocked("Quote value outside bounded positive range")
    return n


def review_stage113_csv(
    master: Stage112Master,
    manifest: Stage113SourceManifest,
    raw_bytes: bytes,
) -> Stage113Dataset:
    if (type(master) is not Stage112Master or type(manifest) is not Stage113SourceManifest
        or type(raw_bytes) is not bytes):
        raise Stage113Blocked("Exact typed master, manifest and raw byte payload required")
    if (master.verdict != "LOCAL_CONTRACT_STRUCTURE_ONLY_NO_GO"
        or master.live_trading_enabled is not False
        or master.official_contract_master_verified is not False
        or master.exchange_expiry_verified is not False
        or master.official_lot_history_verified is not False
        or type(master.master_sha256) is not str or not _HASH.fullmatch(master.master_sha256)
        or master.contract_count != len(master.contracts)):
        raise Stage113Blocked("Predecessor master must remain locally unverified")
    try:
        from .stage112_fo_contract_master import review_stage112_master
        if review_stage112_master(master.contracts, trading_date=master.trading_date) != master:
            raise Stage113Blocked("Contract master fingerprint mismatch")
    except Stage112Blocked as exc:
        raise Stage113Blocked("Corrupt predecessor master") from exc
    if (type(manifest.dataset_id) is not str or not _ID.fullmatch(manifest.dataset_id)
        or type(manifest.file_basename) is not str or not _BASENAME.fullmatch(manifest.file_basename)
        or type(manifest.declared_provider) is not str or not _ID.fullmatch(manifest.declared_provider)
        or type(manifest.raw_sha256) is not str or not _HASH.fullmatch(manifest.raw_sha256)
        or type(manifest.declared_byte_count) is not int
        or manifest.rights_status not in ("RIGHTS_UNVERIFIED", "SYNTHETIC_TEST_ONLY")
        or manifest.source_kind not in ("LOCAL_UNVERIFIED_FILE", "SYNTHETIC_FIXTURE_ONLY")
        or manifest.independently_authenticated is not False
        or manifest.redistribution_permitted_verified is not False
        or manifest.live_trading_enabled is not False
        or (manifest.source_kind == "SYNTHETIC_FIXTURE_ONLY")
           != (manifest.rights_status == "SYNTHETIC_TEST_ONLY")):
        raise Stage113Blocked("Unsupported, deceptive or unsafe data provenance")
    if (len(raw_bytes) < 30 or len(raw_bytes) > _MAX_BYTES
        or len(raw_bytes) != manifest.declared_byte_count
        or sha256(raw_bytes).hexdigest() != manifest.raw_sha256):
        raise Stage113Blocked("Raw bytes mismatch caller-declared checksum and size")
    recorded = _stamp(manifest.recorded_at_ist)
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Stage113Blocked("Only UTF-8 CSV accepted") from exc
    if "\x00" in text or len(text.splitlines()) > 10_002:
        raise Stage113Blocked("Binary content or oversized CSV")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if reader.fieldnames is None or tuple(reader.fieldnames) != _FIELDS:
        raise Stage113Blocked("Exact six-column CSV schema required")
    keys = {c.contract_id:c for c in master.contracts}
    rows: list[Stage113Quote] = []
    seen: set[tuple[str,str]] = set()
    lo = hi = None
    try:
        for record in reader:
            if len(rows) >= 10_000 or None in record or None in record.values():
                raise Stage113Blocked("Malformed or oversized quote row")
            cid = record["contract_id"]
            if cid not in keys or (cid, record["observed_at_ist"]) in seen:
                raise Stage113Blocked("Unknown contract or duplicate quote timestamp")
            stamp = _stamp(record["observed_at_ist"])
            if stamp.date().isoformat() != master.trading_date or stamp > recorded:
                raise Stage113Blocked("Quote day / ingest time mismatch")
            from datetime import date
            if stamp.date() > date.fromisoformat(keys[cid].expiry_date):
                raise Stage113Blocked("Quote timestamp beyond contract expiry")
            bid = _number(record["bid_paise"], positive=True)
            ask = _number(record["ask_paise"], positive=True)
            vol = _number(record["volume"])
            oi = _number(record["open_interest"])
            if bid > ask or bid % keys[cid].tick_size_paise or ask % keys[cid].tick_size_paise:
                raise Stage113Blocked("Crossed or off-tick quote")
            if ask > 3 * bid:
                raise Stage113Blocked("Excessively wide local quote")
            rows.append(Stage113Quote(cid, stamp.isoformat(), bid, ask, vol, oi))
            seen.add((cid,stamp.isoformat()))
            lo = stamp if lo is None or stamp < lo else lo
            hi = stamp if hi is None or stamp > hi else hi
    except (csv.Error, ValueError) as exc:
        if isinstance(exc, Stage113Blocked):
            raise
        raise Stage113Blocked("Unable to parse bounded CSV safely") from exc
    if not rows or lo is None or hi is None:
        raise Stage113Blocked("No usable quotes in data chunk")
    payload = ["STAGE113_LOCAL_CSV_V1", master.master_sha256, asdict(manifest),
               [asdict(r) for r in sorted(rows, key=lambda x:(x.observed_at_ist,x.contract_id))]]
    digest = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),allow_nan=False).encode()).hexdigest()
    return Stage113Dataset(master.underlying, master.trading_date, master.master_sha256,
                           manifest.dataset_id, manifest.declared_provider, manifest.source_kind,
                           manifest.raw_sha256, tuple(rows), len(rows), lo.isoformat(), hi.isoformat(),digest)
