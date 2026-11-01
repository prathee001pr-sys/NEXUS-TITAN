# Phase 6 ZIP source map

Reference archive: `NEXUS_TITAN_V6_Phase6_Agent_Runtime_And_Backtest.zip`

The V2 integration branch is additive. Original V2 files are retained where names
or interfaces overlap. This document records the source mapping and collision
policy rather than claiming a blind archive extraction.

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
| `research/strategies.py` | `src/nexus_titan/research/v6_strategies.py` | ZIP candidate catalogue kept separate; V2 `strategies.py` preserved |
| `research/validation.py` | `src/nexus_titan/research/v6_validation.py` | ZIP walk-forward/Monte Carlo kept separate; V2 `validation.py` preserved |
| `research/market_signal.py`, `signal_engine.py`, `post_mortem.py` | `src/nexus_titan/research/` | Adapted and covered by Phase 6 tests |
| `risk/` | `src/nexus_titan/risk/` | Integrated with the original V2 permission boundary; no live-order route |
| `self_improvement/` | `src/nexus_titan/self_improvement/` | ACE, Agent Runtime, EVOLVE, research, experiments and human-gated proposals |
| `storage/` | `src/nexus_titan/storage/` | SQLite/JSON ledger support |
| `trading_engine.py` | `src/nexus_titan/trading_engine.py` | CSV-to-decision research flow; not a broker adapter |
| `virtual/` | `src/nexus_titan/virtual/` | Durable local virtual account and order lifecycle |

## Collision policy

- V2 `research/backtest_engine.py`, `research/strategies.py` and
  `research/validation.py` are preserved.
- ZIP advanced backtesting uses `research/backtest.py`.
- ZIP strategy catalogue and walk-forward validation are available as
  `research/v6_strategies.py` and `research/v6_validation.py`.
- V2 CSV ingestion, OHLCV contract, data quality, sessions, MarketDataService
  and SQLite candle store are preserved.
- No ZIP module is allowed to enable real-money order placement or alter V2
  permission/risk safeguards.

## Verification

- The archive's standalone test suite was run separately: **246 passed**.
- The V2 integration branch's combined GitHub Actions suite passed: **272 passed**
  at commit `9724c3cb6e3530fb8ca5dfba0f3df1a90dc9cb6f`.
- Phase 6 CLI runners and their smoke tests were added after that run; check the
  latest branch CI before considering those runners verified.
- This is not a byte-for-byte merge of every ZIP file. Source/API parity and
  instrument-accounting validation remain a deliberate final acceptance gate.
