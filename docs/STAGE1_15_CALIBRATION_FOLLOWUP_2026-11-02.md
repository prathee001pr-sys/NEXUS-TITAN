# Stage 1–15 Calibration Follow-up — 02 November 2026

## Exact local candidate
- Archive: `NEXUS_TITAN_Stage1-15_Canonical_Integrated_With_Calibration_2026-11-02.zip`
- SHA-256: `90b9db62b6890e4b95721ea9cd33915620294c095ec2c61f582def2393ce73c8`
- Archive entries: 232
- Python source files under `src/nexus_titan/`: 96
- Test modules: 56
- Uncompressed archive size: 1,789,726 bytes
- Includes `intelligence/calibration.py` and `tests/test_probability_calibration.py`.

## Revalidation performed from a fresh extraction
Environment: Python 3.13 in the local verification container. The project declares Python >=3.11 and CI uses Python 3.11.

Commands:
```bash
python -m pip install -e '.[dev]' --no-build-isolation
python -m pytest -o addopts='' -q
python -m compileall -q src scripts
python scripts/run_project_validation.py
```

Results:
- **426 passed, 5 subtests passed** (7.20s).
- `compileall` passed.
- Offline project validation completed successfully.
- ZIP sidecar checksum verified successfully.

## Calibration scope
The calibrator calculates Brier score, fixed-width reliability bins and expected calibration error from explicitly supplied, resolved OOS binary observations. It rejects non-OOS labels, duplicate prediction IDs, invalid probabilities, non-boolean outcomes, naive timestamps and unresolved/ill-ordered observations.

The output is diagnostic only. The candidate's consensus result remains `UNCALIBRATED`; this module is not wired to authorize trades or strategy promotion. The caller still owns the predeclared outcome definition and trustworthy OOS lineage. A minimum sample count only makes a report `READY_FOR_REVIEW`, not calibrated or production-verified.

## GitHub evidence boundary
- PR #3 (`feature/oos-probability-calibration`, head `fa8c34eba862108d6cd333c59964c4e3cc6e6405`) has a separate hosted Actions success, run #41393193730, with 183 tests. It is still draft and based on `main`.
- PR #1 remains the Phase 6 integration branch. Its hosted run #41388360519 passed 286 tests + 5 subtests at head `1e9436f6b82baf55eb33d4b98ff0cf47dc6fd69c`.
- The exact 426-test archive above has been freshly validated locally but is **not** yet committed as source to PR #1 or verified by hosted CI against its own commit.
- This document is evidence bookkeeping only. It does not merge PRs, change source code, or approve a release.

## Release status
The release preflight remains `BLOCKED_EXTERNAL_EVIDENCE`. Licensed point-in-time market data, independent security review, target-environment backup/restore drills, multi-day ₹50,000 shadow evidence and owner sign-off remain outstanding. Live trading remains disabled.
