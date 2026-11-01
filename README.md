# NEXUS TITAN V2

NEXUS TITAN is a modular, trading-first AI research and virtual-trading system.
The V2 repository preserves its original Core, data, security and baseline
backtest modules while integrating selected capabilities from the V6 Phase 6 ZIP.

## Current branch status

Phase 6 integration is being reviewed in the draft pull request:
[Phase 6 integration PR #1](https://github.com/prathee001pr-sys/NEXUS-TITAN-V2/pull/1)

See:
- [Phase 6 integration status](docs/PHASE6_INTEGRATION_STATUS.md)
- [ZIP compatibility test report](docs/PHASE6_ZIP_COMPATIBILITY_TEST_REPORT.md)
- [ZIP source map and collision policy](docs/PHASE6_ZIP_SOURCE_MAP.md)
- [Master requirements register](docs/MASTER_REQUIREMENTS_REGISTER.md)
- [Original V2 data/backtest design notes](docs/HISTORICAL_BACKTEST_ENGINE.md)

## Main capabilities in the integration branch

- Core runtime, events, four-layer memory, permission boundary and audit trail.
- CSV/SQLite historical candle store and data-quality/session validation.
- Original V2 long-only backtest and Moving Average Crossover baseline.
- Separate V6 advanced backtest, technical indicators, six strategy candidates,
  rolling walk-forward validation and Monte Carlo stress analysis.
- ACE declarative agent registry and SQLite-backed Agent Runtime.
- TITAN EVOLVE learning store, 12 supervised specialists, research ingestion,
  optional LLM synthesis, scheduled research and review-only code proposals.
- Indicative Indian transaction-cost model, portfolio risk sizing and deterministic veto.
- Theoretical options Greeks, isolated crypto virtual account and durable paper-order lifecycle.
- Read-only dashboard API and offline command-line runners.

## Setup

Requires Python 3.11 or later.

```bash
python -m pip install -e ".[dev]"
pytest
```

Run the offline validation command:

```bash
python scripts/run_project_validation.py
```

Run a sample historical backtest against your own OHLCV CSV:

```bash
python scripts/run_backtest.py --csv path/to/ohlcv.csv --strategy all
```

Run the local supervised EVOLVE cycle:

```bash
python scripts/run_evolve_agents.py --llm-disabled
```

Run an ACE Agent Runtime help / metrics command:

```bash
python scripts/run_agent_runtime.py --show-metrics
```

Scheduled research is opt-in and requires an explicit exact-host allow-list:

```bash
python scripts/run_evolve_scheduler.py --allow-hosts docs.python.org --list
```

## Safety and limitations

- **Historical research and local virtual/paper execution only.**
- No live broker adapter or real-money order placement is enabled.
- Generated Python is not executed, imported dynamically, or auto-applied.
- ACE agent registration and EVOLVE skill promotion require explicit human approval.
- Self-improvement cannot modify protected risk controls or permissions.
- The included market CSV sample is illustrative only and is not licensed/verified
  historical exchange data.
- Options Greeks are theoretical, not an options-chain historical backtest.
- Crypto virtual trading is isolated from Indian equity capital.
- Indian statutory cost rates are indicative and need broker/exchange contract-note
  reconciliation before being used for any financial decision.
- Passing unit tests does not prove profitability, data provenance or production readiness.

The sample files `data/market_sample.csv` and `data/nifty_daily_sample.csv` are synthetic smoke-test fixtures, not real NSE history. Do not use them for trading conclusions.

The integration PR remains draft until source/API parity, risk/accounting edge cases,
security, data licensing and end-to-end acceptance checks are reviewed.
