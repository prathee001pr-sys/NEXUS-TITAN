"""Strict offline CSV ingestion for point-in-time NSE option-chain research.

The importer never grants live trading, strategy promotion, licence rights, or
vendor identity. SHA-256 only binds an operator-provided checksum to these bytes.
No broker/network access, order placement, or database writes occur.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.derivatives.chain_and_settlement import OptionChainQuote
from nexus_titan.derivatives.chain_integrity import inspect_verified_option_chain


COLUMNS = (
    "timestamp", "symbol", "underlying", "expiry_date", "strike",
    "option_type", "bid", "ask", "ltp", "volume", "open_interest",
    "underlying_spot", "lot_size",
)


class OptionChainIngestionError(ValueError):
    """The entire input snapshot was rejected; no quotes were released."""


@dataclass(frozen=True, slots=True)
class ResearchOptionChainSnapshot:
    """All-or-nothing, offline-only validated research data and audit evidence."""

    quotes: tuple[OptionChainQuote, ...]
    sha256: str
    observed_at: datetime
    provider_reference: str
    licence_evidence_reference: str
    calendar_evidence_reference: str
    contract_evidence_reference: str
    approved_for_strategy_promotion: bool = False


def _positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _required_reference(name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise OptionChainIngestionError(f"{name} must be an explicit non-empty reference")


def _parse_row(row: dict[str, str], number: int) -> OptionChainQuote:
    try:
        if any(not isinstance(v, str) or not v.strip() for v in row.values()):
            raise ValueError("missing or blank field")
        values = {key: row[key].strip() for key in COLUMNS}
        return OptionChainQuote(
            timestamp=values["timestamp"],
            symbol=values["symbol"],
            underlying=values["underlying"],
            expiry_date=values["expiry_date"],
            strike=float(values["strike"]),
            option_type=values["option_type"],  # type: ignore[arg-type]
            bid=float(values["bid"]),
            ask=float(values["ask"]),
            ltp=float(values["ltp"]),
            volume=int(values["volume"]),
            open_interest=int(values["open_interest"]),
            underlying_spot=float(values["underlying_spot"]),
            lot_size=int(values["lot_size"]),
        )
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise OptionChainIngestionError(f"CSV row {number}: {exc}") from exc


def load_research_option_chain_csv(
    path: str | Path,
    *,
    expected_sha256: str,
    contract: PointInTimeContractSpec,
    observed_at: datetime,
    calendar: MarketCalendar,
    provider_reference: str,
    licence_evidence_reference: str,
    calendar_evidence_reference: str,
    max_file_bytes: int = 8 * 1024 * 1024,
    max_rows: int = 20_000,
    max_quote_age_seconds: float = 120.0,
) -> ResearchOptionChainSnapshot:
    """Load an immutable, structurally screened single-snapshot CSV (offline).

    All conditions must pass before any quotes are returned. Explicit calendar
    overrides/holidays are caller supplied and must be independently reviewed.
    Provider/licence/contract references are recorded declarations, NOT proofs.
    Only an NSE/Asia-Kolkata options snapshot is accepted by this adapter.
    """
    _positive_int("max_file_bytes", max_file_bytes)
    _positive_int("max_rows", max_rows)
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise OptionChainIngestionError("expected_sha256 must contain 64 hexadecimal characters")
    for key, value in (
        ("provider_reference", provider_reference),
        ("licence_evidence_reference", licence_evidence_reference),
        ("calendar_evidence_reference", calendar_evidence_reference),
    ):
        _required_reference(key, value)
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise OptionChainIngestionError("Reviewed Asia/Kolkata MarketCalendar is required")
    if not isinstance(contract, PointInTimeContractSpec) or contract.exchange.strip().upper() != "NSE":
        raise OptionChainIngestionError("NSE point-in-time contract metadata is required")
    if not isinstance(observed_at, datetime) or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise OptionChainIngestionError("observed_at must be timezone-aware")
    if not calendar.is_open(observed_at):
        raise OptionChainIngestionError("Observation is outside the supplied exchange session")

    location = Path(path)
    if not location.is_file():
        raise OptionChainIngestionError("Option-chain CSV is missing")
    if location.stat().st_size > max_file_bytes:
        raise OptionChainIngestionError("Option-chain CSV exceeds max_file_bytes")
    payload = location.read_bytes()
    if len(payload) > max_file_bytes:
        raise OptionChainIngestionError("Option-chain CSV exceeds max_file_bytes")
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, expected_sha256.lower()):
        raise OptionChainIngestionError("SHA-256 checksum mismatch: source bytes changed")
    try:
        source = io.StringIO(payload.decode("utf-8-sig"), newline="")
        reader = csv.DictReader(source, restkey="__EXTRA_FIELDS__", restval=None, strict=True)
        header = reader.fieldnames
        if header is None or len(header) != len(COLUMNS) or set(header) != set(COLUMNS):
            raise OptionChainIngestionError("CSV header must have each required column exactly once")
        rows: list[OptionChainQuote] = []
        for number, row in enumerate(reader, start=2):
            if number - 1 > max_rows:
                raise OptionChainIngestionError("Option-chain CSV exceeds max_rows")
            if "__EXTRA_FIELDS__" in row:
                raise OptionChainIngestionError(f"CSV row {number}: unexpected extra columns")
            quote = _parse_row(row, number)
            try:
                when = datetime.fromisoformat(quote.timestamp.replace("Z", "+00:00"))
                if when.tzinfo is None or when.utcoffset() is None:
                    raise ValueError("missing timezone")
            except (TypeError, ValueError, AttributeError) as exc:
                raise OptionChainIngestionError(f"CSV row {number}: invalid timezone-aware timestamp") from exc
            if not calendar.is_open(when):
                raise OptionChainIngestionError(f"CSV row {number}: quote outside exchange session")
            rows.append(quote)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise OptionChainIngestionError(f"Cannot parse strict UTF-8 CSV: {exc}") from exc

    result = inspect_verified_option_chain(
        tuple(rows), contract, observed_at=observed_at,
        max_quote_age_seconds=max_quote_age_seconds,
    )
    if not result.is_valid:
        raise OptionChainIngestionError("Option-chain integrity gate rejected snapshot: " + "; ".join(result.issues))

    # Always research-only. Never infer licensing, promotion, or execution rights
    # from references, matching hashes, or a green structural validator.
    return ResearchOptionChainSnapshot(
        quotes=tuple(rows),
        sha256=digest,
        observed_at=observed_at,
        provider_reference=provider_reference.strip(),
        licence_evidence_reference=licence_evidence_reference.strip(),
        calendar_evidence_reference=calendar_evidence_reference.strip(),
        contract_evidence_reference=str(contract.source_reference).strip(),
    )
