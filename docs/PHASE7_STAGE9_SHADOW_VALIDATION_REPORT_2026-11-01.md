# NEXUS TITAN Phase 7 — Stage 9 Shadow Validation Report

## Scope
Stage 9 adds an offline evidence framework for future multi-session ₹50,000 virtual shadow observation. It does not connect to a broker, exchange, live data provider, or real account. Existing Stage 8 source was retained; changes are additive.

## New components
- `src/nexus_titan/shadow/validation.py`
  - Append-only JSONL evidence ledger with SHA-256 hash chaining and verification on reopen.
  - Monotonic, timezone-aware event timestamps and India session-date validation.
  - Session cash reconciliation: expected close = opening balance + realized P&L - fees; also checks event counts.
  - Fail-closed readiness gate requiring minimum sessions, fully reconciled sessions, minimum closed trades, verified licensed data provenance and verified execution calibration.
  - Readiness output is for human review only. Strategy promotion is never automatic and live trading remains disabled.
- `tests/test_stage9_shadow_validation.py`
  - hash-chain integrity/tamper, reopen, monotonic timestamps, session reconciliation, readiness gating and invalid-input coverage.

## Verification
- `PYTHONPATH=src python scripts/run_project_validation.py`: passed.
- Full test suite: 378 passed, 5 subtests passed.
- `PYTHONPATH=src python scripts/run_advanced_backtest_suite.py --json-out reports/phase7_advanced_backtest_report_stage9.json`: completed successfully.
- Compile check included in project validation.

## Backtest evidence and limits
The generated report explicitly identifies the bundled NIFTY dataset as a synthetic 120-daily-bar smoke fixture (2025-01-01 through 2025-04-30), not licensed exchange history. Its manifest is not verified and strategy promotion is disallowed. Eight strategies were evaluated; no strategy was promoted. Walk-forward evidence is thin (for example, one reported candidate has only two OOS trades against a 30-trade threshold). The futures demo has only three trades and is not statistically meaningful. The ₹50,000 paper account result is a deterministic single-session demo, not multi-day shadow evidence. G0/G3/G4/G5 are code-verified; G1/G2/G6/G7/G8/G9 still require external evidence or owner sign-off.

## Not implemented / external dependencies
- Actual licensed 1-minute NSE history and option-chain history.
- Official point-in-time contract master and holiday/session calendar verification.
- Broker/exchange-calibrated queue, fills, latency, slippage and statutory costs.
- Multi-day unattended paper observation and independent security assessment.
- Real broker reconciliation, live order submission, automatic strategy promotion.

## Safety
No broker adapter or live-order path was added. The ₹50,000 virtual framework remains research-only. Risk limits, permissions and kill-switch ownership remain outside EVOLVE and the new shadow gate.
