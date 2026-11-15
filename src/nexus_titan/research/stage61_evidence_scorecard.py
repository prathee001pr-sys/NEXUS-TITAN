"""Stage61 offline F&O research evidence scorecard — always NO-GO for trading.

Combines already-created Stage59/60 research metadata with optional
Stage58 *separately fabricated* execution scenarios and Stage44 options
catalog. This is a read-only consistency reviewer, NOT an F&O backtester.

A Stage58 scenario lacks the symbol/expiry/quote timestamps necessary
to bind it cryptographically/semantically to a Stage60 holdout. NEVER
infer that a simulated fee, quote depth or fill corresponds to a
directional prediction or that a favorable prediction equals P&L.

No DB, broker, filesystem, networking, capital or order access.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal

from nexus_titan.data.historical_fo_catalog import HistoricalCatalogResult
from nexus_titan.data.stage59_futures_history import Stage59FuturesHistory
from nexus_titan.research.stage60_purged_oos import Stage60OfflineResearchReport
from nexus_titan.simulation.stage58_execution_stress import Stage58ExecutionScenario

_SHA = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)

_MANDATORY_BLOCKERS = (
    "NO_AUTHENTICATED_LICENSED_REAL_FO_DATA",
    "NO_OFFICIAL_POINT_IN_TIME_CONTRACT_OR_CALENDAR",
    "NO_BOUND_OBSERVED_BID_ASK_DEPTH_TO_HOLDOUT_SIGNALS",
    "NO_AUTHENTICATED_EXECUTION_FEES_MARGIN_SETTLEMENT",
    "NO_ACTUAL_FO_PNL_OR_REALISTIC_SHADOW_FILLS",
    "NO_INDEPENDENT_HUMAN_IDENTITY_OR_GLOBAL_RISK_VETO",
    "NO_UNIFIED_AUTHORITATIVE_CAPITAL_AND_LEGACY_BYPASS_FENCE",
    "NO_RECONCILED_OWNER_APPROVED_PROSPECTIVE_MERGE",
)
_UNTRUSTED_STAGE59_FLAGS = (
    "vendor_identity_authenticated",
    "licence_authenticated",
    "official_contract_master_authenticated",
    "exchange_calendar_authenticated",
    "source_is_independently_verified_exchange_history",
    "full_exchange_universe_coverage_verified",
    "real_orderbook_depth_present",
    "fill_or_backtest_performance_verified",
    "approved_for_strategy_promotion",
    "production_ready",
)
_UNTRUSTED_STAGE60_FLAGS = (
    "dataset_source_authenticated",
    "licence_authenticated",
    "official_historical_lot_master_authenticated",
    "exchange_calendar_authenticated",
    "options_quotes_cross_instrument_synchronized",
    "executable_depth_verified",
    "margin_and_funding_verified",
    "execution_costs_or_broker_fills_verified",
    "real_fo_backtest_performance_verified",
    "strategy_promotion_authorized",
    "capital_ledger_updated",
    "independent_global_risk_veto_enforced",
    "live_trading_enabled",
    "production_ready",
)
_UNTRUSTED_STAGE58_FLAGS = (
    "depth_provenance_independently_authenticated",
    "official_contract_master_independently_authenticated",
    "official_fees_or_margin_verified",
    "capital_reserved_in_any_account",
    "broker_fill_reconciliation_verified",
    "external_human_identity_verified",
    "independent_risk_veto_enforced",
    "approved_for_strategy_promotion",
    "live_trading_enabled",
    "production_ready",
)
_UNTRUSTED_STAGE44_FLAGS = (
    "external_source_authenticated",
    "licence_authenticated",
    "point_in_time_exchange_metadata_authenticated",
    "exchange_calendar_authenticated",
    "full_market_history_coverage_verified",
    "realistic_fo_backtest_verified",
    "strategy_promotion_allowed",
)


@dataclass(frozen=True, slots=True)
class Stage61EvidenceCheck:
    check_id: str
    status: Literal["LOCAL_CONSISTENCY", "CONFLICT", "MISSING_EVIDENCE"]
    detail: str


@dataclass(frozen=True, slots=True)
class Stage61FOMarketReadinessScorecard:
    schema_version: int
    scope: str
    underlying: str
    futures_symbol: str
    futures_dataset_id: str
    inspected_candles: int
    oos_folds: int
    oos_predictions: int
    oos_hit_rate: Decimal | None
    synthetic_execution_fragment_count: int
    synthetic_execution_fee_reserve: float | None
    options_declared_snapshot_count: int
    checks: tuple[Stage61EvidenceCheck, ...]
    structural_conflicts: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    mandatory_release_blockers: tuple[str, ...]
    local_inputs_structurally_consistent: bool
    local_evidence_sha256: str | None
    # The word "readiness" means BLOCKER REPORT, NEVER permission.
    source_vendor_authenticated: bool = False
    source_licence_authenticated: bool = False
    independently_verified_option_chain: bool = False
    execution_scenario_bound_to_holdout: bool = False
    real_orderbook_depth_authenticated: bool = False
    actual_execution_or_fees_reconciled: bool = False
    genuine_futures_options_backtest_verified: bool = False
    strategy_promotion_authorized: bool = False
    global_risk_veto_unbypassable: bool = False
    independently_verified_human_identity: bool = False
    unified_capital_settlement_verified: bool = False
    live_trading_enabled: bool = False
    production_ready: bool = False
    broker_orders_transmitted: int = 0


def _authority_clear(item: object, attrs: tuple[str, ...]) -> bool:
    return all(getattr(item, key, None) is False for key in attrs) and (
        type(getattr(item, "live_orders_transmitted", None)) is int
        and getattr(item, "live_orders_transmitted") == 0
    )


def _finite_nonnegative(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _check_execution(candidate: Stage58ExecutionScenario) -> bool:
    if (candidate.segment not in ("FUTURES", "OPTIONS")
            or candidate.side not in ("BUY", "SELL")
            or candidate.status not in ("FILLED", "PARTIAL", "UNFILLED")
            or type(candidate.requested_lots) is not int
            or candidate.requested_lots < 1
            or not isinstance(candidate.schedule_version, str)
            or not candidate.schedule_version.strip()
            or any(type(x) is not int or x < 0 for x in (
                candidate.requested_quantity, candidate.filled_quantity,
                candidate.remaining_quantity, candidate.observed_snapshots,
            )) or candidate.requested_quantity == 0
            or candidate.filled_quantity + candidate.remaining_quantity
            != candidate.requested_quantity
            or not isinstance(candidate.fragments, tuple)
            or not candidate.fragments
            or len(candidate.fragments) > candidate.observed_snapshots
            or len(candidate.fragments) > 100
            or not _authority_clear(candidate, _UNTRUSTED_STAGE58_FLAGS)):
        return False
    numeric = (candidate.filled_notional, candidate.fragment_fees_sum,
               candidate.aggregate_fee_estimate, candidate.conservative_fee_reserve,
               candidate.conservative_execution_friction, candidate.fill_ratio)
    if not all(_finite_nonnegative(v) for v in numeric):
        return False
    if (type(candidate.signed_mid_shortfall) not in (int, float)
            or not math.isfinite(candidate.signed_mid_shortfall)):
        return False
    if (abs(candidate.fill_ratio - candidate.filled_quantity
            / candidate.requested_quantity) > 1e-7
            or candidate.conservative_fee_reserve + 0.011 <
            max(candidate.fragment_fees_sum, candidate.aggregate_fee_estimate)
            or candidate.conservative_execution_friction + 0.011 <
            candidate.conservative_fee_reserve):
        return False
    expected_status = ("UNFILLED" if candidate.filled_quantity == 0 else
                       "FILLED" if candidate.remaining_quantity == 0 else "PARTIAL")
    if candidate.status != expected_status:
        return False
    if candidate.filled_quantity == 0 and (
        candidate.average_fill_price is not None
        or candidate.filled_notional != 0
        or candidate.fragment_fees_sum != 0
        or candidate.aggregate_fee_estimate != 0
        or candidate.conservative_fee_reserve != 0
    ):
        return False
    if candidate.filled_quantity > 0 and (
        not _finite_nonnegative(candidate.average_fill_price)
        or candidate.average_fill_price == 0
    ):
        return False
    cumulative = 0
    fee_total = 0.0
    prior = None
    observed_events = set()
    for fragment in candidate.fragments:
        if (not isinstance(fragment.event_id, str)
                or not fragment.event_id.strip()
                or fragment.event_id in observed_events
                or not isinstance(fragment.observed_at, datetime)
                or fragment.observed_at.tzinfo is None
                or fragment.observed_at.utcoffset() is None
                or (prior is not None and fragment.observed_at <= prior)
                or type(fragment.filled_quantity) is not int
                or fragment.filled_quantity < 0
                or fragment.live_orders_transmitted != 0):
            return False
        observed_events.add(fragment.event_id)
        prior = fragment.observed_at
        cumulative += fragment.filled_quantity
        if (fragment.remaining_quantity != candidate.requested_quantity - cumulative
                or cumulative > candidate.requested_quantity):
            return False
        if fragment.filled_quantity == 0:
            if (fragment.fees is not None or fragment.execution_price is not None
                    or fragment.notional != 0):
                return False
        else:
            if (fragment.fees is None
                    or not _finite_nonnegative(fragment.fees.total_charges)
                    or not _finite_nonnegative(fragment.execution_price)
                    or fragment.execution_price == 0
                    or not _finite_nonnegative(fragment.notional)):
                return False
            fee_total += fragment.fees.total_charges
    return (cumulative == candidate.filled_quantity
            and abs(round(fee_total, 2) - candidate.fragment_fees_sum) <= 0.011)


def _check_folds(oos: Stage60OfflineResearchReport) -> bool:
    folds = oos.folds
    if not isinstance(folds, tuple) or not folds or len(folds) > 20:
        return False
    total_pred = total_correct = total_candidates = total_flat = 0
    previous_holdout = None
    for index, fold in enumerate(folds, start=1):
        if (fold.fold_number != index or fold.trained_strategy_parameters is not False
                or fold.actual_trades_recorded != 0 or fold.actual_fills_verified != 0
                or not isinstance(fold.observations, tuple)
                or fold.candidate_label_count < 1
                or fold.directional_prediction_count < 0
                or fold.correct_direction_count < 0
                or fold.neutral_signal_count < 0
                or fold.flat_market_miss_count < 0
                or fold.candidate_label_count !=
                fold.neutral_signal_count + fold.directional_prediction_count
                or fold.directional_prediction_count != len(fold.observations)
                or fold.correct_direction_count >
                fold.directional_prediction_count
                or not (fold.training_last_at < fold.embargo_first_at
                        <= fold.embargo_last_at < fold.holdout_first_at
                        < fold.holdout_last_at)
                or (previous_holdout is not None
                    and fold.training_last_at != previous_holdout)):
            return False
        correct = 0
        flat = 0
        seen = set()
        for item in fold.observations:
            if (item.origin_in_holdout is not True
                    or item.target_in_same_holdout is not True
                    or item.orders_or_fills != 0
                    or item.prediction not in (-1, 1)
                    or item.actual_next_close_direction not in (-1, 0, 1)
                    or item.target_at <= item.origin_at
                    or item.origin_at < fold.holdout_first_at
                    or item.target_at > fold.holdout_last_at
                    or item.correct is not
                    (item.prediction == item.actual_next_close_direction)
                    or item.origin_at in seen):
                return False
            seen.add(item.origin_at)
            correct += int(item.correct)
            flat += int(item.actual_next_close_direction == 0)
        if (correct != fold.correct_direction_count
                or flat != fold.flat_market_miss_count
                or (fold.hit_rate != (Decimal(correct) / len(fold.observations)
                    if fold.observations else None))):
            return False
        previous_holdout = fold.holdout_last_at
        total_pred += fold.directional_prediction_count
        total_correct += correct
        total_candidates += fold.candidate_label_count
        total_flat += flat
    rate = Decimal(total_correct) / total_pred if total_pred else None
    return (
        oos.total_directional_predictions == total_pred
        and oos.total_correct_directions == total_correct
        and oos.total_candidate_labels == total_candidates
        and oos.total_flat_market_misses == total_flat
        and oos.overall_directional_hit_rate == rate
        and oos.evidence_verdict in (
            "EXPLORATORY_SAMPLE_ONLY",
            "INSUFFICIENT_OUT_OF_SAMPLE_OBSERVATIONS",
        )
        and (oos.evidence_verdict == "EXPLORATORY_SAMPLE_ONLY")
        is oos.evidence_sample_sufficient
    )


def inspect_stage61_fo_evidence(
    history: Stage59FuturesHistory,
    oos: Stage60OfflineResearchReport,
    *,
    execution: Stage58ExecutionScenario | None = None,
    option_catalog: HistoricalCatalogResult | None = None,
) -> Stage61FOMarketReadinessScorecard:
    """Read-only exact report cross-check; cannot grant financial authority."""
    if not isinstance(history, Stage59FuturesHistory):
        raise TypeError("Stage59FuturesHistory required")
    if not isinstance(oos, Stage60OfflineResearchReport):
        raise TypeError("Stage60OfflineResearchReport required")
    if execution is not None and not isinstance(execution, Stage58ExecutionScenario):
        raise TypeError("Stage58ExecutionScenario or None required")
    if option_catalog is not None and not isinstance(option_catalog, HistoricalCatalogResult):
        raise TypeError("HistoricalCatalogResult or None required")

    checks: list[Stage61EvidenceCheck] = []
    errors: list[str] = []
    missing: list[str] = []
    def check(name: str, valid: bool, description: str) -> None:
        if not valid:
            errors.append(name)
        checks.append(Stage61EvidenceCheck(
            name, "LOCAL_CONSISTENCY" if valid else "CONFLICT", description,
        ))
    def needs(name: str, description: str) -> None:
        missing.append(name)
        checks.append(Stage61EvidenceCheck(name, "MISSING_EVIDENCE", description))

    history_ok = (
        _authority_clear(history, _UNTRUSTED_STAGE59_FLAGS)
        and isinstance(history.dataset_id, str) and bool(history.dataset_id)
        and isinstance(history.candles, tuple)
        and 2 <= len(history.candles) <= 1000
        and type(history.count) is int and history.count == len(history.candles)
        and type(history.expected_slots) is int and history.expected_slots == len(history.candles)
        and _SHA.fullmatch(history.file_sha256 or "") is not None
        and history.inspected_contract_lot_size > 0
        and history.inspected_contract_tick_size > Decimal("0")
        and history.candles[0].timestamp == history.first_observed_at
        and history.candles[-1].timestamp == history.last_observed_at
    )
    check("S61-STAGE59-SOURCE-SHAPE", history_ok,
          "Operator-declared preflight shape only; no raw-file rehash, licence or exchange attestation")
    metadata_ok = (
        _authority_clear(oos, _UNTRUSTED_STAGE60_FLAGS)
        and _SHA.fullmatch(oos.source_file_sha256 or "") is not None
        and _SHA.fullmatch(oos.local_evidence_digest or "") is not None
        and oos.dataset_id == history.dataset_id
        and oos.underlying == history.underlying
        and oos.symbol == history.symbol
        and oos.timeframe == history.timeframe
        and oos.contract_expiry_date == history.expiry_date
        and oos.source_file_sha256 == history.file_sha256
        and oos.implementation_scope == "FIXED_MA_DIRECTIONAL_OOS_NOT_FO_BACKTEST_PNL"
    )
    check("S61-STAGE60-HISTORY-BINDING", metadata_ok,
          "OOS report matches futures partition identity, contract expiry and claimed file digest")
    check("S61-STAGE60-HELDOUT-LABELS", _check_folds(oos),
          "Recount held-out directional observations and label/embargo boundaries")
    if not oos.evidence_sample_sufficient:
        needs("S61-OOS-SAMPLE-INSUFFICIENT",
              "Configured Stage60 directional sample floor not met")
    else:
        needs("S61-OOS-EXPLORATORY-NOT-PROFIT",
              "Even a large synthetic directional sample is not trade-level P&L validation")

    fragments = 0
    fee = None
    if execution is None:
        needs("S61-SIMULATED-EXECUTION-ABSENT",
              "Optional Stage58 indicative cost/depth scenario missing")
    else:
        valid_exec = _check_execution(execution)
        check("S61-STAGE58-ARITHMETIC", valid_exec,
              "Synthetic fragment quantity, fees, time, and authority flags are internally consistent")
        fragments = len(execution.fragments) if valid_exec else 0
        fee = execution.conservative_fee_reserve if valid_exec else None
        if execution.segment != "FUTURES":
            needs("S61-FUTURES-EXECUTION-SEGMENT-MISMATCH",
                  "Supplied scenario is not a FUTURES fragment simulation")
        needs("S61-EXECUTION-NOT-LINKED-TO-OOS",
              "Stage58 lacks contract ID/expiry/timestamps tied to Stage60 holdout; no shared fills")

    option_count = 0
    if option_catalog is None:
        needs("S61-OPTIONS-CATALOG-ABSENT",
              "No optional structurally preflighted Stage44 options history supplied")
    else:
        valid_opts = (
            _authority_clear(option_catalog, _UNTRUSTED_STAGE44_FLAGS)
            and isinstance(option_catalog.partitions, tuple)
            and 1 <= len(option_catalog.partitions) <= 128
            and type(option_catalog.snapshot_count) is int
            and 1 <= option_catalog.snapshot_count <= 20000
            and option_catalog.first_observed_at <= history.first_observed_at
            and option_catalog.last_observed_at >= history.last_observed_at
        )
        if valid_opts:
            try:
                valid_opts = any(
                    x.preflight.underlying == history.underlying
                    and x.preflight.snapshot_count > 0
                    for x in option_catalog.partitions
                )
            except (AttributeError, TypeError, ValueError):
                valid_opts = False
        if valid_opts and oos.options_catalog_declared_window_observed:
            option_count = oos.related_options_snapshot_count
            valid_opts = (type(option_count) is int and option_count > 0
                          and option_count <= option_catalog.snapshot_count)
        elif valid_opts and not oos.options_catalog_declared_window_observed:
            # The OOS report was produced without the supplied optional
            # catalog; it is NOT jointly observed evidence.
            valid_opts = False
        check("S61-STAGE44-OPTIONS-METADATA", valid_opts,
              "Only source-declared options coverage; quote sync is never inferred")
    needs("S61-REAL-EXECUTION-DATA-MISSING",
          "No authenticated bid/ask depth joined to forecast origin and fill time")
    needs("S61-EXTERNAL-SOURCE-ATTESTATION-MISSING",
          "No independent real NSE market history, historical contract master or licence")
    needs("S61-GLOBAL-RISK-RELEASE-NO-GO",
          "Mandatory risk boundary, live identity, capital atomicity and owner review absent")

    digest = None
    if not errors:
        material = json.dumps([
            "STAGE61_LOCAL_SYNTHETIC_SCORECARD_NOT_TRADING_AUTHORITY_V1",
            history.dataset_id, history.file_sha256,
            oos.local_evidence_digest,
            [x.check_id + ":" + x.status for x in checks],
            str(oos.overall_directional_hit_rate),
            fragments, fee, option_count,
        ], separators=(",", ":"), sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()

    return Stage61FOMarketReadinessScorecard(
        schema_version=1,
        scope="OFFLINE_SYNTHETIC_EVIDENCE_BLOCKER_REPORT_NO_BACKTEST_PNL",
        underlying=history.underlying, futures_symbol=history.symbol,
        futures_dataset_id=history.dataset_id,
        inspected_candles=history.count if history_ok else 0,
        oos_folds=len(oos.folds),
        oos_predictions=oos.total_directional_predictions,
        oos_hit_rate=oos.overall_directional_hit_rate,
        synthetic_execution_fragment_count=fragments,
        synthetic_execution_fee_reserve=fee,
        options_declared_snapshot_count=option_count,
        checks=tuple(checks), structural_conflicts=tuple(errors),
        missing_evidence=tuple(missing),
        mandatory_release_blockers=_MANDATORY_BLOCKERS,
        local_inputs_structurally_consistent=not errors,
        local_evidence_sha256=digest,
    )
