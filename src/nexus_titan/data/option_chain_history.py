"""Bounded, fail-closed time-series QA for *already imported* option snapshots.

Research-only: no market connectivity, strategy promotion, or trading actions.
Each supplied snapshot is rechecked with the existing option-chain integrity gate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.derivatives.chain_integrity import inspect_verified_option_chain


class OptionChainHistoryError(ValueError):
    """No partial time series is released if any historical gate fails."""


@dataclass(frozen=True, slots=True)
class OptionChainHistoryReport:
    snapshot_count: int
    expected_slots: int
    missing_slots: int
    missing_examples: tuple[datetime, ...]
    issues: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.issues and self.missing_slots == 0


@dataclass(frozen=True, slots=True)
class ResearchOptionChainHistory:
    snapshots: tuple[ResearchOptionChainSnapshot, ...]
    interval_minutes: int
    expected_slots: int
    approved_for_strategy_promotion: bool = False


def _valid_positive_int(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _same_session_grid(observed: datetime, calendar: MarketCalendar, minutes: int) -> bool:
    local = observed.astimezone(calendar.zone)
    for session in calendar.sessions_for_date(local.date()):
        start = datetime.combine(local.date(), session.opens, tzinfo=calendar.zone)
        finish = datetime.combine(local.date(), session.closes, tzinfo=calendar.zone)
        if start <= local < finish:
            offset = (local - start).total_seconds()
            return offset >= 0 and offset % (minutes * 60) == 0
    return False


def inspect_option_chain_history(
    snapshots: Sequence[ResearchOptionChainSnapshot],
    *,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    interval_minutes: int = 1,
    max_snapshots: int = 2000,
    max_expected_slots: int = 20000,
    max_calendar_days: int = 366,
    max_quote_age_seconds: float = 120.0,
    min_strike_retention_ratio: float = 0.8,
    max_missing_examples: int = 20,
) -> OptionChainHistoryReport:
    """Audit ordering, gaps, session-grid alignment and per-snapshot chain safety.

    Missing slots are counted **only between** the first and last observation;
    completeness beyond the observed boundary is unknown. Weekends, supplied
    holidays, and all configured trading-session breaks are excluded.
    Unknown external source identity/licensing remains unverified.
    """
    for name, value in (
        ("interval_minutes", interval_minutes),
        ("max_snapshots", max_snapshots),
        ("max_expected_slots", max_expected_slots),
        ("max_calendar_days", max_calendar_days),
        ("max_missing_examples", max_missing_examples),
    ):
        _valid_positive_int(name, value)
    if (isinstance(max_quote_age_seconds, bool) or
            not isinstance(max_quote_age_seconds, (int, float)) or
            not 0 <= max_quote_age_seconds < float("inf")):
        raise ValueError("max_quote_age_seconds must be finite and non-negative")
    if (isinstance(min_strike_retention_ratio, bool) or
            not isinstance(min_strike_retention_ratio, (int, float)) or
            not 0 <= min_strike_retention_ratio <= 1):
        raise ValueError("min_strike_retention_ratio must be in [0, 1]")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise ValueError("A reviewed Asia/Kolkata MarketCalendar is required")
    if not isinstance(contract, PointInTimeContractSpec) or contract.exchange.upper() != "NSE":
        raise ValueError("NSE point-in-time contract metadata is required")
    if not isinstance(snapshots, (tuple, list)):
        raise TypeError("snapshots must be a list or tuple, not a stream")
    rows = tuple(snapshots)
    if not rows:
        return OptionChainHistoryReport(0, 0, 0, (), ("Empty option-chain history",))
    if len(rows) > max_snapshots:
        return OptionChainHistoryReport(len(rows), 0, 0, (), ("Snapshot count exceeds bounded max_snapshots",))

    issues: list[str] = []
    seen_times: set[datetime] = set()
    seen_hashes: set[str] = set()
    instants: list[datetime] = []
    anchor_evidence: tuple[str, str, str, str] | None = None
    previous_strikes: set[tuple[float, str]] | None = None

    for index, item in enumerate(rows):
        if not isinstance(item, ResearchOptionChainSnapshot):
            issues.append(f"Snapshot {index}: not a validated research snapshot")
            continue
        moment = item.observed_at
        if not isinstance(moment, datetime) or moment.tzinfo is None or moment.utcoffset() is None:
            issues.append(f"Snapshot {index}: observation must be timezone-aware")
            continue
        when = moment.astimezone(timezone.utc)
        if instants and when < instants[-1]:
            issues.append(f"Snapshot {index}: observations are out of order")
        if when in seen_times:
            issues.append(f"Snapshot {index}: duplicate observation timestamp")
        seen_times.add(when)
        instants.append(when)
        if not calendar.is_open(moment):
            issues.append(f"Snapshot {index}: observation outside configured exchange session")
        elif not _same_session_grid(moment, calendar, interval_minutes):
            issues.append(f"Snapshot {index}: observation not aligned to session interval grid")

        if not isinstance(item.sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", item.sha256):
            issues.append(f"Snapshot {index}: invalid source digest")
        elif item.sha256.lower() in seen_hashes:
            issues.append(f"Snapshot {index}: replayed/duplicate source payload digest")
        else:
            seen_hashes.add(item.sha256.lower())
        if item.approved_for_strategy_promotion is not False:
            issues.append(f"Snapshot {index}: promotion authorization is forbidden")

        evidence = (
            item.provider_reference, item.licence_evidence_reference,
            item.calendar_evidence_reference, item.contract_evidence_reference,
        )
        if any(not isinstance(ref, str) or not ref.strip() for ref in evidence):
            issues.append(f"Snapshot {index}: missing evidence reference")
        if anchor_evidence is None:
            anchor_evidence = evidence
        elif evidence != anchor_evidence:
            issues.append(f"Snapshot {index}: provider/licence/calendar/contract evidence changed within series")
        if item.contract_evidence_reference != contract.source_reference:
            issues.append(f"Snapshot {index}: contract evidence reference mismatch")

        if not isinstance(item.quotes, tuple):
            issues.append(f"Snapshot {index}: immutable quote tuple required")
            continue
        integrity = inspect_verified_option_chain(
            item.quotes, contract, observed_at=moment,
            max_quote_age_seconds=max_quote_age_seconds,
        )
        if not integrity.is_valid:
            issues.append(
                f"Snapshot {index}: option-chain integrity failed: " +
                "; ".join(integrity.issues[:6])
            )
        for quote in item.quotes:
            if not hasattr(quote, "timestamp"):
                continue
            try:
                quote_time = datetime.fromisoformat(quote.timestamp.replace("Z", "+00:00"))
                if quote_time.tzinfo is None or quote_time.utcoffset() is None or not calendar.is_open(quote_time):
                    issues.append(f"Snapshot {index}: quote outside configured exchange session")
            except (AttributeError, TypeError, ValueError):
                issues.append(f"Snapshot {index}: invalid quote timestamp")
        current_strikes = {
            (quote.strike, quote.option_type) for quote in item.quotes
            if hasattr(quote, "strike") and hasattr(quote, "option_type")
        }
        if previous_strikes is not None and previous_strikes:
            ratio = len(previous_strikes & current_strikes) / len(previous_strikes)
            if ratio < min_strike_retention_ratio:
                issues.append(f"Snapshot {index}: strike coverage/retention fell below threshold")
        previous_strikes = current_strikes

    if not instants:
        return OptionChainHistoryReport(len(rows), 0, 0, (), tuple(issues))
    first, last = min(instants), max(instants)
    start_local, end_local = first.astimezone(calendar.zone), last.astimezone(calendar.zone)
    day_span = (end_local.date() - start_local.date()).days
    if day_span > max_calendar_days:
        issues.append("History spans more days than max_calendar_days; audit in smaller batches")
        return OptionChainHistoryReport(len(rows), 0, 0, (), tuple(issues))

    expected_count = 0
    missing_count = 0
    examples: list[datetime] = []
    step = timedelta(minutes=interval_minutes)
    for day_offset in range(day_span + 1):
        day = start_local.date() + timedelta(days=day_offset)
        for session in calendar.sessions_for_date(day):
            slot = datetime.combine(day, session.opens, tzinfo=calendar.zone)
            closes = datetime.combine(day, session.closes, tzinfo=calendar.zone)
            while slot < closes:
                utc_slot = slot.astimezone(timezone.utc)
                if first <= utc_slot <= last:
                    expected_count += 1
                    if expected_count > max_expected_slots:
                        issues.append("Expected grid exceeds max_expected_slots; audit in smaller batches")
                        return OptionChainHistoryReport(len(rows), expected_count, missing_count, tuple(examples), tuple(issues))
                    if utc_slot not in seen_times:
                        missing_count += 1
                        if len(examples) < max_missing_examples:
                            examples.append(utc_slot)
                slot += step
    if missing_count:
        issues.append(f"Missing {missing_count} expected option-chain snapshot interval(s)")
    return OptionChainHistoryReport(
        len(rows), expected_count, missing_count, tuple(examples), tuple(issues)
    )


def assemble_research_option_chain_history(
    snapshots: Sequence[ResearchOptionChainSnapshot],
    *,
    contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    interval_minutes: int = 1,
    **quality_limits: object,
) -> ResearchOptionChainHistory:
    """Release a tuple only when the entire bounded history passes validation.

    Never grants strategy-promotion authority. Invalid input releases no partial
    snapshot series.
    """
    report = inspect_option_chain_history(
        snapshots, contract=contract, calendar=calendar,
        interval_minutes=interval_minutes, **quality_limits,
    )
    if not report.is_valid:
        raise OptionChainHistoryError("History integrity rejected: " + "; ".join(report.issues))
    return ResearchOptionChainHistory(tuple(snapshots), interval_minutes, report.expected_slots)
