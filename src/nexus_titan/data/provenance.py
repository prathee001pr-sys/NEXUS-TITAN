"""Dataset provenance, licensing verification, and point-in-time manifest registry (Workstream D / DATA-011..020)."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

DatasetClass = Literal[
    "SYNTHETIC_SMOKE_FIXTURE",
    "UNVERIFIED_RESEARCH_SAMPLE",
    "LICENSED_EXCHANGE_HISTORY",
]


@dataclass(frozen=True)
class DatasetManifest:
    """Cryptographically hashed dataset provenance and licensing record.

    Evidence references and review metadata are owner-supplied declarations. They
    must point to independently reviewable source documents; this class does not
    authenticate a vendor or licence merely because a string is present.
    """

    dataset_id: str
    file_path: str
    sha256_checksum: str
    vendor_name: str
    licence_id: str
    instrument_symbol: str
    venue: str
    interval: str
    timezone_name: str
    start_timestamp: str
    end_timestamp: str
    bar_count: int
    dataset_class: DatasetClass = "SYNTHETIC_SMOKE_FIXTURE"
    survivorship_bias_free: bool = False
    vendor_corrections_applied: bool = False
    missing_bars_count: int | None = None
    duplicate_bars_count: int = 0
    allowed_for_strategy_promotion: bool = False
    notes: str = ""
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    coverage_verified: bool = False
    vendor_identity_evidence_ref: str = ""
    licence_evidence_ref: str = ""
    coverage_evidence_ref: str = ""
    instrument_metadata_evidence_ref: str = ""
    evidence_reviewed_by: str = ""
    evidence_reviewed_at: str = ""

    def __post_init__(self) -> None:
        required_strings = (
            "dataset_id", "file_path", "sha256_checksum", "vendor_name", "licence_id",
            "instrument_symbol", "venue", "interval", "timezone_name",
        )
        for name in required_strings:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", self.sha256_checksum):
            raise ValueError("sha256_checksum must be exactly 64 hexadecimal characters.")

        if self.dataset_class not in (
            "SYNTHETIC_SMOKE_FIXTURE", "UNVERIFIED_RESEARCH_SAMPLE", "LICENSED_EXCHANGE_HISTORY"
        ):
            raise ValueError("Unsupported dataset_class.")
        for name in ("bar_count", "duplicate_bars_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer.")
        if self.missing_bars_count is not None and (
            isinstance(self.missing_bars_count, bool)
            or not isinstance(self.missing_bars_count, int)
            or self.missing_bars_count < 0
        ):
            raise ValueError("missing_bars_count must be None or a non-negative integer.")
        for name in ("survivorship_bias_free", "vendor_corrections_applied", "allowed_for_strategy_promotion", "coverage_verified"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be a boolean.")

        if self.dataset_class == "SYNTHETIC_SMOKE_FIXTURE" and self.allowed_for_strategy_promotion:
            raise ValueError("A synthetic smoke-test fixture can never be marked allowed_for_strategy_promotion.")
        if self.allowed_for_strategy_promotion:
            required_evidence = (
                "vendor_identity_evidence_ref", "licence_evidence_ref", "coverage_evidence_ref",
                "instrument_metadata_evidence_ref", "evidence_reviewed_by", "evidence_reviewed_at",
            )
            missing = [name for name in required_evidence if not getattr(self, name).strip()]
            if missing:
                raise ValueError("Strategy promotion requires explicit evidence and review metadata: " + ", ".join(missing))
            if (
                self.dataset_class != "LICENSED_EXCHANGE_HISTORY"
                or not self.licence_id.strip()
                or not self.survivorship_bias_free
                or self.missing_bars_count != 0
                or self.duplicate_bars_count != 0
                or not self.coverage_verified
            ):
                raise ValueError(
                    "Strategy promotion requires licensed history, reviewed coverage, "
                    "survivorship-bias-free coverage, and zero missing/duplicate bars."
                )
            _parse_aware_timestamp(self.evidence_reviewed_at, "evidence_reviewed_at")
        _parse_aware_timestamp(self.recorded_at, "recorded_at")
        if self.start_timestamp:
            _parse_aware_timestamp(self.start_timestamp, "start_timestamp")
        if self.end_timestamp:
            _parse_aware_timestamp(self.end_timestamp, "end_timestamp")
        if self.start_timestamp and self.end_timestamp:
            if _parse_aware_timestamp(self.start_timestamp, "start_timestamp") > _parse_aware_timestamp(self.end_timestamp, "end_timestamp"):
                raise ValueError("start_timestamp must not be after end_timestamp.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_aware_timestamp(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid ISO-8601 timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset.")
    return parsed.astimezone(timezone.utc)


def compute_dataset_sha256(path: str | Path) -> str:
    """Return full 64-character SHA-256 hex digest of a dataset file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {file_path}")
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _calendar_coverage_report(candles: tuple[Any, ...], *, symbol: str, interval: str, source: str, calendar: Any):
    """Run the shared session-aware quality inspector over canonical candles."""
    from nexus_titan.data.ohlcv import CandleQuery, OHLCVCandle
    from nexus_titan.data.quality import inspect_candle_batch, timeframe_duration

    if not candles:
        return None
    rows = tuple(
        OHLCVCandle(
            symbol=symbol.upper(), timeframe=interval,
            timestamp=datetime.fromisoformat(item.timestamp),
            open=item.open, high=item.high, low=item.low, close=item.close,
            volume=item.volume, source=source,
        )
        for item in candles
    )
    start = rows[0].timestamp
    end = rows[-1].timestamp + timeframe_duration(interval)
    query = CandleQuery(symbol.upper(), interval, start, end)
    return inspect_candle_batch(rows, query, calendar=calendar)


