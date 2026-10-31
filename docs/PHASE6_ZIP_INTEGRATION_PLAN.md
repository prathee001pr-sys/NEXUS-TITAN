# V6 Phase 6 ZIP Integration Plan

## Source of truth

The uploaded `NEXUS_TITAN_V6_Phase6_Agent_Runtime_And_Backtest.zip` is the
reference implementation for Phase 6 Agent Runtime and advanced backtesting.
The existing V2 repository work remains preserved and is not to be discarded
or blindly overwritten.

## ZIP validation evidence

- Extracted archive and ran its tests directly with `PYTHONPATH=src pytest -q`.
- Result: **246 passed, 0 failed**.
- The package installation command could not fetch build dependencies because
  the execution environment had no network access; direct test execution succeeded.
- The ZIP release notes additionally report 48 source files compiled and 88%
  coverage. Those two figures are archive-reported evidence and have not been
  independently re-run in this integration session.

## Integration inventory

| ZIP capability | Planned V2 treatment |
|---|---|
| ACE-controlled Agent Runtime | Integrate as a new governed runtime after its ACE registry and dependencies are present |
| Durable SQLite task queue | Preserve task states, idempotency, bounded retries and fail-closed recovery |
| Agent workflow coordination | Integrate dependency graph, handoff inbox and metrics |
| Advanced backtest engine | Add alongside the existing V2 `backtest_engine.py`; do not replace it until parity and migration tests pass |
| Indicators and strategy catalogue | Integrate without deleting the current V2 Moving Average Crossover baseline |
| Walk-forward/out-of-sample validation | Compare with and extend the current V2 chronological holdout evaluator |
| Indian charges and risk sizing | Bring in only with their required instrument, cost and risk dependencies and tests |

## Existing V2 work to preserve

- OHLCV contracts, market-data quality/session checks, MarketDataService, CSV
  importer, SQLite candle storage and its adapter.
- The existing `BacktestEngine` and its accounting/integration tests.
- `MovingAverageCrossover` and its tests.
- `split_chronologically` / `evaluate_out_of_sample` and their tests.
- Master Requirements Register, CI workflow and all existing Core/security work.

## Safety constraints

- No real-money broker execution or live order placement.
- Do not execute generated agent Python, shell commands or arbitrary network calls.
- Only human-approved declarative agent specifications may be eligible for runtime.
- Only explicitly registered, allowlisted trusted host adapters may execute.
- Risk controls, permissions and live-trading gates remain protected from EVOLVE.
- Do not claim ZIP-reported backtest performance is executable trading P&L where
  the bundled dataset is NIFTY spot proxy data.

## Integration sequence

1. Map every ZIP file against V2 paths and identify collisions/dependencies.
2. Add ACE registry prerequisites and runtime in additive commits; run focused tests.
3. Add advanced backtest engine beside the existing V2 engine; run ZIP backtest tests.
4. Integrate indicators, strategy and validation modules with explicit compatibility
   tests against the current V2 data contracts.
5. Run the full V2 test suite and the imported Phase 6 suite together in CI.
6. Update the Master Requirements Register only with evidence from the resulting CI.

Until these steps pass, Phase 6 integration status is **Planned / partially imported**,
not Tested or Verified. The archive's 246 passing tests validate the archive itself,
not its integration with V2.
