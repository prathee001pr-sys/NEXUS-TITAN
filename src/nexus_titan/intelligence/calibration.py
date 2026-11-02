"""Out-of-sample probability calibration diagnostics.

This module measures how well previously recorded probabilities match binary
outcomes. It does not generate trading signals, promote strategies, or replace
the independent risk veto. Only resolved, explicitly out-of-sample observations
are accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CalibrationObservation:
    """A probability forecast and its later, independently resolved outcome."""

    prediction_id: str
    probability: float
    outcome: bool
    predicted_at: datetime
    resolved_at: datetime
    evidence_split: str = "OUT_OF_SAMPLE"


@dataclass(frozen=True, slots=True)
class ReliabilityBin:
    lower_bound: float
    upper_bound: float
    sample_count: int
    mean_probability: float | None
    observed_frequency: float | None


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    sample_count: int
    bin_count: int
    brier_score: float | None
    expected_calibration_error: float | None
    bins: tuple[ReliabilityBin, ...]
    sufficient_evidence: bool
    status: str
    limitations: tuple[str, ...]


class ProbabilityCalibrator:
    """Compute reliability diagnostics from clean OOS binary observations.

    Scores are descriptive. READY_FOR_REVIEW requires the configured minimum
    OOS sample count; it is not strategy promotion or trade authorization.
    """

    def __init__(self, *, bin_count: int = 10, min_samples: int = 100) -> None:
        if isinstance(bin_count, bool) or not isinstance(bin_count, int) or not 2 <= bin_count <= 100:
            raise ValueError("bin_count must be an integer between 2 and 100")
        if isinstance(min_samples, bool) or not isinstance(min_samples, int) or min_samples < 1:
            raise ValueError("min_samples must be a positive integer")
        self.bin_count = bin_count
        self.min_samples = min_samples

    @staticmethod
    def _validate(item: CalibrationObservation) -> None:
        if not isinstance(item, CalibrationObservation):
            raise TypeError("observations must be CalibrationObservation instances")
        if not isinstance(item.prediction_id, str) or not item.prediction_id.strip():
            raise ValueError("prediction_id must be a non-empty string")
        if isinstance(item.probability, bool) or not isinstance(item.probability, (int, float)):
            raise ValueError("probability must be a finite number in [0, 1]")
        if not isfinite(float(item.probability)) or not 0.0 <= float(item.probability) <= 1.0:
            raise ValueError("probability must be a finite number in [0, 1]")
        if type(item.outcome) is not bool:
            raise ValueError("outcome must be a bool")
        if item.evidence_split != "OUT_OF_SAMPLE":
            raise ValueError("only OUT_OF_SAMPLE observations are accepted")
        for value, name in ((item.predicted_at, "predicted_at"), (item.resolved_at, "resolved_at")):
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if item.resolved_at <= item.predicted_at:
            raise ValueError("resolved_at must be later than predicted_at")

    def evaluate(self, observations: Iterable[CalibrationObservation]) -> CalibrationReport:
        items = tuple(observations)
        seen: set[str] = set()
        for item in items:
            self._validate(item)
            if item.prediction_id in seen:
                raise ValueError(f"duplicate prediction_id: {item.prediction_id}")
            seen.add(item.prediction_id)

        if not items:
            return CalibrationReport(
                sample_count=0,
                bin_count=self.bin_count,
                brier_score=None,
                expected_calibration_error=None,
                bins=tuple(
                    ReliabilityBin(i / self.bin_count, (i + 1) / self.bin_count, 0, None, None)
                    for i in range(self.bin_count)
                ),
                sufficient_evidence=False,
                status="INSUFFICIENT_EVIDENCE",
                limitations=("No resolved out-of-sample observations were supplied.",),
            )

        buckets: list[list[CalibrationObservation]] = [[] for _ in range(self.bin_count)]
        squared_error = 0.0
        for item in items:
            probability = float(item.probability)
            squared_error += (probability - float(item.outcome)) ** 2
            index = min(int(probability * self.bin_count), self.bin_count - 1)
            buckets[index].append(item)

        n = len(items)
        brier = squared_error / n
        reliability_bins: list[ReliabilityBin] = []
        weighted_gap = 0.0
        for index, bucket in enumerate(buckets):
            lower = index / self.bin_count
            upper = (index + 1) / self.bin_count
            if bucket:
                mean_probability = sum(float(x.probability) for x in bucket) / len(bucket)
                observed_frequency = sum(int(x.outcome) for x in bucket) / len(bucket)
                weighted_gap += (len(bucket) / n) * abs(mean_probability - observed_frequency)
            else:
                mean_probability = None
                observed_frequency = None
            reliability_bins.append(ReliabilityBin(
                lower, upper, len(bucket), mean_probability, observed_frequency
            ))

        sufficient = n >= self.min_samples
        limitations: list[str] = []
        if not sufficient:
            limitations.append(
                f"Need at least {self.min_samples} resolved OOS observations; received {n}."
            )
        limitations.append(
            "Calibration depends on a predeclared outcome definition, sampling process, "
            "and valid walk-forward separation."
        )
        limitations.append(
            "These diagnostics do not authorize trades, strategy promotion, or risk-limit changes."
        )
        return CalibrationReport(
            sample_count=n,
            bin_count=self.bin_count,
            brier_score=brier,
            expected_calibration_error=weighted_gap,
            bins=tuple(reliability_bins),
            sufficient_evidence=sufficient,
            status="READY_FOR_REVIEW" if sufficient else "INSUFFICIENT_EVIDENCE",
            limitations=tuple(limitations),
        )
