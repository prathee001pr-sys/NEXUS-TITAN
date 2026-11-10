"""Stage106: synthetic-only research holdout chronology and lineage gate.

No model training, target leakage permission, trade signal, actual accuracy,
strategy promotion or external data verification is claimed here.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from hashlib import sha256
import json
import re
from .stage103_readonly_assurance_gate import Stage103AssuranceReport
from .stage104_historical_catalog_review import Stage104Catalog
from .stage105_execution_stress_review import Stage105ExecutionPreview

class Stage106Blocked(ValueError):
    pass

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_HEX = re.compile(r"[a-f0-9]{64}\Z", re.ASCII)

@dataclass(frozen=True, slots=True)
class Stage106SyntheticObservation:
    forecast_at_ist: str
    outcome_known_at_ist: str
    predicted_direction: int  # -1, 0, +1 only
    synthetic_observed_direction: int  # -1, 0, +1 only
    source: str = "LOCAL_SYNTHETIC_TEST_ONLY"

@dataclass(frozen=True, slots=True)
class Stage106ResearchReview:
    experiment_id: str
    symbol: str
    currency: str
    training_catalog_sha256: str
    holdout_catalog_sha256: str
    stage103_review_sha256: str
    stage105_scenario_sha256: str
    observation_count: int
    illustrative_direction_matches: int
    evidence_sha256: str
    lookahead_window_overlap: bool = False
    out_of_sample_market_evidence_verified: bool = False
    real_accuracy_verified: bool = False
    autonomous_strategy_promotion: bool = False
    live_trading_enabled: bool = False
    verdict: str = "SYNTHETIC_HOLDOUT_STRUCTURE_ONLY_NO_GO"


def _minute(raw: str) -> datetime:
    if type(raw) is not str or len(raw) > 40:
        raise Stage106Blocked("Invalid observation time")
    try: t = datetime.fromisoformat(raw)
    except (TypeError, ValueError) as exc: raise Stage106Blocked("Malformed observation clock") from exc
    if (t.utcoffset() != timedelta(hours=5, minutes=30) or t.isoformat() != raw
        or t.second != 0 or t.microsecond != 0 or t.weekday() > 4
        or not time(9, 15) <= t.time() < time(15, 30)):
        raise Stage106Blocked("Observation clock must be canonical session IST minute")
    return t


def review_stage106_holdout(
    experiment_id: str,
    training: Stage104Catalog,
    holdout: Stage104Catalog,
    assurance: Stage103AssuranceReport,
    execution: Stage105ExecutionPreview,
    observations: list[Stage106SyntheticObservation] | tuple[Stage106SyntheticObservation, ...],
) -> Stage106ResearchReview:
    if (type(experiment_id) is not str or not _ID.fullmatch(experiment_id)
        or type(training) is not Stage104Catalog or type(holdout) is not Stage104Catalog
        or type(assurance) is not Stage103AssuranceReport
        or type(execution) is not Stage105ExecutionPreview
        or type(observations) not in (list, tuple) or not 2 <= len(observations) <= 100):
        raise Stage106Blocked("Exact typed, bounded synthetic OOS inputs required")
    for c in (training, holdout):
        if (c.symbol not in ("NIFTY", "BANKNIFTY") or c.currency != "INR"
            or c.complete_trading_calendar_verified is not False
            or c.independent_data_provider_verified is not False
            or c.historical_15y_coverage_verified is not False
            or c.strategy_signal_authorized is not False or c.live_trading_enabled is not False
            or c.verdict != "SYNTHETIC_CATALOG_STRUCTURE_ONLY_NO_GO"
            or type(c.catalog_sha256) is not str or not _HEX.fullmatch(c.catalog_sha256)
            or type(c.source_window_hashes) is not tuple
            or type(c.session_count) is not int or c.session_count != len(c.source_window_hashes)
            or type(c.minute_bar_count) is not int or c.minute_bar_count < c.session_count):
            raise Stage106Blocked("Training/holdout catalogs not eligible for synthetic research")
    if (training.symbol != holdout.symbol or training.symbol != assurance.underlying
        or training.symbol != execution.underlying
        or training.last_date >= holdout.first_date
        or training.catalog_sha256 == holdout.catalog_sha256
        or set(training.source_window_hashes) & set(holdout.source_window_hashes)):
        raise Stage106Blocked("Holdout leakage, source overlap, or wrong symbol")
    if (assurance.synthetic_inputs_consistent is not True
        or assurance.source_authenticity_verified is not False
        or assurance.expiry_to_account_linkage_verified is not False
        or assurance.broker_fills_reconciled is not False
        or assurance.real_market_shadow_verified is not False
        or assurance.live_trading_enabled is not False or assurance.trade_authorized is not False
        or assurance.verdict != "CROSS_STAGE_SYNTHETIC_INTEGRITY_ONLY_NO_GO"
        or type(assurance.review_sha256) is not str or not _HEX.fullmatch(assurance.review_sha256)):
        raise Stage106Blocked("Stage103 assurance is not synthetic/no-go")
    if (execution.currency != "INR" or execution.catalog_sha256 != holdout.catalog_sha256
        or execution.window_sha256 != assurance.historical_window_sha256
        or execution.chain_sha256 != assurance.synthetic_chain_sha256
        or execution.actual_fill_verified is not False
        or execution.execution_liquidity_verified is not False
        or execution.statutory_charges_verified is not False
        or execution.trade_authorized is not False or execution.live_trading_enabled is not False
        or execution.verdict != "SIMULATED_PARTIAL_FILL_COSTS_ONLY_NO_GO"
        or type(execution.scenario_sha256) is not str or not _HEX.fullmatch(execution.scenario_sha256)):
        raise Stage106Blocked("Execution research not linked to the correct synthetic holdout")
    first_bar = _minute(execution.source_first_asof_ist)
    last_bar = _minute(execution.source_last_asof_ist)
    if first_bar > last_bar or first_bar.date().isoformat() != holdout.last_date:
        raise Stage106Blocked("Holdout source-window clock inconsistent")
    previous_outcome: datetime | None = None
    matches = 0
    serial: list[list] = []
    for o in observations:
        if (type(o) is not Stage106SyntheticObservation
            or o.source != "LOCAL_SYNTHETIC_TEST_ONLY"
            or type(o.predicted_direction) is not int
            or type(o.synthetic_observed_direction) is not int
            or o.predicted_direction not in (-1, 0, 1)
            or o.synthetic_observed_direction not in (-1, 0, 1)):
            raise Stage106Blocked("Malformed observation or non-synthetic label")
        start, end = _minute(o.forecast_at_ist), _minute(o.outcome_known_at_ist)
        if (not first_bar <= start < end <= last_bar or start.date() != end.date()
            or not holdout.first_date <= start.date().isoformat() <= holdout.last_date
            or previous_outcome is not None and start <= previous_outcome):
            raise Stage106Blocked("Label leakage, overlap or out-of-holdout forecast")
        previous_outcome = end
        matches += o.predicted_direction == o.synthetic_observed_direction
        serial.append([o.forecast_at_ist, o.outcome_known_at_ist,
                       o.predicted_direction, o.synthetic_observed_direction])
    payload = ["STAGE106_SYNTHETIC_HOLDOUT_V1", experiment_id, training.catalog_sha256,
               holdout.catalog_sha256, assurance.review_sha256, execution.scenario_sha256, serial]
    digest = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    return Stage106ResearchReview(experiment_id, training.symbol, "INR", training.catalog_sha256,
        holdout.catalog_sha256, assurance.review_sha256, execution.scenario_sha256,
        len(observations), matches, digest)
