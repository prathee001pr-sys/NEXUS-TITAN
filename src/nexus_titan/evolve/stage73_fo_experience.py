"""Stage73: bounded F&O EVOLVE experience memory, strictly research-only.

Records predeclared binary forecasts before outcomes, compares paired OOS
probabilities with the existing calibrator. No model training, orders, or
strategy promotion. Hash-chain is local/tamper-evident, not signed or durable.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from nexus_titan.derivatives.stage72_expiry_iv_research import Stage72OptionsResearchReport
from nexus_titan.intelligence.calibration import CalibrationObservation, ProbabilityCalibrator

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z", re.ASCII)
_SHA = re.compile(r"[a-fA-F0-9]{64}\Z", re.ASCII)
_REGIMES = ("TREND", "RANGE", "HIGH_VOL", "UNCERTAIN")
_GENESIS = "0" * 64


class Stage73Blocked(ValueError):
    """Research event is inconsistent or cannot be admitted."""


@dataclass(frozen=True, slots=True)
class FOForecast:
    episode_id: str
    model_id: str
    probability_up: float
    underlying: str
    regime: str
    stage72_sha256: str
    stage71_sha256: str
    observed_at: datetime
    predicted_at: datetime
    horizon_at: datetime
    expiry_cutoff: datetime
    model_training_cutoff: datetime
    evidence_split: str = "OUT_OF_SAMPLE"
    event_definition: str = "UNDERLYING_UP_AT_HORIZON"


@dataclass(frozen=True, slots=True)
class FOOutcome:
    episode_id: str
    up: bool
    resolved_at: datetime
    declared_label_sha256: str


@dataclass(frozen=True, slots=True)
class FOJournal:
    kind: str
    key: str
    canonical_payload: str
    previous_sha256: str
    entry_sha256: str


@dataclass(frozen=True, slots=True)
class FORegimeScore:
    model_id: str
    regime: str
    count: int
    brier: float


@dataclass(frozen=True, slots=True)
class FOEvolveReview:
    champion: str
    challenger: str
    champion_calibration: object
    challenger_calibration: object
    paired_count: int
    unpaired_count: int
    unresolved_count: int
    champion_paired_brier: float | None
    challenger_paired_brier: float | None
    challenger_minus_champion_brier: float | None
    lower_challenger_brier_observed: bool
    research_review_suggested: bool
    regime_scores: tuple[FORegimeScore, ...]
    journal_head_sha256: str
    review_sha256: str
    blockers: tuple[str, ...]
    independent_exchange_data_verified: bool = False
    independently_verified_outcomes: bool = False
    real_oos_protocol_verified: bool = False
    option_trade_pnl_verified: bool = False
    model_weights_updated: bool = False
    strategy_promotion_authorized: bool = False
    paper_order_authorized: bool = False
    live_trading_enabled: bool = False
    broker_orders_transmitted: int = 0
    verdict: str = "STAGE73_RESEARCH_ONLY_NO_GO"


def _aware(t: datetime, name: str) -> datetime:
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
        raise Stage73Blocked(name + " must be timezone-aware")
    return t.astimezone(timezone.utc)


def _id(s: str, label: str) -> str:
    if not isinstance(s, str) or _ID.fullmatch(s) is None:
        raise Stage73Blocked(label + " is not a valid bounded identifier")
    return s


def _sha(s: str, label: str) -> str:
    if not isinstance(s, str) or _SHA.fullmatch(s) is None:
        raise Stage73Blocked(label + " must be SHA-256 hex")
    return s.lower()


def _serialized(item: object) -> str:
    return json.dumps(asdict(item), sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=lambda v: v.isoformat())


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class Stage73FOExperienceMemory:
    """Append-only in-memory research experience; not independent attestations."""

    def __init__(self, *, max_forecasts: int = 10000):
        if type(max_forecasts) is not int or not 2 <= max_forecasts <= 20000:
            raise Stage73Blocked("Invalid record budget")
        self.max_forecasts = max_forecasts
        self._forecasts: dict[tuple[str, str], FOForecast] = {}
        self._outcomes: dict[str, FOOutcome] = {}
        self._journal: list[FOJournal] = []

    @property
    def journal_head_sha256(self) -> str:
        return self._journal[-1].entry_sha256 if self._journal else _GENESIS

    def _append(self, kind: str, key: str, item: object) -> None:
        payload = _serialized(item)
        prev = self.journal_head_sha256
        digest = _hash(json.dumps([prev, kind, key, payload], separators=(",", ":")))
        self._journal.append(FOJournal(kind, key, payload, prev, digest))

    def verify_local_integrity(self) -> bool:
        previous = _GENESIS
        forecasts: dict[tuple[str, str], str] = {}
        outcomes: dict[str, str] = {}
        for entry in self._journal:
            if not isinstance(entry, FOJournal) or entry.previous_sha256 != previous:
                return False
            actual = _hash(json.dumps(
                [previous, entry.kind, entry.key, entry.canonical_payload],
                separators=(",", ":")))
            if actual != entry.entry_sha256:
                return False
            if entry.kind == "FORECAST":
                parts = entry.key.split("|")
                if len(parts) != 2 or tuple(parts) in forecasts:
                    return False
                forecasts[(parts[0], parts[1])] = entry.canonical_payload
            elif entry.kind == "OUTCOME":
                if entry.key in outcomes:
                    return False
                outcomes[entry.key] = entry.canonical_payload
            else:
                return False
            previous = actual
        if set(forecasts) != set(self._forecasts) or set(outcomes) != set(self._outcomes):
            return False
        try:
            return (all(_serialized(v) == forecasts[k] for k, v in self._forecasts.items())
                    and all(_serialized(v) == outcomes[k] for k, v in self._outcomes.items()))
        except (TypeError, ValueError):
            return False

    def add_forecast(
        self, report: Stage72OptionsResearchReport, *, episode_id: str,
        model_id: str, probability_up: float, regime: str,
        predicted_at: datetime, horizon_at: datetime,
        model_training_cutoff: datetime,
    ) -> FOForecast:
        if not self.verify_local_integrity():
            raise Stage73Blocked("Local research journal integrity failed")
        episode = _id(episode_id, "episode_id")
        model = _id(model_id, "model_id")
        if (episode, model) in self._forecasts or episode in self._outcomes:
            raise Stage73Blocked("Duplicate forecast or already resolved episode")
        if len(self._forecasts) >= self.max_forecasts:
            raise Stage73Blocked("Forecast budget exceeded")
        if not isinstance(report, Stage72OptionsResearchReport):
            raise Stage73Blocked("Stage72 typed report required")
        flags = (
            "contract_master_independently_authenticated",
            "vendor_and_licence_independently_authenticated",
            "official_expiry_cutoff_authenticated",
            "tradeable_bid_ask_depth_verified",
            "model_calibration_or_accuracy_verified",
            "expiry_settlement_and_costs_verified",
            "strategy_promotion_authorized",
            "paper_order_authorized",
            "live_trading_enabled",
        )
        if (report.release_verdict != "STAGE72_IV_GREEKS_RESEARCH_ONLY_NO_GO"
                or any(getattr(report, k, None) is not False for k in flags)
                or type(report.broker_orders_transmitted) is not int
                or report.broker_orders_transmitted != 0
                or not isinstance(report.rows, tuple) or not report.rows):
            raise Stage73Blocked("Stage72 report has unverified authority or no research rows")
        if report.underlying not in ("NIFTY", "BANKNIFTY"):
            raise Stage73Blocked("Unsupported F&O underlying")
        if type(regime) is not str or regime not in _REGIMES:
            raise Stage73Blocked("Invalid research market regime")
        if (type(probability_up) not in (float, int) or not math.isfinite(probability_up)
                or not 0 <= probability_up <= 1):
            raise Stage73Blocked("Probability must be finite in [0,1]")
        observed = _aware(report.observation_time, "Stage72 observation")
        predicted = _aware(predicted_at, "Prediction")
        horizon = _aware(horizon_at, "Horizon")
        expiry = _aware(report.declared_expiry_cutoff, "Declared expiry")
        train = _aware(model_training_cutoff, "Training cutoff")
        if not (train <= observed <= predicted <= observed + timedelta(seconds=120)
                and predicted < horizon <= expiry):
            raise Stage73Blocked("Future knowledge, stale features or invalid horizon")
        rec = FOForecast(
            episode, model, float(probability_up), report.underlying,
            regime, _sha(report.research_output_sha256, "Stage72 source"),
            _sha(report.source_alignment_sha256, "Stage71 source"),
            observed, predicted, horizon, expiry, train,
        )
        for prior in self._forecasts.values():
            if prior.episode_id != episode:
                continue
            for field in (
                "underlying", "regime", "stage72_sha256", "stage71_sha256",
                "observed_at", "predicted_at", "horizon_at",
                "expiry_cutoff", "evidence_split", "event_definition",
            ):
                if getattr(prior, field) != getattr(rec, field):
                    raise Stage73Blocked("Unfair model comparison: differing episode inputs")
        self._forecasts[(episode, model)] = rec
        self._append("FORECAST", episode + "|" + model, rec)
        return rec

    def record_outcome(
        self, *, episode_id: str, up: bool, resolved_at: datetime,
        declared_label_sha256: str,
    ) -> FOOutcome:
        if not self.verify_local_integrity():
            raise Stage73Blocked("Local research journal integrity failed")
        episode = _id(episode_id, "episode_id")
        if episode in self._outcomes:
            raise Stage73Blocked("Outcome replay rejected")
        linked = [v for v in self._forecasts.values() if v.episode_id == episode]
        if not linked:
            raise Stage73Blocked("Outcome cannot precede forecasts")
        if type(up) is not bool:
            raise Stage73Blocked("Outcome label must be bool")
        when = _aware(resolved_at, "Outcome")
        if any(not f.predicted_at < f.horizon_at <= when <= f.expiry_cutoff for f in linked):
            raise Stage73Blocked("Outcome before horizon or after declared expiry")
        rec = FOOutcome(episode, up, when, _sha(declared_label_sha256, "Label declaration"))
        self._outcomes[episode] = rec
        self._append("OUTCOME", episode, rec)
        return rec

    def compare(
        self, *, champion: str, challenger: str,
        min_paired_samples: int = 100,
    ) -> FOEvolveReview:
        if not self.verify_local_integrity():
            raise Stage73Blocked("Local research journal integrity failed")
        a, b = _id(champion, "champion"), _id(challenger, "challenger")
        if a == b:
            raise Stage73Blocked("Distinct model IDs required")
        if type(min_paired_samples) is not int or not 2 <= min_paired_samples <= 10000:
            raise Stage73Blocked("Invalid minimum paired sample count")
        by_model: dict[str, dict[str, FOForecast]] = {a: {}, b: {}}
        for (ep, model), f in self._forecasts.items():
            if model in by_model and ep in self._outcomes:
                if f.evidence_split != "OUT_OF_SAMPLE":
                    raise Stage73Blocked("Only held-out OOS evidence accepted")
                by_model[model][ep] = f
        shared = sorted(set(by_model[a]) & set(by_model[b]))
        unmatched = set(by_model[a]) ^ set(by_model[b])
        calibrations = {}
        regime_scores = []
        for model in (a, b):
            calibration_inputs = [
                CalibrationObservation(
                    prediction_id=ep, probability=f.probability_up,
                    outcome=self._outcomes[ep].up,
                    predicted_at=f.predicted_at,
                    resolved_at=self._outcomes[ep].resolved_at,
                    evidence_split="OUT_OF_SAMPLE",
                )
                for ep, f in sorted(by_model[model].items())
            ]
            calibrations[model] = ProbabilityCalibrator(
                min_samples=min_paired_samples, bin_count=10,
            ).evaluate(calibration_inputs)
            for regime in _REGIMES:
                records = [f for f in by_model[model].values() if f.regime == regime]
                if records:
                    brier = math.fsum(
                        (f.probability_up - float(self._outcomes[f.episode_id].up))**2
                        for f in records
                    ) / len(records)
                    regime_scores.append(FORegimeScore(
                        model, regime, len(records), round(brier, 8)))
        def paired_brier(model: str) -> float | None:
            return (math.fsum(
                (by_model[model][ep].probability_up - float(self._outcomes[ep].up))**2
                for ep in shared
            ) / len(shared)) if shared else None
        a_brier, b_brier = paired_brier(a), paired_brier(b)
        delta = b_brier - a_brier if a_brier is not None and b_brier is not None else None
        improved = delta is not None and delta < 0
        enough = len(shared) >= min_paired_samples and not unmatched
        blockers = []
        if not enough:
            blockers.append("INSUFFICIENT_OR_UNPAIRED_OUT_OF_SAMPLE_EVIDENCE")
        if not improved:
            blockers.append("NO_OBSERVED_PAIRED_BRIER_IMPROVEMENT")
        blockers.extend((
            "LABELS_AND_TIMESTAMPS_NOT_INDEPENDENTLY_AUTHENTICATED",
            "PROFITABILITY_AND_STRATEGY_PROMOTION_NOT_PROVEN",
        ))
        audit = _hash(json.dumps(
            [self.journal_head_sha256, a, b, shared, min_paired_samples,
             a_brier, b_brier], separators=(",", ":"), allow_nan=False,
        ))
        return FOEvolveReview(
            champion=a, challenger=b,
            champion_calibration=calibrations[a],
            challenger_calibration=calibrations[b],
            paired_count=len(shared), unpaired_count=len(unmatched),
            unresolved_count=len({ep for ep, _ in self._forecasts} - set(self._outcomes)),
            champion_paired_brier=a_brier, challenger_paired_brier=b_brier,
            challenger_minus_champion_brier=delta,
            lower_challenger_brier_observed=improved,
            research_review_suggested=enough and improved,
            regime_scores=tuple(regime_scores),
            journal_head_sha256=self.journal_head_sha256,
            review_sha256=audit, blockers=tuple(blockers),
        )
