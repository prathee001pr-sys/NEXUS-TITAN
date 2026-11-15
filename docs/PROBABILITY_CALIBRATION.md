# OOS Probability Calibration Diagnostics

## Purpose and safety boundary

`nexus_titan.intelligence.calibration.ProbabilityCalibrator` computes descriptive reliability diagnostics from resolved, explicitly out-of-sample binary observations. It does not generate signals, create orders, authorize trades, promote strategies, or modify risk controls. The independent Risk & Veto remains authoritative. The current `ConsensusEngine` confidence field remains `UNCALIBRATED`; this module is not yet wired into the signal path.

## Required observation contract

Each `CalibrationObservation` carries a unique `prediction_id`, a probability in [0, 1], a boolean outcome, timezone-aware `predicted_at` and `resolved_at` timestamps, and `evidence_split="OUT_OF_SAMPLE"`. The resolved timestamp must be later than the prediction timestamp. Duplicate IDs, training/in-sample labels, invalid probabilities, non-boolean outcomes and naive timestamps are rejected.

The caller must define the binary outcome in advance (for example, a target-before-stop result over a fixed horizon), preserve the prediction-time lineage, and ensure walk-forward separation. The calibrator cannot prove that a caller's OOS label is truthful.

## Diagnostics

- **Brier score:** mean squared error between probability and binary outcome.
- **Expected calibration error (ECE):** count-weighted absolute difference between average forecast probability and observed outcome frequency in equal-width bins.
- **Reliability bins:** sample count, mean forecast probability and observed frequency for each bin.
- **Minimum evidence gate:** default 100 resolved OOS observations. Below this, status is `INSUFFICIENT_EVIDENCE`; at or above it, status is `READY_FOR_REVIEW`, not a strategy promotion or verified-calibration state.

Empty buckets are retained as null-valued bins; probability 1.0 is included in the final bin.

## Example

```python
from nexus_titan.intelligence.calibration import (
    CalibrationObservation,
    ProbabilityCalibrator,
)

report = ProbabilityCalibrator(bin_count=10, min_samples=100).evaluate(observations)
print(report.status, report.brier_score, report.expected_calibration_error)
```

Use only archived predictions whose outcomes have fully resolved. Do not use the calibration report as a replacement for market-state quality, strategy validation, the veto layer, or human approval.
