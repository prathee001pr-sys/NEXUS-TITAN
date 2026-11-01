# NEXUS TITAN V2 — Master Requirements Register

This register is the initial baseline for tracking requirements through:
**Designed → Built → Tested → Verified**.

A status is advanced only when the acceptance criteria for that state are met.
Transitions to Tested and Verified must include a concrete evidence reference.
The SQLite-backed implementation lives in
`src/nexus_titan/core/requirements.py`.

| ID | Requirement | Acceptance criteria | Initial status | Evidence / notes |
|---|---|---|---|---|
| CORE-001 | Safe configuration | Validated environment and logging settings; paper trading defaults off | Tested | CI run #6 |
| CORE-002 | Permission guard | Live trading and risk/permission changes require human approval | Tested | CI run #6 |
| CORE-003 | Event system | Subscribe, publish, unsubscribe and handler errors are tested | Tested | CI run #6 |
| CORE-004 | Four-layer memory | Working, episodic, knowledge and procedural layers; confidence/source/time validation | Tested | CI run #6 |
| CORE-005 | Durable memory | SQLite records survive close/reopen and support retrieval by layer | Tested | CI run #6 |
| CORE-006 | Lazy module registry | Modules register once and load only when requested | Tested | CI run #6 |
| CORE-007 | Audit ledger | Hash chain verifies and tampering through returned copies is prevented | Tested | CI run #6; persistence test included |
| EVOLVE-001 | Research notes | Research records retain title, hypothesis and source | Tested | CI run #6 |
| EVOLVE-002 | Human-gated experiments | Proposed experiments require an identified human approver before start | Tested | CI run #6 |
| EVOLVE-003 | Protected controls | EVOLVE cannot target risk controls, permissions or live trading | Tested | CI run #6 |
| EVOLVE-004 | Isolated artifact workspace | Per-experiment folders; path traversal blocked; artifacts are not executable | Tested | `src/nexus_titan/evolve/sandbox.py`; `tests/test_sandbox.py`; CI #41255869182 (275 passed, 5 subtests) |
| GOV-001 | Requirements register | SQLite-backed lifecycle; transitions require evidence; records survive restart | Tested | `src/nexus_titan/core/requirements.py`; `tests/test_requirements.py`; CI #41255869182 (275 passed, 5 subtests) |
| DATA-001 | OHLCV data contract | Immutable, timezone-normalized candles; valid decimal OHLCV values and query bounds | Tested | `tests/test_ohlcv.py`; CI run #34 |
| DATA-002 | Data quality inspection | Detect duplicates, ordering errors, missing intervals, query-bound and identity errors without mutating input | Tested | `tests/test_data_quality.py`; CI run #34 |
| DATA-003 | Configurable market sessions | Weekly sessions, holidays and special sessions; timezone-aware open/close checks | Tested | `tests/test_sessions.py`; CI run #34; holiday feed remains caller-supplied |
| DATA-004 | Historical data service boundary | Adapter results are type-checked, validated and returned as immutable batches; no broker/order execution | Tested | `tests/test_market_data_service.py`; CI run #34 |
| DATA-005 | CSV historical importer | Strict required headers, timezone-aware ISO timestamps, OHLCV validation and clear malformed-row errors | Tested | `src/nexus_titan/data/csv_import.py`; `tests/test_csv_import.py`; CI #62 success |
| DATA-006 | SQLite candle storage | Decimal-safe local persistence, unique candle key, duplicate accounting and ordered half-open retrieval | Tested | `src/nexus_titan/data/sqlite_store.py`; `tests/test_sqlite_store.py`; CI #62 success |
| DATA-007 | Validated CSV-to-store pipeline | Quality checks complete before any rows are persisted; invalid batch leaves store unchanged | Tested | `tests/test_csv_import.py`; CI #51 success; later adapter changes pending |
| DATA-008 | SQLite MarketDataSource adapter | Stored candles can be retrieved through the standard MarketDataService validation boundary | Tested | `SQLiteMarketDataSource`; `tests/test_sqlite_store.py`; CI #62 success |
| DATA-009 | Historical backtest engine | Next-bar execution, long-only position lifecycle, explicit costs, P&L and risk metrics | Tested | `src/nexus_titan/research/backtest_engine.py`; `tests/test_backtest_engine.py`; CI #62 success |
| STRAT-001 | Moving Average Crossover reference strategy | Fast/slow SMA uses completed candles only; warm-up and parameter validation; next-open integration test | Tested | `src/nexus_titan/research/strategies.py`; `tests/test_moving_average_strategy.py`; combined CI #41255869182 success (275 passed, 5 subtests) |
| VALID-001 | Chronological out-of-sample evaluation | Strict ordered split with separate holdout; warm-up history retained; only holdout candles can generate fills and metrics | Tested | `src/nexus_titan/research/validation.py`; `tests/test_out_of_sample_validation.py`; combined CI #41255869182 success (275 passed, 5 subtests) |
| CI-001 | Continuous integration | Push/PR runs Python tests and reports a successful job | Tested | GitHub Actions run #41255869182 at `8ed6c200676ae2a58f3448a10b69164b37ba27b3`, 275 passed and 5 subtests passed |

