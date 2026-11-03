"""Stage60: leakage-conscious, brokerless NSE futures OOS forecast research.

Consumes ONLY already-preflighted Stage59 in-memory futures candles.
May optionally observe a preflighted Stage44 OPTIONS catalog for
structural coverage. It never invents option prices, bid/ask depth,
fills, fees, margin, position accounting or realistic F&O P&L.

This deliberately FIXED moving-average directional diagnostic is not
a trained, selected, optimized, or independently verified strategy.
All source references, even Stage59 "source_verified" claims, are
caller-declared. Splits use label-time containment and an embargo,
but are not a proof against a malicious strategy or a data provider.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from nexus_titan.data.historical_fo_catalog import HistoricalCatalogResult
from nexus_titan.data.instrument_master import PointInTimeContractSpec
from nexus_titan.data.ohlcv import CandleQuery
from nexus_titan.data.quality import inspect_candle_batch
from nexus_titan.data.sessions import MarketCalendar
from nexus_titan.data.stage59_futures_history import Stage59FuturesHistory

_SHA = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)


class Stage60ResearchBlocked(ValueError):
    """Complete local research sequence rejected; no evidence is promoted."""


@dataclass(frozen=True, slots=True)
class Stage60ResearchConfig:
    initial_train_bars: int = 12
    holdout_bars: int = 8
    embargo_bars: int = 2
    max_folds: int = 3
    fast_ma_bars: int = 3
    slow_ma_bars: int = 5
    minimum_oos_predictions: int = 30

    def __post_init__(self) -> None:
        limits = (
            (self.initial_train_bars, 6, 5000),
            (self.holdout_bars, 3, 1000),
            (self.embargo_bars, 1, 100),
            (self.max_folds, 1, 20),
            (self.fast_ma_bars, 1, 250),
            (self.slow_ma_bars, 2, 500),
            (self.minimum_oos_predictions, 1, 5000),
        )
        if any(type(x) is not int or not lo <= x <= hi for x, lo, hi in limits):
            raise Stage60ResearchBlocked("Invalid bounded Stage60 research configuration")
        if (self.fast_ma_bars >= self.slow_ma_bars
                or self.slow_ma_bars >= self.initial_train_bars):
            raise Stage60ResearchBlocked("MA lookback must be shorter than initial training bars")


@dataclass(frozen=True, slots=True)
class Stage60DirectionalObservation:
    origin_at: datetime
    target_at: datetime
    prediction: int  # +1 direction up, -1 down; 0 means neutral and excluded
    actual_next_close_direction: int
    correct: bool
    origin_in_holdout: bool = True
    target_in_same_holdout: bool = True
    orders_or_fills: int = 0


@dataclass(frozen=True, slots=True)
class Stage60Fold:
    fold_number: int
    training_last_at: datetime
    embargo_first_at: datetime
    embargo_last_at: datetime
    holdout_first_at: datetime
    holdout_last_at: datetime
    trained_strategy_parameters: bool
    candidate_label_count: int
    directional_prediction_count: int
    correct_direction_count: int
    neutral_signal_count: int
    flat_market_miss_count: int
    hit_rate: Decimal | None
    observations: tuple[Stage60DirectionalObservation, ...]
    actual_trades_recorded: int = 0
    actual_fills_verified: int = 0


@dataclass(frozen=True, slots=True)
class Stage60OfflineResearchReport:
    dataset_id: str
    underlying: str
    symbol: str
    timeframe: str
    contract_expiry_date: str
    source_file_sha256: str
    local_evidence_digest: str
    folds: tuple[Stage60Fold, ...]
    total_candidate_labels: int
    total_directional_predictions: int
    total_correct_directions: int
    total_flat_market_misses: int
    overall_directional_hit_rate: Decimal | None
    evidence_sample_sufficient: bool
    evidence_verdict: str
    options_catalog_declared_window_observed: bool
    related_options_snapshot_count: int
    implementation_scope: str = "FIXED_MA_DIRECTIONAL_OOS_NOT_FO_BACKTEST_PNL"
    dataset_source_authenticated: bool = False
    licence_authenticated: bool = False
    official_historical_lot_master_authenticated: bool = False
    exchange_calendar_authenticated: bool = False
    options_quotes_cross_instrument_synchronized: bool = False
    executable_depth_verified: bool = False
    margin_and_funding_verified: bool = False
    execution_costs_or_broker_fills_verified: bool = False
    real_fo_backtest_performance_verified: bool = False
    strategy_promotion_authorized: bool = False
    capital_ledger_updated: bool = False
    independent_global_risk_veto_enforced: bool = False
    live_orders_transmitted: int = 0
    live_trading_enabled: bool = False
    production_ready: bool = False


def inspect_stage60_purged_oos(
    history: Stage59FuturesHistory,
    *, contract: PointInTimeContractSpec,
    calendar: MarketCalendar,
    config: Stage60ResearchConfig = Stage60ResearchConfig(),
    option_catalog: HistoricalCatalogResult | None = None,
) -> Stage60OfflineResearchReport:
    """Bounded, no-write fixed-parameter OOS directional diagnostic.

    Labels are close(i+1)-close(i), with BOTH i and i+1 contained
    inside the holdout window. Training never sees target labels
    across the embargo/test boundary. No strategy fitting occurs.
    """
    if not isinstance(history, Stage59FuturesHistory):
        raise Stage60ResearchBlocked("Only Stage59 preflight futures history is accepted")
    if not isinstance(config, Stage60ResearchConfig):
        raise Stage60ResearchBlocked("Typed Stage60 config required")
    if (not isinstance(contract, PointInTimeContractSpec)
            or contract.segment != "FUTURES" or contract.exchange != "NSE"
            or not contract.source_verified or not contract.source_reference
            or contract.symbol != history.symbol or contract.underlying != history.underlying
            or contract.expiry_date is None
            or contract.expiry_date.isoformat() != history.expiry_date
            or contract.lot_size != history.inspected_contract_lot_size
            or Decimal(str(contract.tick_size)) != history.inspected_contract_tick_size):
        raise Stage60ResearchBlocked("NSE futures contract, expiry and source claim mismatch")
    if not isinstance(calendar, MarketCalendar) or calendar.timezone_name != "Asia/Kolkata":
        raise Stage60ResearchBlocked("Asia/Kolkata market calendar required")
    # Declared Stage59 preflight metadata is *not* cryptographically protected.
    # If any caller mutates a no-authority flag to True, fail rather than
    # propagate it as a verified source/financial result.
    if any((
        history.vendor_identity_authenticated,
        history.licence_authenticated,
        history.official_contract_master_authenticated,
        history.exchange_calendar_authenticated,
        history.source_is_independently_verified_exchange_history,
        history.real_orderbook_depth_present,
        history.approved_for_strategy_promotion,
        history.production_ready,
        history.live_orders_transmitted != 0,
    )):
        raise Stage60ResearchBlocked("Untrusted Stage59 history claims external authority")
    rows = history.candles
    n = len(rows)
    step = timedelta(minutes=int(history.timeframe[:-1])) if (
        history.timeframe.endswith("m") and history.timeframe[:-1].isdigit()
    ) else timedelta(0)
    if (not isinstance(rows, tuple) or n < config.initial_train_bars
            + config.embargo_bars + config.holdout_bars
            or n > 1000 or step <= timedelta(0)
            or history.count != n or history.expected_slots != n
            or _SHA.fullmatch(history.file_sha256 or "") is None):
        raise Stage60ResearchBlocked("Futures partition too short, unbounded or inconsistent")
    if rows[0].timestamp != history.first_observed_at or (
        rows[-1].timestamp != history.last_observed_at
    ):
        raise Stage60ResearchBlocked("Futures history endpoint drift")
    if not all(
        bar.symbol == history.symbol and bar.timeframe == history.timeframe
        and bar.source and bar.timestamp == rows[0].timestamp + i * step
        for i, bar in enumerate(rows)
    ):
        raise Stage60ResearchBlocked("Futures timestamps/identity are not an unbroken grid")
    day = rows[0].timestamp.astimezone(calendar.zone).date()
    if (not contract.effective_from <= day <= contract.effective_to
            or day > contract.expiry_date
            or not all(calendar.is_open(x.timestamp) for x in rows)):
        raise Stage60ResearchBlocked("Futures series is outside contract/session metadata")
    query = CandleQuery(
        history.symbol, history.timeframe,
        rows[0].timestamp, rows[-1].timestamp + step,
    )
    if not inspect_candle_batch(rows, query, calendar=calendar).is_valid:
        raise Stage60ResearchBlocked("Existing OHLCV quality gate rejected futures history")

    option_count = 0
    option_coverage = False
    if option_catalog is not None:
        if not isinstance(option_catalog, HistoricalCatalogResult):
            raise Stage60ResearchBlocked("Typed Stage44 catalog required")
        if (option_catalog.external_source_authenticated
                or option_catalog.licence_authenticated
                or option_catalog.point_in_time_exchange_metadata_authenticated
                or option_catalog.exchange_calendar_authenticated
                or option_catalog.realistic_fo_backtest_verified
                or option_catalog.strategy_promotion_allowed
                or option_catalog.live_orders_transmitted != 0):
            raise Stage60ResearchBlocked("Untrusted options catalog claims external authority")
        if (not option_catalog.partitions or option_catalog.snapshot_count < 1
                or option_catalog.first_observed_at > rows[0].timestamp
                or option_catalog.last_observed_at < rows[-1].timestamp):
            raise Stage60ResearchBlocked("No structural options timeline coverage across futures window")
        matching = [
            p for p in option_catalog.partitions
            if p.preflight.underlying == history.underlying
        ]
        if not matching:
            raise Stage60ResearchBlocked("Options catalog does not cover futures underlying")
        option_count = sum(x.preflight.snapshot_count for x in matching)
        option_coverage = True  # ONLY time-window/source-declared metadata

    folds = []
    cursor = config.initial_train_bars
    for fold_index in range(config.max_folds):
        first_test = cursor + config.embargo_bars
        last_test_exclusive = first_test + config.holdout_bars
        if last_test_exclusive > n:
            break
        observed = []
        neutral = flat_misses = 0
        # Predict only with data available at the origin bar's close.
        # Origin AND label target must be inside the same held-out fold.
        for origin in range(first_test, last_test_exclusive - 1):
            prefix = rows[:origin + 1]
            fast = sum(x.close for x in prefix[-config.fast_ma_bars:]) / config.fast_ma_bars
            slow = sum(x.close for x in prefix[-config.slow_ma_bars:]) / config.slow_ma_bars
            prediction = 1 if fast > slow else -1 if fast < slow else 0
            if prediction == 0:
                neutral += 1
                continue
            delta = rows[origin + 1].close - rows[origin].close
            actual = 1 if delta > 0 else -1 if delta < 0 else 0
            if actual == 0:
                flat_misses += 1
            observed.append(Stage60DirectionalObservation(
                origin_at=rows[origin].timestamp,
                target_at=rows[origin + 1].timestamp,
                prediction=prediction,
                actual_next_close_direction=actual,
                correct=actual == prediction,
            ))
        correct = sum(1 for x in observed if x.correct)
        count = len(observed)
        folds.append(Stage60Fold(
            fold_number=fold_index + 1,
            training_last_at=rows[cursor - 1].timestamp,
            embargo_first_at=rows[cursor].timestamp,
            embargo_last_at=rows[first_test - 1].timestamp,
            holdout_first_at=rows[first_test].timestamp,
            holdout_last_at=rows[last_test_exclusive - 1].timestamp,
            trained_strategy_parameters=False,
            candidate_label_count=config.holdout_bars - 1,
            directional_prediction_count=count,
            correct_direction_count=correct,
            neutral_signal_count=neutral,
            flat_market_miss_count=flat_misses,
            hit_rate=Decimal(correct) / count if count else None,
            observations=tuple(observed),
        ))
        cursor = last_test_exclusive  # Prior OOS becomes past history ONLY.
    if not folds:
        raise Stage60ResearchBlocked("No complete embargoed holdout fold can be formed")
    prediction_count = sum(x.directional_prediction_count for x in folds)
    correct = sum(x.correct_direction_count for x in folds)
    candidate = sum(x.candidate_label_count for x in folds)
    flat = sum(x.flat_market_miss_count for x in folds)
    enough = prediction_count >= config.minimum_oos_predictions
    # Local SHA256 records only the supplied synthetic bytes and parameters.
    # It is not vendor attestation, a cryptographic signature or risk approval.
    manifest = json.dumps(
        ["STAGE60_FIXED_MA_NO_FILL_RESEARCH_V1", history.dataset_id,
         history.symbol, history.file_sha256, history.expiry_date,
         [str(x.close) for x in rows],
         list((config.initial_train_bars, config.holdout_bars,
               config.embargo_bars, config.max_folds,
               config.fast_ma_bars, config.slow_ma_bars,
               config.minimum_oos_predictions)),
         [(x.fold_number, x.training_last_at.isoformat(),
           x.holdout_first_at.isoformat(), x.holdout_last_at.isoformat())
          for x in folds]],
        separators=(",", ":"), ensure_ascii=False,
    )
    return Stage60OfflineResearchReport(
        dataset_id=history.dataset_id, underlying=history.underlying,
        symbol=history.symbol, timeframe=history.timeframe,
        contract_expiry_date=history.expiry_date,
        source_file_sha256=history.file_sha256,
        local_evidence_digest=hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
        folds=tuple(folds), total_candidate_labels=candidate,
        total_directional_predictions=prediction_count,
        total_correct_directions=correct,
        total_flat_market_misses=flat,
        overall_directional_hit_rate=Decimal(correct) / prediction_count
            if prediction_count else None,
        evidence_sample_sufficient=enough,
        evidence_verdict="EXPLORATORY_SAMPLE_ONLY" if enough
            else "INSUFFICIENT_OUT_OF_SAMPLE_OBSERVATIONS",
        options_catalog_declared_window_observed=option_coverage,
        related_options_snapshot_count=option_count,
    )
