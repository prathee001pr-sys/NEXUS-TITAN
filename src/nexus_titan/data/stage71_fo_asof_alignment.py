"""Stage71: offline completed-candle alignment for synthetic F&O research.

Composes Stage59 futures-history and Stage44 option-chain catalog *outputs*.
They are still entirely operator-declared research inputs. This module
cannot independently authenticate a feed, exchange contract, licence, clock,
broker execution, or end-to-end source integrity. It produces NO features
that require an incomplete future candle, and NO training/promotion permit.
"""
from __future__ import annotations

import hashlib
import json
import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from nexus_titan.data.historical_fo_catalog import HistoricalCatalogResult
from nexus_titan.data.option_chain_ingest import ResearchOptionChainSnapshot
from nexus_titan.data.stage59_futures_history import Stage59FuturesHistory

_SHA = re.compile(r"[a-fA-F0-9]{64}\Z", re.ASCII)
_IST = ZoneInfo("Asia/Kolkata")
_INTERVAL = re.compile(r"(1|5|15|30)m\Z", re.ASCII)
_UNDERLYINGS = ("NIFTY", "BANKNIFTY")


class Stage71AlignmentBlocked(ValueError):
    """No partial aligned research dataset may be returned on QA failure."""


@dataclass(frozen=True, slots=True)
class Stage71AlignedObservation:
    underlying: str
    option_dataset_id: str
    option_snapshot_sha256: str
    option_observed_at: datetime
    option_quote_count: int
    futures_dataset_id: str
    futures_csv_sha256: str
    futures_bar_opened_at: datetime
    futures_bar_closed_at: datetime
    futures_age_seconds: int


@dataclass(frozen=True, slots=True)
class Stage71FOLearningPreflight:
    underlying: str
    option_dataset_count: int
    observed_option_snapshots: int
    observed_futures_bars: int
    aligned_observation_count: int
    first_option_observed_at: datetime
    last_option_observed_at: datetime
    latest_completed_futures_at: datetime
    input_alignment_sha256: str
    observations: tuple[Stage71AlignedObservation, ...]
    # No operator supplied metadata may silently set these external claims.
    vendor_identity_independently_authenticated: bool = False
    data_licence_independently_authenticated: bool = False
    point_in_time_exchange_contracts_authenticated: bool = False
    independent_calendar_verified: bool = False
    real_market_depth_verified: bool = False
    historically_complete_fo_universe_verified: bool = False
    leak_free_full_training_pipeline_verified: bool = False
    model_performance_verified: bool = False
    approved_for_strategy_promotion: bool = False
    paper_order_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE71_OFFLINE_ALIGNED_RESEARCH_ONLY_NO_GO"


