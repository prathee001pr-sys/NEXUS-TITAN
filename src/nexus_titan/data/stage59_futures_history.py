"""Stage59: bounded, read-only, point-in-time NSE futures OHLCV CSV preflight.

A provider adapter may normalize its data to the explicit 12-column CSV
contract below. Every declaration (licence, calendar, vendor, contract
source_verified) remains *untrusted*. Structural QA never authenticates a
vendor, real data, order-book depth or rights to strategy promotion.

Existing options-chain Stage26/44 historical preflights remain unchanged.
No network, writes, broker, execution, capital ledger or live trading.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
from nexus_titan.data.quality import inspect_candle_batch
from nexus_titan.data.sessions import MarketCalendar

_COLUMNS = (
    "timestamp", "symbol", "exchange", "segment", "expiry_date", "lot_size",
    "open", "high", "low", "close", "volume", "open_interest",
)
_CSV_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.csv\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-fA-F]{64}\Z", re.ASCII)
_INTEGER = re.compile(r"(0|[1-9][0-9]*)\Z", re.ASCII)
_PRICE = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]{1,8})?\Z", re.ASCII)
_MAX_PRICE = Decimal("1000000000")
_MAX_VOLUME = 1_000_000_000_000
_ALLOWED_INTERVALS = (1, 5, 15, 30)


class Stage59HistoryBlocked(ValueError):
    """Fail-closed historical research preflight refusal; no data released."""


@dataclass(frozen=True, slots=True)
class Stage59FuturesCSVDeclaration:
    dataset_id: str
    filename: str
    expected_sha256: str
    provider_reference: str
    licence_reference: str
    calendar_reference: str
    contract_reference: str
    expected_first: datetime
    expected_last: datetime
    interval_minutes: int = 1
    coverage_mode: Literal["DECLARED_WINDOW", "FULL_SESSION"] = "DECLARED_WINDOW"
    dataset_class_claim: str = "UNVERIFIED_RESEARCH_SAMPLE"


@dataclass(frozen=True, slots=True)
class Stage59FuturesHistory:
    dataset_id: str
    symbol: str
    underlying: str
    expiry_date: str
    timeframe: str
    first_observed_at: datetime
    last_observed_at: datetime
    file_sha256: str
    count: int
    expected_slots: int
    declared_full_session: bool
    candles: tuple[OHLCVCandle, ...]
    # No operator-supplied name, digest, claimed licence or flag can set these.
    vendor_identity_authenticated: bool = False
    licence_authenticated: bool = False
    official_contract_master_authenticated: bool = False
    exchange_calendar_authenticated: bool = False
    source_is_independently_verified_exchange_history: bool = False
    full_exchange_universe_coverage_verified: bool = False
    real_orderbook_depth_present: bool = False
    fill_or_backtest_performance_verified: bool = False
    approved_for_strategy_promotion: bool = False
    live_orders_transmitted: int = 0
    production_ready: bool = False

    def fetch_candles(self, query: CandleQuery) -> tuple[OHLCVCandle, ...]:
        """Provider-independent in-memory MarketDataSource-style read.

        Refuses missing/out-of-window requests rather than quietly returning
        incomplete candles. The inspected CSV itself remains unchanged.
        """
        if not isinstance(query, CandleQuery):
            raise Stage59HistoryBlocked("CandleQuery required")
        if query.symbol != self.symbol or query.timeframe != self.timeframe:
            raise Stage59HistoryBlocked("Query symbol/timeframe mismatches inspected futures data")
        step = timedelta(minutes=int(self.timeframe[:-1]))
        start = self.first_observed_at.astimezone(timezone.utc)
        end = self.last_observed_at.astimezone(timezone.utc) + step
        if query.start < start or query.end > end:
            raise Stage59HistoryBlocked("Query outside structurally inspected declaration window")
        if ((query.start - start) % step or (query.end - start) % step):
            raise Stage59HistoryBlocked("Query must use complete, aligned candle-open intervals")
        expected = (query.end - query.start) // step
        result = tuple(
            bar for bar in self.candles
            if query.start <= bar.timestamp < query.end
        )
        if len(result) != expected:
            raise Stage59HistoryBlocked("Requested in-memory partition is incomplete")
        return result


def _reference(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 512:
        raise Stage59HistoryBlocked("Missing/bounded " + label + " declaration")


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Stage59HistoryBlocked(name + " requires an explicit timezone offset")
    return value.astimezone(timezone.utc)


def _integer(raw: str, label: str, *, upper: int, positive: bool = False) -> int:
    if (not isinstance(raw, str) or len(raw) > 16
            or _INTEGER.fullmatch(raw) is None):
        raise Stage59HistoryBlocked(label + " must be a nonnegative decimal integer")
    n = int(raw)
    if n > upper or (positive and n == 0):
        raise Stage59HistoryBlocked(label + " is outside the bounded range")
    return n


def _price(raw: str, label: str, tick: Decimal) -> Decimal:
    if (not isinstance(raw, str) or len(raw) > 60
            or _PRICE.fullmatch(raw) is None):
        raise Stage59HistoryBlocked("Invalid " + label + " price")
    try:
        v = Decimal(raw)
        if (not v.is_finite() or v <= 0 or v > _MAX_PRICE
                or (v / tick) != (v / tick).to_integral_value()):
            raise Stage59HistoryBlocked("Non-finite, non-positive or non-tick " + label)
        return v
    except (InvalidOperation, ValueError, ArithmeticError) as exc:
        raise Stage59HistoryBlocked("Invalid numeric/tick " + label) from exc


def preflight_stage59_futures_csv(
    root: str | Path, *, declaration: Stage59FuturesCSVDeclaration,
    contract: PointInTimeContractSpec, calendar: MarketCalendar,
    max_file_bytes: int = 2_000_000, max_rows: int = 1000,
) -> Stage59FuturesHistory:
    """Read exactly one declared per-contract, per-session futures CSV.

    Full-session mode proves ONLY the explicit supplied calendar's grid for
    this contract on this single day. It does not prove calendar authenticity,
    complete multi-year market coverage, licensing or real vendor identity.
    """
    if not isinstance(declaration, Stage59FuturesCSVDeclaration):
        raise Stage59HistoryBlocked("Typed futures history declaration required")
    if not isinstance(contract, PointInTimeContractSpec):
        raise Stage59HistoryBlocked("Point-in-time contract metadata required")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise Stage59HistoryBlocked("Explicit India market calendar required")
    if (type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 16_000_000
            or type(max_rows) is not int or not 1 <= max_rows <= 10000):
        raise Stage59HistoryBlocked("Invalid bounded file/row budget")
    for field in (
        "dataset_id", "provider_reference", "licence_reference",
        "calendar_reference", "contract_reference",
    ):
        _reference(getattr(declaration, field), field)
    if (not isinstance(declaration.filename, str)
            or _CSV_NAME.fullmatch(declaration.filename) is None):
        raise Stage59HistoryBlocked("Only one plain CSV basename is accepted")
    if (not isinstance(declaration.expected_sha256, str)
            or _SHA.fullmatch(declaration.expected_sha256) is None):
        raise Stage59HistoryBlocked("Exact SHA-256 byte digest required")
    if (declaration.dataset_class_claim not in (
        "SYNTHETIC_SMOKE_FIXTURE", "UNVERIFIED_RESEARCH_SAMPLE",
        "LICENSED_EXCHANGE_HISTORY",
    ) or declaration.coverage_mode not in ("DECLARED_WINDOW", "FULL_SESSION")):
        raise Stage59HistoryBlocked("Unsupported data-class or coverage claim")
    if (type(declaration.interval_minutes) is not int
            or declaration.interval_minutes not in _ALLOWED_INTERVALS):
        raise Stage59HistoryBlocked("Supported intraday intervals are 1, 5, 15, 30 minutes")
    if (contract.exchange.upper() != "NSE" or contract.segment != "FUTURES"
            or contract.underlying not in ("NIFTY", "BANKNIFTY")
            or not isinstance(contract.expiry_date, date)
            or contract.source_verified is not True
            or contract.source_reference != declaration.contract_reference
            or type(contract.lot_size) is not int or contract.lot_size < 1):
        raise Stage59HistoryBlocked("NSE NIFTY/BANKNIFTY future contract identity/evidence mismatch")
    try:
        tick = Decimal(str(contract.tick_size))
        if not tick.is_finite() or tick <= 0:
            raise Stage59HistoryBlocked("Invalid point-in-time tick")
    except (InvalidOperation, ValueError) as exc:
        raise Stage59HistoryBlocked("Invalid point-in-time tick") from exc

    start = _aware(declaration.expected_first, "expected_first")
    stop = _aware(declaration.expected_last, "expected_last")
    if start > stop:
        raise Stage59HistoryBlocked("Inverted declared candle bounds")
    day = start.astimezone(calendar.zone).date()
    if stop.astimezone(calendar.zone).date() != day:
        raise Stage59HistoryBlocked("A partition cannot span multiple India market days")
    if (not contract.effective_from <= day <= contract.effective_to
            or day > contract.expiry_date):
        raise Stage59HistoryBlocked("Candle day outside point-in-time expiry/effective window")
    step = timedelta(minutes=declaration.interval_minutes)
    delta = stop - start
    if delta % step:
        raise Stage59HistoryBlocked("Declared endpoints are not aligned to interval minutes")
    expected_slots = int(delta // step) + 1
    if not 1 <= expected_slots <= max_rows:
        raise Stage59HistoryBlocked("Expected grid exceeds single-session row cap")

    sessions = calendar.sessions_for_date(day)
    matching = []
    for session in sessions:
        opened = datetime.combine(day, session.opens, calendar.zone).astimezone(timezone.utc)
        closed = datetime.combine(day, session.closes, calendar.zone).astimezone(timezone.utc)
        if opened <= start <= stop and stop + step <= closed:
            matching.append((opened, closed))
    if len(matching) != 1:
        raise Stage59HistoryBlocked("Expected grid outside one configured open NSE session")
    opened, closed = matching[0]
    if (start - opened) % step:
        raise Stage59HistoryBlocked("First candle not aligned to supplied session opening")
    if declaration.coverage_mode == "FULL_SESSION":
        if (len(sessions) != 1 or start != opened or stop + step != closed
                or (closed - opened) % step):
            raise Stage59HistoryBlocked("FULL_SESSION must exactly cover the one supplied full trading session")

    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise Stage59HistoryBlocked("Existing root folder required")
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise Stage59HistoryBlocked("Unlinked existing source folder required")
    base = base.resolve(strict=True)
    target = base / declaration.filename
    if target.is_symlink() or not target.is_file() or target.resolve().parent != base:
        raise Stage59HistoryBlocked("Missing, linked or escaped original CSV")
    try:
        with target.open("rb") as handle:
            payload = handle.read(max_file_bytes + 1)
    except OSError as exc:
        raise Stage59HistoryBlocked("Unable to read the source file") from exc
    if not payload or len(payload) > max_file_bytes:
        raise Stage59HistoryBlocked("Empty or oversized futures CSV")
    checksum = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(checksum, declaration.expected_sha256.lower()):
        raise Stage59HistoryBlocked("Declared SHA-256 checksum mismatch")

    bars: list[OHLCVCandle] = []
    previous: datetime | None = None
    seen: set[datetime] = set()
    try:
        stream = io.StringIO(payload.decode("utf-8-sig"), newline="")
        reader = csv.reader(stream, strict=True)
        header = next(reader, None)
        if tuple(header or ()) != _COLUMNS:
            raise Stage59HistoryBlocked("Exact normalized 12-column futures CSV header required")
        for row_number, fields in enumerate(reader, start=2):
            if len(bars) >= max_rows:
                raise Stage59HistoryBlocked("CSV row cap exceeded")
            if len(fields) != len(_COLUMNS) or any(
                not isinstance(v, str) or "\n" in v or "\r" in v or not v.strip()
                for v in fields
            ):
                raise Stage59HistoryBlocked(f"Row {row_number}: malformed, missing or multiline fields")
            row = dict(zip(_COLUMNS, fields))
            raw_ts = row["timestamp"]
            if len(raw_ts) > 48:
                raise Stage59HistoryBlocked(f"Row {row_number}: timestamp too long")
            try:
                ts = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except ValueError as exc:
                raise Stage59HistoryBlocked(f"Row {row_number}: malformed timestamp") from exc
            instant = _aware(ts, f"Row {row_number} timestamp")
            if instant in seen:
                raise Stage59HistoryBlocked(f"Row {row_number}: duplicate candle timestamp")
            if previous is not None and instant <= previous:
                raise Stage59HistoryBlocked(f"Row {row_number}: out-of-order timestamps")
            if (row["symbol"] != contract.symbol or row["exchange"] != "NSE"
                    or row["segment"] != "FUTURES"
                    or row["expiry_date"] != contract.expiry_date.isoformat()
                    or _integer(row["lot_size"], "lot_size", upper=100000, positive=True) != contract.lot_size):
                raise Stage59HistoryBlocked(f"Row {row_number}: contract identity, expiry or lot size mismatch")
            o = _price(row["open"], "open", tick)
            h = _price(row["high"], "high", tick)
            l = _price(row["low"], "low", tick)
            c = _price(row["close"], "close", tick)
            volume = _integer(row["volume"], "volume", upper=_MAX_VOLUME)
            _integer(row["open_interest"], "open_interest", upper=_MAX_VOLUME)
            try:
                candle = OHLCVCandle(
                    symbol=contract.symbol, timeframe=f"{declaration.interval_minutes}m",
                    timestamp=instant, open=o, high=h, low=l, close=c,
                    volume=volume, source=declaration.provider_reference,
                )
            except ValueError as exc:
                raise Stage59HistoryBlocked(f"Row {row_number}: invalid OHLCV candle") from exc
            seen.add(instant)
            previous = instant
            bars.append(candle)
    except (csv.Error, UnicodeError) as exc:
        raise Stage59HistoryBlocked("Invalid UTF-8 CSV source encoding or syntax") from exc
    if len(bars) != expected_slots:
        raise Stage59HistoryBlocked("Missing/extra declared interval candles")
    expected = tuple(start + i * step for i in range(expected_slots))
    if tuple(b.timestamp for b in bars) != expected:
        raise Stage59HistoryBlocked("Missing, duplicate, out-of-grid or shifted candle opening")
    if not all(calendar.is_open(moment) for moment in expected):
        raise Stage59HistoryBlocked("Candle outside supplied open session")

    # Reuse existing provider-independent candle batch inspector instead
    # of inventing a competing quality schema.
    query = CandleQuery(
        contract.symbol, f"{declaration.interval_minutes}m", start, stop + step,
    )
    report = inspect_candle_batch(tuple(bars), query, calendar=calendar)
    if not report.is_valid:
        raise Stage59HistoryBlocked("Existing session-aware candle quality gate rejected history")
    return Stage59FuturesHistory(
        dataset_id=declaration.dataset_id, symbol=contract.symbol,
        underlying=contract.underlying, expiry_date=contract.expiry_date.isoformat(),
        timeframe=f"{declaration.interval_minutes}m",
        first_observed_at=start, last_observed_at=stop,
        file_sha256=checksum, count=len(bars), expected_slots=expected_slots,
        declared_full_session=(declaration.coverage_mode == "FULL_SESSION"),
        candles=tuple(bars),
    )
