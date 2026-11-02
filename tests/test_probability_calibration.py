from datetime import datetime, timedelta, timezone

import pytest

from nexus_titan.intelligence.calibration import (
    CalibrationObservation,
    ProbabilityCalibrator,
)


BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(index: int, probability: float, outcome: bool, **changes):
    values = {
        "prediction_id": f"pred-{index}",
        "probability": probability,
        "outcome": outcome,
        "predicted_at": BASE + timedelta(minutes=index),
        "resolved_at": BASE + timedelta(minutes=index + 1),
        "evidence_split": "OUT_OF_SAMPLE",
    }
    values.update(changes)
    return CalibrationObservation(**values)


def test_empty_report_is_explicitly_insufficient():
    report = ProbabilityCalibrator(min_samples=2).evaluate([])
    assert report.sample_count == 0
    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert report.brier_score is None
    assert report.expected_calibration_error is None
    assert len(report.bins) == 10


def test_perfectly_calibrated_buckets_have_zero_brier_and_ece():
    samples = [observation(i, 0.0, False) for i in range(5)]
    samples += [observation(i + 5, 1.0, True) for i in range(5)]
    report = ProbabilityCalibrator(min_samples=10, bin_count=10).evaluate(samples)
    assert report.sufficient_evidence is True
    assert report.status == "READY_FOR_REVIEW"
    assert report.brier_score == 0.0
    assert report.expected_calibration_error == 0.0
    assert report.bins[0].sample_count == 5
    assert report.bins[-1].sample_count == 5


def test_under_sampled_report_does_not_claim_calibration_readiness():
    report = ProbabilityCalibrator(min_samples=3).evaluate([
        observation(1, 0.8, True), observation(2, 0.8, False)
    ])
    assert report.sufficient_evidence is False
    assert report.status == "INSUFFICIENT_EVIDENCE"
    assert report.brier_score == pytest.approx(0.34)
    assert report.expected_calibration_error == pytest.approx(0.3)


@pytest.mark.parametrize("probability", [-0.01, 1.01, float("nan"), float("inf"), True])
def test_invalid_probability_is_rejected(probability):
    with pytest.raises(ValueError):
        ProbabilityCalibrator().evaluate([observation(1, probability, True)])


def test_in_sample_observation_is_rejected():
    with pytest.raises(ValueError, match="OUT_OF_SAMPLE"):
        ProbabilityCalibrator().evaluate([
            observation(1, 0.5, True, evidence_split="TRAIN")
        ])


def test_duplicate_prediction_id_is_rejected():
    first = observation(1, 0.5, True)
    duplicate = observation(2, 0.6, False, prediction_id=first.prediction_id)
    with pytest.raises(ValueError, match="duplicate"):
        ProbabilityCalibrator().evaluate([first, duplicate])


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        ProbabilityCalibrator().evaluate([
            observation(1, 0.5, True, predicted_at=datetime(2026, 1, 1))
        ])


def test_outcome_must_be_boolean_and_resolve_after_forecast():
    with pytest.raises(ValueError, match="outcome must be a bool"):
        ProbabilityCalibrator().evaluate([observation(1, 0.5, 1)])
    with pytest.raises(ValueError, match="later than"):
        ProbabilityCalibrator().evaluate([
            observation(1, 0.5, True, resolved_at=BASE)
        ])


def test_bin_edges_are_consistent_and_probability_one_is_in_last_bucket():
    values = [
        observation(0, 0.0, False),
        observation(1, 0.1, False),
        observation(2, 0.5, True),
        observation(3, 1.0, True),
    ]
    report = ProbabilityCalibrator(bin_count=10, min_samples=4).evaluate(values)
    assert report.bins[0].sample_count == 1
    assert report.bins[1].sample_count == 1
    assert report.bins[5].sample_count == 1
    assert report.bins[9].sample_count == 1


def test_wrong_observation_type_is_rejected():
    with pytest.raises(TypeError):
        ProbabilityCalibrator().evaluate([object()])