| ACE-001 | Governed Agent Creation Engine | Declarative specifications; capability/tool allowlist; non-executable prototypes; named human approval before permanent registration | Tested | `self_improvement/agent_creation.py`; `tests/test_phase6_agent_runtime.py`; CI #41255869182 (275 passed, 5 subtests) |
| ARUN-001 | Controlled Agent Runtime | Approved registry only; allowlisted host tools; JSON payload/tool-call bounds; SQLite tasks, idempotency, audit events, dependencies and fail-closed recovery | Tested | `self_improvement/agent_runtime.py`; `tests/test_phase6_agent_runtime.py`; CI #41255869182 (275 passed, 5 subtests) |
| EVOLVE-005 | Governed specialist-agent team | Twelve deterministic/optional-LLM specialists; research evidence, proposal-only code generation and protected-control vetoes | Tested | `self_improvement/agents.py`; `tests/test_phase6_evolve_services.py`; CI #41255869182 (275 passed, 5 subtests) |
| BTEST-001 | Advanced instrument-aware backtest | Costs, slippage, stops/targets, risk sizing, trade metrics and explicit research-only outputs | Tested | `research/backtest.py`; `tests/test_phase6_advanced_backtest.py`; CI #41255869182 (275 passed, 5 subtests); further accounting/market-microstructure verification pending |
| VALID-002 | Rolling walk-forward and Monte Carlo gates | Chronological multi-fold holdout, minimum evidence gate, block bootstrap and explicit promotion blocker | Tested | `research/v6_validation.py`; `tests/test_phase6_validation.py`; CI #41255869182 (275 passed, 5 subtests) |
| DATA-010 | Canonical market-data validation | Timestamp order/duplicates, OHLC bounds, finite positive prices and non-negative volume are checked | Tested | `data/canonical.py`; `tests/test_phase6_canonical_data.py`; CI #41255869182 (275 passed, 5 subtests) |
| RISK-001 | Portfolio risk and deterministic veto | Whole-lot sizing, exposure caps, daily/consecutive-loss and drawdown lockouts | Tested | `risk/portfolio_risk.py`, `risk/authoritative_risk.py`; `tests/test_phase6_portfolio_risk.py`; CI #41255869182 (275 passed, 5 subtests) |
| COST-001 | Indicative Indian statutory charge calculator | Brokerage, STT, exchange, SEBI, stamp and GST calculations are configurable and disclose limits | Tested | `cost/charges.py`; CI #41255869182 (275 passed, 5 subtests); official/broker contract-note reconciliation remains outstanding |
| VIRT-001 | Durable virtual account and order lifecycle | Explicit starting capital; approval state; fills, partial fills, idempotency, kill switch, paper exits and SQLite restore | Tested | `virtual/order_manager.py`, `virtual/durable_store.py`; `tests/test_phase6_virtual_order_manager.py`; CI #41255869182 (275 passed, 5 subtests) |
| DERIV-001 | Theoretical options analytics | Black-Scholes theoretical Greeks and bounded IV solver return finite, validated outputs | Tested | `derivatives/options_engine.py`; `tests/test_phase6_options_greeks.py`; options chain/backtest/margin remain not implemented |
| CRYPTO-001 | Isolated crypto virtual account | Explicit capital, quantity-step/min-notional, maker/taker fee and optional VDA TDS, separate from Indian equity account | Tested | `crypto/crypto_engine.py`; `tests/test_phase6_crypto_engine.py`; exchange-specific historical feed remains not implemented |
| UI-001 | Read-only dashboard backend | Telemetry reflects virtual account and reports missing data providers without inventing prices | Tested | `dashboard/api_service.py`; `tests/test_phase6_dashboard.py`; front-end UI remains outstanding |


## Evidence policy

The CI run confirms that the repository test job completed successfully; it does not
independently validate exchange data accuracy, official market calendars, provider
licensing, production reliability or trading profitability. Data requirements remain
**Tested**, not **Verified**, until those external and end-to-end acceptance checks
have evidence.

CI run #62 passed for commit `3b4abda2fdd3e7a4a62dca8b66a1a407407aff94`.
The Moving Average Crossover strategy and chronological out-of-sample evaluation
were committed after that run; their automated CI result must be checked before
their status advances beyond **Built**.

## Scope and safety notes

- "Tested" means automated tests passed; it does not mean production approval.
- "Verified" is reserved for evidence that validates the full requirement, not just that code exists.
- The experiment workspace is **artifact storage only**. It does not run user code, scripts,
  notebooks, strategies, plugins or shell commands. It has no network or broker connection.
- SQLite files are local plaintext databases in this phase. Do not store passwords, API keys,
  broker tokens, or other secrets in them. OS-level access controls, encryption and backup
  procedures remain future work.
- Real-money trading is out of scope. No live broker execution is implemented.


## Phase 6 integration note

The above Phase 6 statuses reflect GitHub Actions run #41255869182 at commit `8ed6c200676ae2a58f3448a10b69164b37ba27b3`: **275 passed, 5 subtests passed**. They are **Tested**, not **Verified**. External data licensing, market accuracy, exchange-charge reconciliation, full exchange execution, production security and profitability are not proven by unit tests.
