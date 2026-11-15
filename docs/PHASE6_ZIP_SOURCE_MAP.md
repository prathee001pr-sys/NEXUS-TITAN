# Phase 6 ZIP source map

Reference archive: `NEXUS_TITAN_V6_Phase6_Agent_Runtime_And_Backtest.zip`

The V2 integration branch is additive. Original V2 files are retained where names
or interfaces overlap. All 48 original ZIP Python source paths are represented:
8 files are byte-identical, 40 are adapted, and 21 additional V2 source modules
remain. The original ZIP's 246-test suite has been run unchanged against the
integrated `src/` tree and passed. This is not a blind archive extraction.

## Package mapping

| ZIP package / capability | V2 integration location | Treatment |
|---|---|---|
| `ai_agents/agent_system.py` | `src/nexus_titan/ai_agents/` | Adapted integration; deterministic veto retained |
| `config/` | `src/nexus_titan/config/` | Package support |
| `cost/charges.py` | `src/nexus_titan/cost/` | Integrated with configurable cost schedule; official reconciliation pending |
| `crypto/crypto_engine.py` | `src/nexus_titan/crypto/` | Isolated virtual-account implementation |
| `dashboard/api_service.py` | `src/nexus_titan/dashboard/` | Read-only backend only |
| `data/canonical.py`, `csv_ohlcv.py`, `market_data.py` | `src/nexus_titan/data/` | Additive canonical/CSV/provider boundary; V2 CSV/SQLite store retained |
| `derivatives/options_engine.py` | `src/nexus_titan/derivatives/` | Theoretical Black-Scholes/IV analytics; not an options execution engine |
| `research/backtest.py` | `src/nexus_titan/research/backtest.py` | Separate advanced engine; V2 `backtest_engine.py` retained |
| `research/indicators.py` | `src/nexus_titan/research/indicators.py` | Exact ZIP source |
| `research/strategies.py` | `src/nexus_titan/research/v6_strategies.py` plus exports in `research/strategies.py` | ZIP candidate catalogue kept separate; V2 `MovingAverageCrossover` remains; ZIP API classes are re-exported |
| `research/validation.py` | `src/nexus_titan/research/v6_validation.py` plus exports in `research/validation.py` | ZIP walk-forward/Monte Carlo kept separate; V2 split/OOS evaluator remains; ZIP APIs are re-exported |
| `research/market_signal.py`, `signal_engine.py`, `post_mortem.py` | `src/nexus_titan/research/` | Adapted and covered by Phase 6 tests |
| `risk/` | `src/nexus_titan/risk/` | Integrated with the original V2 permission boundary; no live-order route |
| `self_improvement/` | `src/nexus_titan/self_improvement/` | ACE, Agent Runtime, EVOLVE, research, experiments and human-gated proposals |
| `storage/` | `src/nexus_titan/storage/` | SQLite/JSON ledger support |
| `trading_engine.py` | `src/nexus_titan/trading_engine.py` | CSV-to-decision research flow; not a broker adapter |
| `virtual/` | `src/nexus_titan/virtual/` | Durable local virtual account and order lifecycle |

## Collision policy

- V2 `research/backtest_engine.py` remains intact.
- V2 `research/strategies.py` retains `MovingAverageCrossover` and also re-exports the ZIP candidate classes/registry.
- V2 `research/validation.py` retains `split_chronologically` / `evaluate_out_of_sample` and also re-exports ZIP walk-forward/Monte Carlo APIs.
- ZIP advanced backtesting uses `research/backtest.py`; ZIP catalogue/validation remain separately available as `research/v6_strategies.py` and `research/v6_validation.py`.
- V2 CSV ingestion, OHLCV contract, data quality, sessions, MarketDataService
  and SQLite candle store are preserved.
- No ZIP module is allowed to enable real-money order placement or alter V2
  permission/risk safeguards.

## Verification

- ZIP standalone suite: **246 passed**.
- Original ZIP's tests, unchanged, against the integrated V2 source: **246 passed**.
- V2 branch CI: **280 passed, 5 subtests passed** (run #41256952073).
- Key regression coverage now includes manual approval snapshot integrity, derivative lot-size fills, daily-loss lockout, dashboard capability telemetry and legacy backtest method compatibility.
- This is not a byte-for-byte merge. Exhaustive API parity, independent instrument accounting and production-data validation remain open.
