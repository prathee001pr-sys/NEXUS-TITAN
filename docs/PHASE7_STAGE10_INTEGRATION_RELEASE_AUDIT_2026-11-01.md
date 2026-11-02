# NEXUS TITAN Phase 7 — Stage 10 Integration & Release Audit

## Scope
Stage 10 continues from the Stage 9 package in an isolated working copy. Original Stage 9 ZIP was not modified. This stage focuses on integration/release tooling correctness and documentation; it does not add live market feeds, broker connectivity, new trading strategies, or live order execution.

## Audit finding
A clean extracted ZIP uses a `src/` package layout. Running bare `pytest` from the repository root fails import collection unless `src/` is installed or supplied through `PYTHONPATH`. More importantly, `scripts/run_advanced_backtest_suite.py` launched pytest in a subprocess without explicitly supplying the repository `src/` path. This caused the backtest report to incorrectly mark G0 build reproducibility as failed even though the tests passed when invoked with `PYTHONPATH=src`.

## Changes made
- `scripts/run_project_validation.py`: now supplies the repository `src/` path to its pytest subprocess, preserving any existing `PYTHONPATH` entries.
- `scripts/run_advanced_backtest_suite.py`: same explicit `src/` path propagation, so its embedded test evidence matches the actual package layout.
- `README.md`: updates latest stage to Stage 9/10, adds Stage 9 shadow evidence capability, and documents Stage 10 release-tooling scope.
- `docs/MASTER_REQUIREMENTS_REGISTER.md`: adds REL-001 through REL-003 with evidence and explicit boundaries.
- Backtest report regenerated to `reports/phase7_advanced_backtest_report_stage10.json`.

## Verification
- Environment: Python 3.13.5.
- `python scripts/run_project_validation.py`: passed from extracted project root without manually setting `PYTHONPATH`.
- Full suite: 378 passed, 5 subtests passed.
- `python scripts/run_advanced_backtest_suite.py --json-out reports/phase7_advanced_backtest_report_stage10.json`: completed; embedded test evidence reports 378/378 passed.
- G0 build reproducibility: PASSED_CODE_VERIFIED.
- G3 accounting accuracy: PASSED_CODE_VERIFIED.
- G4 risk and approval safety: PASSED_CODE_VERIFIED.
- G5 execution realism: PASSED_CODE_VERIFIED (golden fixtures only; simulator remains simplified).
- G1, G2, G6, G7, G8 and G9: EXTERNAL_INPUT_REQUIRED.
- ZIP integrity and SHA-256 manifest generated after cleanup.

## Backtest interpretation and limitations
- Eight strategy candidates evaluated; none promoted.
- Bundled NIFTY sample is a synthetic 120-daily-bar QA fixture from 2025-01-01 through 2025-04-30, not licensed exchange history.
- The report explicitly warns that the NIFTY index is not an equity-delivery instrument and that the charge setting is a placeholder, not a valid NIFTY execution model.
- Walk-forward/OOS and Monte Carlo evidence is insufficient; the futures fixture has only three trades and is not statistically meaningful.
- ₹50,000 shadow account is a deterministic single-session demo, not multi-day paper observation.
- Strategy promotion remains disabled; live orders transmitted: 0.

## Not done / external evidence still needed
- Licensed NSE 1-minute historical data and historical option-chain coverage.
- Official point-in-time contract master, lot-size changes and exchange calendar evidence.
- Broker/exchange-calibrated statutory charges, SPAN/ELM, queue position, latency, fills and slippage.
- Independent security assessment and operational recovery drills.
- Multi-day shadow observation with trusted daily reconciliation.
- Owner release sign-off.

## Safety
No broker adapter or live-order route was introduced. ₹50,000 remains virtual/research-only. Risk controls, permissions, kill-switch ownership and human approval boundaries remain unchanged. TITAN EVOLVE cannot alter protected controls or promote strategies automatically.