def verify_dataset_manifest(
    manifest: DatasetManifest,
    path: str | Path | None = None,
    *,
    calendar: Any | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Verify file integrity, data quality and declared evidence gates.

    A checksum proves byte identity only. Vendor identity, licensing, point-in-time
    metadata, calendar accuracy and human review remain external evidence; this
    function never infers them from a vendor name or a licence string.
    """
    from nexus_titan.data.canonical import load_canonical_data

    issues: list[str] = []
    target = Path(path) if path is not None else Path(manifest.file_path)
    if not target.is_file():
        issues.append(f"Dataset file missing on disk: {target}")
        return False, tuple(issues)

    actual_hash = compute_dataset_sha256(target)
    if not hmac.compare_digest(actual_hash.lower(), manifest.sha256_checksum.lower()):
        issues.append("Checksum mismatch: full SHA-256 digest does not match the manifest.")

    if manifest.dataset_class != "LICENSED_EXCHANGE_HISTORY":
        issues.append(f"Dataset class {manifest.dataset_class} is not licensed exchange history.")
    if not manifest.vendor_name.strip() or manifest.vendor_name.upper().startswith("SYNTHETIC"):
        issues.append("A verifiable data vendor must be identified.")
    if not manifest.licence_id.strip() or manifest.licence_id.upper().startswith(("INTERNAL", "QA", "UNKNOWN")):
        issues.append("A valid vendor licence identifier is required.")
    if manifest.dataset_class == "LICENSED_EXCHANGE_HISTORY" and not manifest.allowed_for_strategy_promotion:
        issues.append("The manifest does not explicitly permit strategy promotion.")
    if manifest.allowed_for_strategy_promotion and not manifest.survivorship_bias_free:
        issues.append("Survivorship-bias-free evidence is required for strategy promotion.")
    if manifest.duplicate_bars_count > 0:
        issues.append(f"Dataset contains {manifest.duplicate_bars_count} duplicate timestamp bar(s).")
    if manifest.missing_bars_count is None:
        issues.append("Missing-bar count is unknown; an explicit calendar-based coverage audit is required.")
    elif manifest.missing_bars_count > 0:
        issues.append(f"Dataset declares {manifest.missing_bars_count} missing bar(s).")

    if manifest.allowed_for_strategy_promotion:
        evidence_fields = (
            "vendor_identity_evidence_ref", "licence_evidence_ref", "coverage_evidence_ref",
            "instrument_metadata_evidence_ref", "evidence_reviewed_by", "evidence_reviewed_at",
        )
        for field_name in evidence_fields:
            if not getattr(manifest, field_name).strip():
                issues.append(f"Missing required promotion evidence: {field_name}.")
        if not manifest.coverage_verified:
            issues.append("Coverage review is not marked complete.")

    candles, report = load_canonical_data(
        target, symbol=manifest.instrument_symbol, interval=manifest.interval,
        source_timezone=manifest.timezone_name,
    )
    if not report.is_valid:
        issues.extend(f"CSV validation: {item}" for item in report.errors[:20])
    if len(candles) != manifest.bar_count:
        issues.append(f"Bar-count mismatch: manifest={manifest.bar_count}, actual={len(candles)}.")
    if candles:
        if manifest.start_timestamp and candles[0].timestamp != manifest.start_timestamp:
            issues.append("Start timestamp does not match the manifest.")
        if manifest.end_timestamp and candles[-1].timestamp != manifest.end_timestamp:
            issues.append("End timestamp does not match the manifest.")
    elif manifest.bar_count > 0:
        issues.append("Manifest declares bars but no valid candles were parsed.")

    if manifest.coverage_verified:
        if calendar is None:
            issues.append("Coverage is marked verified but no market calendar was supplied for independent re-check.")
        elif report.is_valid and candles:
            try:
                coverage = _calendar_coverage_report(
                    candles, symbol=manifest.instrument_symbol, interval=manifest.interval,
                    source=manifest.vendor_name, calendar=calendar,
                )
                if coverage is None or not coverage.is_valid:
                    issues.append("Calendar-based coverage re-check failed: gaps, out-of-session bars, or identity/bounds errors detected.")
                elif manifest.missing_bars_count != 0:
                    issues.append("Coverage re-check found no gaps but manifest missing_bars_count is not zero.")
            except (TypeError, ValueError) as exc:
                issues.append(f"Calendar-based coverage re-check could not run: {exc}")

    return len(issues) == 0, tuple(issues)


def build_manifest_from_csv(
    csv_path: str | Path,
    *,
    dataset_id: str,
    vendor_name: str = "SYNTHETIC_QA_GENERATOR",
    licence_id: str = "INTERNAL-QA-ONLY",
    instrument_symbol: str = "NIFTY",
    venue: str = "NSE",
    interval: str = "1d",
    timezone_name: str = "Asia/Kolkata",
    dataset_class: DatasetClass = "SYNTHETIC_SMOKE_FIXTURE",
    survivorship_bias_free: bool = False,
    allowed_for_strategy_promotion: bool = False,
    vendor_corrections_applied: bool = False,
    calendar: Any | None = None,
    vendor_identity_evidence_ref: str = "",
    licence_evidence_ref: str = "",
    coverage_evidence_ref: str = "",
    instrument_metadata_evidence_ref: str = "",
    evidence_reviewed_by: str = "",
    evidence_reviewed_at: str = "",
) -> DatasetManifest:
    """Build a manifest; coverage remains unknown unless a calendar audit is supplied."""
    from nexus_titan.data.canonical import load_canonical_data

    target = Path(csv_path).resolve()
    candles, report = load_canonical_data(
        target, symbol=instrument_symbol, interval=interval, source_timezone=timezone_name
    )
    if not report.is_valid:
        raise ValueError("Cannot build a dataset manifest from invalid canonical CSV: " + "; ".join(report.errors[:10]))
    checksum = compute_dataset_sha256(target)
    start_ts = candles[0].timestamp if candles else ""
    end_ts = candles[-1].timestamp if candles else ""

    coverage_verified = False
    missing_bars_count: int | None = None
    notes = "Canonical OHLCV structure validated; session coverage not verified."
    if calendar is not None and candles:
        coverage = _calendar_coverage_report(
            candles, symbol=instrument_symbol, interval=interval, source=vendor_name, calendar=calendar
        )
        coverage_verified = coverage.is_valid
        if coverage_verified:
            missing_bars_count = 0
            notes = "Canonical OHLCV and supplied market-calendar coverage validated."
        else:
            missing_bars_count = None
            notes = (
                f"Calendar coverage failed: {len(coverage.missing_intervals)} gap span(s), "
                f"{len(coverage.outside_session)} out-of-session candle(s), "
                f"{len(coverage.duplicate_timestamps)} duplicate timestamp(s)."
            )

    return DatasetManifest(
        dataset_id=dataset_id,
        file_path=str(target),
        sha256_checksum=checksum,
        vendor_name=vendor_name,
        licence_id=licence_id,
        instrument_symbol=instrument_symbol,
        venue=venue,
        interval=interval,
        timezone_name=timezone_name,
        start_timestamp=start_ts,
        end_timestamp=end_ts,
        bar_count=len(candles),
        dataset_class=dataset_class,
        survivorship_bias_free=survivorship_bias_free,
        vendor_corrections_applied=vendor_corrections_applied,
        missing_bars_count=missing_bars_count,
        duplicate_bars_count=report.duplicate_timestamps,
        allowed_for_strategy_promotion=allowed_for_strategy_promotion,
        notes=notes,
        coverage_verified=coverage_verified,
        vendor_identity_evidence_ref=vendor_identity_evidence_ref,
        licence_evidence_ref=licence_evidence_ref,
        coverage_evidence_ref=coverage_evidence_ref,
        instrument_metadata_evidence_ref=instrument_metadata_evidence_ref,
        evidence_reviewed_by=evidence_reviewed_by,
        evidence_reviewed_at=evidence_reviewed_at,
    )
