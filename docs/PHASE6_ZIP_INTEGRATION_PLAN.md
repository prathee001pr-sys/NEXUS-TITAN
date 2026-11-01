# V6 Phase 6 ZIP Integration Record

## Source of truth

The uploaded `NEXUS_TITAN_V6_Phase6_Agent_Runtime_And_Backtest.zip` was used
as the Phase 6 reference baseline. The original V2 core, CSV/SQLite data
foundation, basic backtest engine, Moving Average Crossover strategy,
chronological OOS validator, security boundary and requirements register were
preserved.

## Archive validation

- ZIP-alone suite: **246 passed** in its extracted source tree.
- That ZIP-alone result is not the V2 integration test result.
- The V2 integration branch's latest code run at the time of this record passed
  **280 tests and 5 subtests** in GitHub Actions run #41256696389.
- CI evidence: https://github.com/prathee001pr-sys/NEXUS-TITAN-V2/actions/runs/41255869182

## Integrated in `integration/phase6-zip-baseline`

- ACE declarative agent prototypes, strict tool/capability allowlists and named
  human approval before permanent registration.
- SQLite-backed controlled Agent Runtime: task states, idempotency, bounded
  JSON/tool calls, events, retry-safe adapters, workflow dependencies, inbox,
  metrics and fail-closed interrupted-task recovery.
- TITAN EVOLVE learning store, 12 supervised specialists, strategy evidence,
  improvement proposals, source ingestion, opt-in LLM research, scheduled
  research and proposal-only code evolution.
- Advanced historical backtest engine, technical indicators, six candidate
  strategies, rolling walk-forward, Monte Carlo stress testing and promotion gates.
- Canonical market-data validation, configurable Indian charge estimates,
  portfolio risk sizing and deterministic risk veto.
- Theoretical options Greeks/IV, isolated crypto virtual account, virtual order
  lifecycle, durable ledgers, trading decision flow and read-only dashboard API.
- Five offline CLI scripts, workflow example, illustrative OHLCV fixture,
  environment placeholders, source-map document and Phase 5/6 ACE/runtime
  reference documentation.

## Compatibility and source mapping

Inventory check: 48/48 ZIP Python source paths are represented in the branch. Eight files are byte-identical, forty are adapted to V2 interfaces/safety boundaries, and twenty-one additional V2 Python modules remain. Original strategy/validation entry points now expose compatibility exports while the V2-specific strategy and OOS APIs remain available.

All 48 Python source paths from the ZIP have a counterpart in the integration
branch. Where ZIP paths collided with existing V2 baselines, the ZIP catalogue
is exposed as `research/v6_strategies.py` and `research/v6_validation.py`.
The original V2 `research/strategies.py`, `research/validation.py` and
`research/backtest_engine.py` remain intact.

Some modules were adapted to V2 data contracts and safety boundaries instead of
being copied byte-for-byte. The detailed mapping is in
`docs/PHASE6_ZIP_SOURCE_MAP.md`. A complete API/behavior parity audit of every
adapted module is still an acceptance task.

## Existing V2 work retained

- OHLCV candle contract, CSV importer, quality validation, market sessions,
  MarketDataService, SQLite candle persistence and adapters.
- Original `BacktestEngine` and its cash-accounting fixes.
- Original V2 Moving Average Crossover and chronological OOS validator.
- Core config/runtime/events/memory/permissions/audit and CI.
- Master Requirements Register and prior feature documentation.

## Safety constraints

- No real-money broker execution or live order placement.
- Generated Python is not imported or executed; code changes remain proposals.
- Agent registration and EVOLVE skill promotion require explicit named human
  approval; production MFA/authenticated identity is not yet integrated.
- Only explicitly registered, allowlisted trusted host adapters may execute.
- EVOLVE cannot modify protected risk controls, permissions or live trading.
- Bundled NIFTY spot sample performance is synthetic research proxy output, not
  executable cash/futures/options P&L or proof of profitability.
- Options analytics are theoretical; crypto is a separate limited virtual silo.

## Remaining acceptance work

1. Complete a line-by-line API/behavior parity audit for the adapted ZIP modules.
2. Add independently calculated futures/option cost, margin, drawdown and
   stop/target/gap accounting fixtures; do not infer exchange-grade accuracy
   from current unit tests.
3. Connect licensed, verified 15-year one-minute market datasets and approved
   point-in-time instrument/contract metadata.
4. Validate official/broker charge schedules, SPAN/ELM margin, options chain,
   exercise/assignment/physical settlement and partial-fill liquidity.
5. Add exchange historical crypto data, funding/fee/tax reconciliation and
   independent crypto backtesting.
6. Complete security review, authenticated approvals/MFA/ACLs, encrypted DB/key
   management, backups, restore drills, performance/load and operational monitoring.
7. Wire the one-shot research scheduler into a user-controlled deployment.
8. Build the finished authenticated dashboard frontend and mobile operator workflows.
9. Live trading remains out of scope and disabled; it requires a separate approved
   design, controls and compliance review.

## Merge state

This is an open **draft** pull request against `main`, not a merge to `main`.
Keep it draft until source parity and the external-data, financial-accounting,
security and operational acceptance items have been reviewed.
