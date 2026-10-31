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
| EVOLVE-004 | Isolated artifact workspace | Per-experiment folders; path traversal blocked; artifacts are not executable | Designed | Implementation introduced in this change; awaiting CI |
| GOV-001 | Requirements register | SQLite-backed lifecycle; transitions require evidence; records survive restart | Designed | Implementation introduced in this change; awaiting CI |
| DATA-001 | OHLCV data contract | Immutable, timezone-normalized candles; valid decimal OHLCV values and query bounds | Tested | `tests/test_ohlcv.py`; CI run #34 |
| DATA-002 | Data quality inspection | Detect duplicates, ordering errors, missing intervals, query-bound and identity errors without mutating input | Tested | `tests/test_data_quality.py`; CI run #34 |
| DATA-003 | Configurable market sessions | Weekly sessions, holidays and special sessions; timezone-aware open/close checks | Tested | `tests/test_sessions.py`; CI run #34; holiday feed remains caller-supplied |
| DATA-004 | Historical data service boundary | Adapter results are type-checked, validated and returned as immutable batches; no broker/order execution | Tested | `tests/test_market_data_service.py`; CI run #34 |
| DATA-005 | CSV historical importer | Strict required headers, timezone-aware ISO timestamps, OHLCV validation and clear malformed-row errors | Built | `src/nexus_titan/data/csv_import.py`; CI pending |
| DATA-006 | SQLite candle storage | Decimal-safe local persistence, unique candle key, duplicate accounting and ordered half-open retrieval | Built | `src/nexus_titan/data/sqlite_store.py`; CI pending |
| DATA-007 | Validated CSV-to-store pipeline | Quality checks complete before any rows are persisted; invalid batch leaves store unchanged | Tested | `tests/test_csv_import.py`; CI #51 success; later adapter changes pending |
| DATA-008 | SQLite MarketDataSource adapter | Stored candles can be retrieved through the standard MarketDataService validation boundary | Built | `SQLiteMarketDataSource`; `tests/test_sqlite_store.py`; CI pending |
| DATA-009 | Historical backtest engine | Next-bar execution, long-only position lifecycle, explicit costs, P&L and risk metrics | Built | `src/nexus_titan/research/backtest_engine.py`; `tests/test_backtest_engine.py`; CI pending |
| STRAT-001 | Moving Average Crossover reference strategy | Fast/slow SMA uses completed candles only; warm-up and parameter validation; next-open integration test | Built | `src/nexus_titan/research/strategies.py`; `tests/test_moving_average_strategy.py`; CI verification pending |
| CI-001 | Continuous integration | Push to main runs Python tests and reports a successful job | Verified | GitHub Actions run #55, commit `0b4a27c`, job `Core tests`, conclusion `success` |

## Evidence policy

The CI run confirms that the repository test job completed successfully; it does not
independently validate exchange data accuracy, official market calendars, provider
licensing, production reliability or trading profitability. Data requirements remain
**Tested**, not **Verified**, until those external and end-to-end acceptance checks
have evidence.

CI run #62 passed for commit `3b4abda2fdd3e7a4a62dca8b66a1a407407aff94`.
The moving-average strategy and its tests were committed after that run; their
automated CI result must be checked before their status advances beyond **Built**.

## Scope and safety notes

- "Tested" means automated tests passed; it does not mean production approval.
- "Verified" is reserved for evidence that validates the full requirement, not just that code exists.
- The experiment workspace is **artifact storage only**. It does not run user code, scripts,
  notebooks, strategies, plugins or shell commands. It has no network or broker connection.
- SQLite files are local plaintext databases in this phase. Do not store passwords, API keys,
  broker tokens, or other secrets in them. OS-level access controls, encryption and backup
  procedures remain future work.
- Real-money trading is out of scope. No live broker execution is implemented.