def _aware(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise Stage71AlignmentBlocked(label + " must be timezone-aware")
    return value.astimezone(timezone.utc)


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise Stage71AlignmentBlocked(label + " must be a SHA-256 digest")
    return value.lower()


def _no_external_approval(obj: object, names: tuple[str, ...], label: str) -> None:
    if any(getattr(obj, name, None) is not False for name in names):
        raise Stage71AlignmentBlocked(label + " claims unverified external authority")
    if type(getattr(obj, "live_orders_transmitted", None)) is not int or obj.live_orders_transmitted != 0:
        raise Stage71AlignmentBlocked(label + " claims live broker activity")


def align_stage71_fo_research_inputs(
    futures: Stage59FuturesHistory,
    catalog: HistoricalCatalogResult,
    *,
    max_futures_age_seconds: int = 300,
    max_aligned_observations: int = 5000,
) -> Stage71FOLearningPreflight:
    """Join only **fully closed** futures candles to option snapshot as-of time.

    Each option observation matches the most recent futures candle whose
    OPEN + timeframe <= option snapshot time, on the SAME India market date.
    If no such candle or the closed data are stale, fail the *whole* input.
    Never use the just-opened futures candle's OHLC close/high/low.
    Synthetic smoke checks do not prove an exchange-wide leak-free pipeline.
    """
    if not isinstance(futures, Stage59FuturesHistory) or not isinstance(catalog, HistoricalCatalogResult):
        raise Stage71AlignmentBlocked("Typed Stage59 futures + Stage44 options catalog required")
    if (type(max_futures_age_seconds) is not int or not 0 <= max_futures_age_seconds <= 900
            or type(max_aligned_observations) is not int
            or not 1 <= max_aligned_observations <= 20000):
        raise Stage71AlignmentBlocked("Invalid bounded alignment budgets")
    if futures.underlying not in _UNDERLYINGS:
        raise Stage71AlignmentBlocked("NIFTY or BANKNIFTY futures required")
    match = _INTERVAL.fullmatch(futures.timeframe)
    if match is None:
        raise Stage71AlignmentBlocked("Unsupported futures timeframe")
    interval = timedelta(minutes=int(match.group(1)))
    _no_external_approval(futures, (
        "vendor_identity_authenticated", "licence_authenticated",
        "official_contract_master_authenticated", "exchange_calendar_authenticated",
        "source_is_independently_verified_exchange_history",
        "full_exchange_universe_coverage_verified", "real_orderbook_depth_present",
        "fill_or_backtest_performance_verified", "approved_for_strategy_promotion",
        "production_ready",
    ), "Stage59")
    _no_external_approval(catalog, (
        "external_source_authenticated", "licence_authenticated",
        "point_in_time_exchange_metadata_authenticated",
        "exchange_calendar_authenticated", "full_market_history_coverage_verified",
        "realistic_fo_backtest_verified", "strategy_promotion_allowed",
    ), "Stage44")
    if (type(futures.count) is not int or futures.count < 1 or futures.count != futures.expected_slots
            or len(futures.candles) != futures.count
            or not isinstance(futures.dataset_id, str) or not futures.dataset_id.strip()):
        raise Stage71AlignmentBlocked("Futures evidence/count unavailable")
    futures_sha = _digest(futures.file_sha256, "Futures CSV")
    completed: list[datetime] = []
    started: list[datetime] = []
    previous_end: datetime | None = None
    for bar in futures.candles:
        if bar.symbol != futures.symbol or bar.timeframe != futures.timeframe:
            raise Stage71AlignmentBlocked("Futures bar contract/timeframe drift")
        start = _aware(bar.timestamp, "Futures bar")
        end = start + interval
        if previous_end is not None and end <= previous_end:
            raise Stage71AlignmentBlocked("Futures bars duplicate or out of order")
        if end.astimezone(_IST).date() != start.astimezone(_IST).date():
            raise Stage71AlignmentBlocked("Futures bar crosses Indian session date")
        started.append(start)
        completed.append(end)
        previous_end = end
    if (started[0] != _aware(futures.first_observed_at, "Futures first")
            or started[-1] != _aware(futures.last_observed_at, "Futures last")):
        raise Stage71AlignmentBlocked("Futures declared boundaries mismatch candles")
    if (type(catalog.dataset_count) is not int
            or catalog.dataset_count < 1
            or catalog.dataset_count != len(catalog.partitions)
            or type(catalog.snapshot_count) is not int
            or not 1 <= catalog.snapshot_count <= max_aligned_observations):
        raise Stage71AlignmentBlocked("Options catalog count/budget mismatch")
    rows: list[Stage71AlignedObservation] = []
    seen_ids: set[str] = set()
    observed = 0
    for partition in catalog.partitions:
        preflight, history = partition.preflight, partition.history
        if (preflight.underlying != futures.underlying
                or not isinstance(preflight.dataset_id, str)
                or not preflight.dataset_id.strip()
                or preflight.dataset_id in seen_ids):
            raise Stage71AlignmentBlocked("Option partition underlying or dataset mismatch")
        seen_ids.add(preflight.dataset_id)
        if (not isinstance(history.snapshots, tuple)
                or type(preflight.snapshot_count) is not int
                or preflight.snapshot_count != len(history.snapshots)
                or preflight.snapshot_count < 1
                or preflight.snapshot_count > max_aligned_observations
                or history.approved_for_strategy_promotion is not False
                or preflight.approved_for_strategy_promotion is not False
                or preflight.live_orders_transmitted != 0):
            raise Stage71AlignmentBlocked("Options history structural/authority mismatch")
        seen_option_times: set[datetime] = set()
        prior: datetime | None = None
        for snap in history.snapshots:
            if not isinstance(snap, ResearchOptionChainSnapshot) or not snap.quotes:
                raise Stage71AlignmentBlocked("Invalid option snapshot type or empty chain")
            if snap.approved_for_strategy_promotion is not False:
                raise Stage71AlignmentBlocked("Option snapshot claims promotion authority")
            when = _aware(snap.observed_at, "Option observed_at")
            if when in seen_option_times or (prior is not None and when <= prior):
                raise Stage71AlignmentBlocked("Option snapshots duplicate or out of order")
            prior = when
            seen_option_times.add(when)
            sha = _digest(snap.sha256, "Option snapshot")
            if when < _aware(preflight.first_observed_at, "Option first") or when > _aware(preflight.last_observed_at, "Option last"):
                raise Stage71AlignmentBlocked("Option snapshot outside inspected partition")
            if any(getattr(q, "underlying", None) != futures.underlying for q in snap.quotes):
                raise Stage71AlignmentBlocked("Option quotes underlying mismatch")
            i = bisect_right(completed, when) - 1
            if i < 0:
                raise Stage71AlignmentBlocked("Future data not completed before option snapshot")
            age = (when - completed[i]).total_seconds()
            if age < 0 or age > max_futures_age_seconds or int(age) != age:
                raise Stage71AlignmentBlocked("Futures information stale or fractional lag")
            if completed[i].astimezone(_IST).date() != when.astimezone(_IST).date():
                raise Stage71AlignmentBlocked("Cross-session futures information rejected")
            rows.append(Stage71AlignedObservation(
                underlying=futures.underlying,
                option_dataset_id=preflight.dataset_id,
                option_snapshot_sha256=sha,
                option_observed_at=when,
                option_quote_count=len(snap.quotes),
                futures_dataset_id=futures.dataset_id,
                futures_csv_sha256=futures_sha,
                futures_bar_opened_at=started[i],
                futures_bar_closed_at=completed[i],
                futures_age_seconds=int(age),
            ))
            if len(rows) > max_aligned_observations:
                raise Stage71AlignmentBlocked("Combined aligned snapshot budget exceeded")
            observed += 1
        if (prior != _aware(preflight.last_observed_at, "Option last")
                or min(seen_option_times) != _aware(preflight.first_observed_at, "Option first")):
            raise Stage71AlignmentBlocked("Option partition boundaries do not match")
    if observed != catalog.snapshot_count or not rows:
        raise Stage71AlignmentBlocked("Catalog snapshots do not match declared count")
    rows.sort(key=lambda x: (x.option_observed_at, x.option_dataset_id))
    material = [
        (r.option_dataset_id, r.option_snapshot_sha256,
         r.option_observed_at.isoformat(), r.futures_dataset_id,
         r.futures_csv_sha256, r.futures_bar_opened_at.isoformat(),
         r.futures_bar_closed_at.isoformat(), r.futures_age_seconds)
        for r in rows
    ]
    digest = hashlib.sha256(json.dumps(
        material, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return Stage71FOLearningPreflight(
        underlying=futures.underlying,
        option_dataset_count=len(seen_ids),
        observed_option_snapshots=observed,
        observed_futures_bars=futures.count,
        aligned_observation_count=len(rows),
        first_option_observed_at=rows[0].option_observed_at,
        last_option_observed_at=rows[-1].option_observed_at,
        latest_completed_futures_at=max(row.futures_bar_closed_at for row in rows),
        input_alignment_sha256=digest,
        observations=tuple(rows),
    )
