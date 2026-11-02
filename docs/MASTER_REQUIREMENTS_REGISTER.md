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
| EVOLVE-004 | Isolated artifact workspace | Per-experiment folders; path traversal blocked; artifacts are not executable | Tested | `src/nexus_titan/evolve/sandbox.py`; `tests/test_sandbox.py`; CI #41256952073 (280 passed, 5 subtests) |
| GOV-001 | Requirements register | SQLite-backed lifecycle; transitions require evidence; records survive restart | Tested | `src/nexus_titan/core/requirements.py`; `tests/test_requirements.py`; CI #41256952073 (280 passed, 5 subtests) |
| DATA-001 | OHLCV data contract | Immutable, timezone-normalized candles; valid decimal OHLCV values and query bounds | Tested | `tests/test_ohlcv.py`; CI run #34 |
| DATA-002 | Data quality inspection | Detect duplicates, ordering errors, missing intervals, query-bound and identity errors without mutating input | Tested | `tests/test_data_quality.py`; CI run #34 |
| DATA-003 | Configurable market sessions | Weekly sessions, holidays and special sessions; timezone-aware open/close checks | Tested | `tests/test_sessions.py`; CI run #34; holiday feed remains caller-supplied |
| DATA-004 | Historical data service boundary | Adapter results are type-checked, validated and returned as immutable batches; no broker/order execution | Tested | `tests/test_market_data_service.py`; CI run #34 |
| DATA-005 | CSV historical importer | Strict required headers, timezone-aware ISO timestamps, OHLCV validation and clear malformed-row errors | Tested | `src/nexus_titan/data/csv_import.py`; `tests/test_csv_import.py`; CI #62 success |
| DATA-006 | SQLite candle storage | Decimal-safe local persistence, unique candle key, duplicate accounting and ordered half-open retrieval | Tested | `src/nexus_titan/data/sqlite_store.py`; `tests/test_sqlite_store.py`; CI #62 success |
| DATA-007 | Validated CSV-to-store pipeline | Quality checks complete before any rows are persisted; invalid batch leaves store unchanged | Tested | `tests/test_csv_import.py`; CI #51 success; later adapter changes pending |
| DATA-008 | SQLite MarketDataSource adapter | Stored candles can be retrieved through the standard MarketDataService validation boundary | Tested | `SQLiteMarketDataSource`; `tests/test_sqlite_store.py`; CI #62 success |
| DATA-009 | Historical backtest engine | Next-bar execution, long-only position lifecycle, explicit costs, P&L and risk metrics | Tested | `src/nexus_titan/research/backtest_engine.py`; `tests/test_backtest_engine.py`; CI #62 success |
| STRAT-001 | Moving Average Crossover reference strategy | Fast/slow SMA uses completed candles only; warm-up and parameter validation; next-open integration test | Tested | `src/nexus_titan/research/strategies.py`; `tests/test_moving_average_strategy.py`; combined CI #41256952073 success (280 passed, 5 subtests) |
| VALID-001 | Chronological out-of-sample evaluation | Strict ordered split with separate holdout; warm-up history retained; only holdout candles can generate fills and metrics | Tested | `src/nexus_titan/research/validation.py`; `tests/test_out_of_sample_validation.py`; combined CI #41256952073 success (280 passed, 5 subtests) |
| CI-001 | Continuous integration | Push/PR runs Python tests and reports a successful job | Tested | GitHub Actions run #41256952073 at `634e634ff54c94fd42b2833a24cb1f6a675ad102`, 280 passed and 5 subtests passed |

| ACE-001 | Governed Agent Creation Engine | Declarative specifications; capability/tool allowlist; non-executable prototypes; named human approval before permanent registration | Tested | `self_improvement/agent_creation.py`; `tests/test_phase6_agent_runtime.py`; CI #41256952073 (280 passed, 5 subtests) |
| ARUN-001 | Controlled Agent Runtime | Approved registry only; allowlisted host tools; JSON payload/tool-call bounds; SQLite tasks, idempotency, audit events, dependencies and fail-closed recovery | Tested | `self_improvement/agent_runtime.py`; `tests/test_phase6_agent_runtime.py`; CI #41256952073 (280 passed, 5 subtests) |
| EVOLVE-005 | Governed specialist-agent team | Twelve deterministic/optional-LLM specialists; research evidence, proposal-only code generation and protected-control vetoes | Tested | `self_improvement/agents.py`; `tests/test_phase6_evolve_services.py`; CI #41256952073 (280 passed, 5 subtests) |
| BTEST-001 | Advanced instrument-aware backtest | Costs, slippage, stops/targets, risk sizing, trade metrics and explicit research-only outputs | Tested | `research/backtest.py`; `tests/test_phase6_advanced_backtest.py`; CI #41256952073 (280 passed, 5 subtests); further accounting/market-microstructure verification pending |
| VALID-002 | Rolling walk-forward and Monte Carlo gates | Chronological multi-fold holdout, minimum evidence gate, block bootstrap and explicit promotion blocker | Tested | `research/v6_validation.py`; `tests/test_phase6_validation.py`; CI #41256952073 (280 passed, 5 subtests) |
| DATA-010 | Canonical market-data validation | Timestamp order/duplicates, OHLC bounds, finite positive prices and non-negative volume are checked | Tested | `data/canonical.py`; `tests/test_phase6_canonical_data.py`; CI #41256952073 (280 passed, 5 subtests) |
| DATA-011 | Dataset provenance and promotion evidence gate | Full SHA-256 matches; canonical CSV is valid; session coverage is calendar-audited; missing/duplicate bars are zero; vendor, licence, coverage and point-in-time instrument evidence references have named human review before promotion | Tested | `data/provenance.py`; `data/quality.py`; `tests/test_data_provenance_gates.py`; local Phase 7 validation 2026-11-01; external evidence authenticity remains unverified |
| RISK-001 | Portfolio risk and deterministic veto | Whole-lot sizing, exposure caps, daily/consecutive-loss and drawdown lockouts | Tested | `risk/portfolio_risk.py`, `risk/authoritative_risk.py`; `tests/test_phase6_portfolio_risk.py`; CI #41256952073 (280 passed, 5 subtests) |
| COST-001 | Indicative Indian statutory charge calculator | Brokerage, STT, exchange, SEBI, stamp and GST calculations are configurable and disclose limits | Tested | `cost/charges.py`; CI #41256952073 (280 passed, 5 subtests); official/broker contract-note reconciliation remains outstanding |
| VIRT-001 | Durable virtual account and order lifecycle | Explicit starting capital; approval state; fills, partial fills, idempotency, kill switch, paper exits and SQLite restore | Tested | `virtual/order_manager.py`, `virtual/durable_store.py`; `tests/test_phase6_virtual_order_manager.py`; CI #41256952073 (280 passed, 5 subtests) |
| DERIV-001 | Theoretical options analytics | Black-Scholes theoretical Greeks and bounded IV solver return finite, validated outputs | Tested | `derivatives/options_engine.py`; `tests/test_phase6_options_greeks.py`; options chain/backtest/margin remain not implemented |
| CRYPTO-001 | Isolated crypto virtual account | Explicit capital, quantity-step/min-notional, maker/taker fee and optional VDA TDS, separate from Indian equity account | Tested | `crypto/crypto_engine.py`; `tests/test_phase6_crypto_engine.py`; exchange-specific historical feed remains not implemented |
| UI-001 | Read-only dashboard backend | Telemetry reflects virtual account and reports missing data providers without inventing prices | Tested | `dashboard/api_service.py`; `tests/test_phase6_dashboard.py`; front-end UI remains outstanding |
| CLI-001 | Offline Phase 6 operator CLI | Runtime, backtest, EVOLVE, scheduler and validation runners import; local backtest and EVOLVE workflow work without network | Tested | `scripts/`; `tests/test_phase6_cli.py`; CI #41256952073 (280 passed, 5 subtests) |
| ZIPMAP-001 | ZIP source-path inventory | All 48 ZIP Python module paths have an integrated counterpart; V2 collision policy is documented | Tested | `docs/PHASE6_ZIP_SOURCE_MAP.md`; `docs/PHASE6_ZIP_COMPATIBILITY_TEST_REPORT.md` |
| ZIP-COMP-001 | ZIP-to-V2 compatibility | Original ZIP tests run unchanged against integrated V2 source without import/API failures | Tested | Original ZIP 30 test modules: 246 passed against integrated V2 `src/`; reproducible report in `docs/PHASE6_ZIP_COMPATIBILITY_TEST_REPORT.md` |
| VIRT-002 | Virtual execution safety regressions | Derivative partial fills enforce lot sizes; order mutation after approval invalidates approval; daily loss prevents fresh entries | Tested | `tests/test_phase6_zip_compatibility.py`; CI #41256952073 (280 passed, 5 subtests) |



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

The above Phase 6 statuses reflect GitHub Actions run #41256952073 at commit `634e634ff54c94fd42b2833a24cb1f6a675ad102`: **280 passed, 5 subtests passed**. Separately, the original ZIP test suite passed 246 tests against the integrated V2 source. These results are **Tested**, not **Verified**. External data licensing, market accuracy, exchange-charge reconciliation, full exchange execution, production security and profitability are not proven by unit tests.

## Blueprint v5.0 — Trading Intelligence Foundation (Stage 3)

| ID | Requirement | Acceptance criteria | Status | Evidence / notes |
|---|---|---|---|---|
| MSTATE-001 | Unified Market State Tensor contract | Timestamped identity, price/volume, regime, options/flow, context and provenance blocks; timezone-aware timestamps; stale/missing/invalid evidence marked; no silent imputation | Tested | `src/nexus_titan/intelligence/market_state.py`; `tests/test_market_state_tensor.py`; Stage 3 local validation (339 passed, 5 subtests) |
| CONS-001 | Conservative Signal & Consensus | Accept only complete evidence-backed proposals; invalid state => DATA INVALID; conflicting/HOLD proposals => WAIT; no proposals => NO TRADE; consensus output is candidate only, never an order | Tested | `src/nexus_titan/intelligence/consensus.py`; `tests/test_signal_consensus.py`; confidence explicitly UNCALIBRATED |
| T01-001 | Market Data Intelligence specialist | Live/historical adapter validation, freshness, source provenance and stale/missing-feed alarms | Built (partial) | Existing data service and Stage 3 state contract; live feed/provider evidence remains outstanding |
| T02-001 | Market Regime Intelligence specialist | Regime label, confidence/evidence, transitions and UNKNOWN fallback | Built (partial) | Existing basic regime logic; full time-of-day/opening-range/transition validation outstanding |
| T03-001 | Advanced Options Intelligence specialist | Validated option-chain, OI changes, Greeks, IV/skew, gamma/expiry and strike liquidity | Built (partial) | Existing Greeks/IV and chain quality foundation; OI-change/skew/gamma workflow outstanding |
| T04-001 | Flow & Microstructure specialist | Order-book imbalance, trade-flow estimates, liquidity gaps, spread and fill-quality caveats | Built (partial) | Existing simulated book/spread/slippage; calibrated live depth/trade-flow data outstanding |
| T05-001 | Strategy Research specialist | Reproducible hypotheses, backtests, walk-forward and unseen validation; no self-promotion | Tested (partial) | Existing backtest and validation suites; full evaluation lab/champion-challenger outstanding |
| T06-001 | Signal & Consensus specialist | Evidence-backed proposal, disagreement handling, uncertainty disclosure and NO TRADE | Tested (foundation) | Stage 3 conservative consensus; calibration dataset and production integration outstanding |
| T07-001 | Independent Risk & Veto specialist | Deterministic exposure/loss/order limits; veto cannot be overridden by model consensus | Tested (core) | Existing authoritative risk modules and Phase 7 safety tests; independent external review outstanding |
| T08-001 | Execution & Post-mortem specialist | Simulated order lifecycle, partial/rejected fills, reconciliation and descriptive trade attribution | Tested (partial) | Virtual execution, partial fills and Stage 8 descriptive trade attribution tested; actual broker/quote reconciliation remains outstanding |

### Stage 3 boundary
The new Market State Tensor and Consensus Engine are deterministic foundations, not a complete live decision system. `TRADE CANDIDATE` is not an order or permission to trade. Independent Risk & Veto, instrument/data checks, paper execution and human governance remain mandatory. No live broker execution is enabled.

## Blueprint v5.0 — Stage 4 Analytical Intelligence (offline calculators)

| ID | Requirement | Acceptance criteria | Status | Evidence / notes |
|---|---|---|---|---|
| T01-002 | Strict OHLCV analytical input contract | Aligned finite OHLCV arrays; impossible candles and negative volume rejected | Tested (calculator boundary) | `research/market_intelligence.py`; `tests/test_stage4_market_intelligence.py`; Stage 4 local validation |
| T02-002 | Regime and volatility diagnostics | ADX trend heuristic, ATR percentage and relative realized-volatility expansion/compression; UNKNOWN on insufficient history | Tested (heuristic only) | `adx()`, `realized_volatility()`, `classify_regime()`; thresholds require instrument/timeframe calibration |
| T02-003 | Opening-range analytics | First-N-bars high/low calculated from caller-isolated session | Tested | `opening_range()`; official exchange session/calendar remains caller-supplied |
| T03-002 | Options OI diagnostics | CE/PE OI totals, PCR and matched-contract OI changes from two point-in-time snapshots | Tested (calculator only) | `summarize_open_interest()`; snapshot completeness and provider data remain external |
| T03-003 | IV skew and gamma exposure proxy | Wing IV difference and explicitly signed gamma-exposure proxy validate finite inputs | Tested (proxy only) | `calculate_iv_skew()`, `gamma_exposure()`; exchange-specific dealer gamma convention not verified |
| T04-002 | Order-book depth imbalance | Bid/ask depth imbalance bounded to [-1, 1] and rejects invalid depth | Tested (snapshot only) | `order_book_imbalance()`; no live depth feed or trade-flow classification integrated |
| T04-003 | Session VWAP | Cumulative typical-price VWAP; caller must isolate each session; zero-volume prefix unavailable | Tested | `vwap()`; no auto session reset/calendar lookup |

### Stage 4 boundary
The new components are deterministic, offline research calculators. They do not connect to live market feeds, infer official exchange calendars, calibrate thresholds, generate orders, or validate profitability. IV skew and gamma exposure are simplified diagnostics; the gamma multiplier/sign convention requires instrument/provider-specific calibration. T01–T04 remain partial integrations until adapters, point-in-time data and end-to-end specialist workflows are evidenced.

## Blueprint v5.0 — Stage 5 Specialist Integration Layer

| ID | Requirement | Acceptance criteria | Status | Evidence / notes |
|---|---|---|---|---|
| PIPE-001 | T01-T04 to T05/T06 decision pipeline | Valid market state and complete specialist proposals flow through deterministic consensus; missing/invalid evidence fails closed | Tested (integration boundary) | `src/nexus_titan/intelligence/pipeline.py`; `tests/test_trading_intelligence_pipeline.py`; local Stage 5 suite |
| PIPE-002 | Independent authoritative risk gate | A consensus candidate cannot become a shadow candidate without explicit risk inputs and a passing authoritative risk result; direction mismatch or veto rejects | Tested (integration boundary) | `TradingIntelligencePipeline.evaluate()` delegates to `AuthoritativeRiskEngine`; risk failure returns zero quantity |
| PIPE-003 | Execution isolation | Pipeline has no broker/order-router dependency and every result has `order_submitted=False` | Tested (code boundary) | `PipelineResult.order_submitted` is always false; live and paper order submission remain separate workflows |
| PIPE-004 | Risk-input completeness | Capital, entry, protective stop, symbol, direction and explicit lot size required for the risk gate | Tested (API contract) | `RiskRequest`; external official contract master and exchange margin verification still required |

### Stage 5 boundary
The Stage 5 pipeline integrates the existing state tensor, consensus engine and authoritative risk engine at a deterministic application boundary. It does not automatically derive all eight specialist proposals, connect live data feeds, invoke a broker, submit virtual orders, calibrate confidence, or establish strategy profitability. A `SHADOW CANDIDATE` is only a risk-approved research output, not a filled paper trade or live-trading permission.

## Blueprint v5.0 — Stage 6 Strategy Evaluation & Adversarial Review

| ID | Requirement | Acceptance criteria | Status | Evidence / notes |
|---|---|---|---|---|
| LAB-001 | Champion–Challenger comparison | Compare two strategies only when both have minimum closed-trade evidence, identical dataset fingerprint, OOS evidence and costs included; return explicit blockers | Tested (comparison utility) | `research/strategy_lab.py`; `tests/test_stage6_strategy_lab.py`; no automatic promotion |
| RED-001 | Deterministic adversarial trade review | Check proposal integrity, protective-stop direction, spread/slippage versus expected edge, liquidity coverage and target direction; report severity and veto recommendation | Tested (advisory checks) | `research/adversarial_red_team.py`; `tests/test_stage6_red_team.py`; does not replace authoritative risk engine |
| PM-001 | Existing automated post-mortem | Preserve trade-level exit, fees and estimated slippage summary for backtest reports | Tested | `research/post_mortem.py`; actual execution slippage requires real order/quote data |
| EVOLVE-006 | Governed learning handoff | Strategy comparison and red-team outputs may be recorded as research evidence only; protected risk/permission/live targets remain inaccessible | Built (workflow boundary) | Existing `evolve/research.py` protected-target checks; no automatic code deployment or strategy promotion |

### Stage 6 boundary
Champion–Challenger is a deterministic comparison utility, not a statistical proof or promotion authority. Both strategies must use the same dataset fingerprint and have at least 30 trades by default, OOS evidence and costs included. Red-Team findings are advisory and must not bypass the independent authoritative risk engine. No broker integration or order submission was added.

## Stage 7 additions — Digital Twin & Execution Simulation

| Requirement | State | Evidence / limitation |
|---|---|---|
| Deterministic gap-up/down stress fixtures | Built + Tested | `simulation/digital_twin.py`; OHLC invariants tested; not calibrated |
| Volatility spike / liquidity drought scenarios | Built + Tested | Scenario fixtures; spread multiplier metadata only |
| Bounded partial-fill execution simulator | Built + Tested | `simulation/execution_simulator.py`; simplified deterministic model |
| Latency rejection | Built + Tested | Regression tests; not broker-latency calibrated |
| Limit-price marketability | Built + Tested | Deterministic quote proxy; no order book queue model |
| Exchange-calibrated digital twin | Designed / Pending | Requires licensed tick and order-book data |
| Realistic queue position / market impact | Designed / Pending | Requires venue-specific execution data and calibration |
| Multi-day live-feed shadow validation | Pending external evidence | No live feed or multi-day evidence supplied |

## Blueprint v5.0 — Stage 8: Post-mortem, Attribution & Operations

| ID | Requirement | Acceptance criteria | Status | Evidence / notes |
|---|---|---|---|---|
| PM-002 | Descriptive trade-level post-mortem | Side breakdown, win/loss distribution, best/worst trade, holding duration, exit reason counts, profit concentration and optional regime grouping; small samples explicitly warned; attribution labelled non-causal | Tested | `research/post_mortem.py`; `tests/test_stage8_post_mortem.py`; Stage 8 local suite |
| OPS-001 | Component heartbeat health monitor | Timezone-aware heartbeat, stale/critical thresholds, consecutive failure tracking and unknown state; no automatic restart | Tested | `operations/health.py`; `tests/test_stage8_operations.py` |
| OPS-002 | Conservative watchdog policy | Critical health requires operator recovery; stale health can hold new research tasks; no trading-control mutation, process restart or order submission | Tested | `operations/watchdog.py`; `tests/test_stage8_operations.py` |
| OPS-003 | Research resource budget manager | Validated concurrency, memory and CPU budgets; ALLOW/THROTTLE/REJECT decisions; never terminates processes | Tested | `operations/resource_manager.py`; `tests/test_stage8_operations.py` |
| EVOLVE-007 | Post-mortem learning evidence compatibility | Extended post-mortem remains compatible with governed EVOLVE learning capture; insights remain research records, not automatic code/risk changes | Tested (handoff compatibility) | `self_improvement/engine.py::capture_post_mortem`; `tests/test_stage8_post_mortem.py`; no code/risk/permission changes or auto-promotion |

## Stage 9 — Shadow validation evidence framework (2026-11-01)

| Requirement | Implementation | Verification | Limitation / status |
|---|---|---|---|
| Append-only shadow evidence log | `src/nexus_titan/shadow/validation.py` JSONL hash chain | tamper detection, reopen, monotonic timestamp tests | Local file evidence only; not remote/WORM storage |
| Session reconciliation | opening balance + realized P&L - fees vs observed close; event-count check | balanced and mismatch fixtures | Requires trusted caller-supplied snapshots |
| Shadow readiness gate | sessions, reconciliations, closed trades, licensed provenance, execution calibration | fail-closed and ready fixture tests | Eligibility for human review only; no promotion |
| Broker/live isolation | module has no broker adapter or order-submission path | static inspection and tests | Live trading remains disabled |

## Stage 10 — Integration & Release Audit hardening (2026-11-01)

| Requirement | Implementation | Verification | Limitation / status |
|---|---|---|---|
| REL-001 | `scripts/run_project_validation.py` injects the repository `src/` path into the pytest subprocess environment | Bare `python scripts/run_project_validation.py` from extracted ZIP passes without manual `PYTHONPATH` | Python/pytest environment still needs dependencies installed; fallback runner applies only when pytest is absent |
| REL-002 | `scripts/run_advanced_backtest_suite.py` injects the repository `src/` path into its pytest subprocess | Advanced suite records 378/378 passed and G0 `PASSED_CODE_VERIFIED` | Other six gates remain external-evidence requirements; no production approval |
| REL-003 | README and release report identify Stage 9 as latest shadow framework and Stage 10 as packaging/validation hardening | Package review and ZIP integrity verification | No new live feed, broker, exchange calibration or live-order capability added |

### Stage 10 boundary
Stage 10 is a release-tooling and integration audit correction, not a new strategy or market-data capability. The initial clean-archive run exposed that the advanced backtest runner launched pytest without propagating the `src/` import path; G0 was therefore incorrectly recorded as failed despite the suite passing when `PYTHONPATH=src` was supplied. Both repository validation and advanced backtest runners now provide that path explicitly. After the correction, the full suite reports 378 passed and 5 subtests passed, and G0 passes. G1, G2, G6, G7, G8 and G9 still require independent external evidence or owner sign-off. The bundled 120-bar NIFTY data remains synthetic and promotion-ineligible.

## Stage 11 — Professional Release Engineering (2026-11-01)
| ID | Requirement | Status | Evidence | Boundary |
|---|---|---|---|---|
| REL-004 | Python 3.11/3.12/3.13 CI matrix | BUILT | `.github/workflows/ci.yml` | CI must run on hosted GitHub Actions to establish remote evidence. |
| REL-005 | Security trust-boundary and deployment baseline | BUILT | `SECURITY.md` | Not a penetration test or certification. |
| REL-006 | Offline operator runbook | BUILT | `docs/OPERATIONS_RUNBOOK.md` | Specific Replit deployment still requires user-workspace verification. |
| REL-007 | Evidence-aware release preflight | TESTED | `scripts/release_preflight.py`, `reports/release_preflight_stage11.json` | Returns BLOCKED_EXTERNAL_EVIDENCE until external approvals are supplied. |
| REL-008 | Static secret-pattern scan | TESTED | 0 findings in Stage 11 source/scripts | Pattern scan only; cannot prove absence of all secrets. |
| REL-009 | Stage 11 test coverage | TESTED | 381/381 tests passed | Unit/regression tests do not establish live-market performance. |

## Stage 12 — Master Integration A-to-Z

| ID | Requirement | Status | Implementation / evidence | Boundary |
|---|---|---|---|---|
| MASTER-001 | Master research/shadow orchestration | BUILT + TESTED | `core/master_integration.py::MasterTradingOrchestrator`; `tests/test_master_integration.py` | Coordinates existing components; does not create live orders |
| MASTER-002 | Market state → consensus → authoritative risk | INTEGRATED | Existing `intelligence/pipeline.py` composed in master cycle | Market state and specialist proposals must be supplied with provenance |
| MASTER-003 | Independent Red-Team pre-execution gate | INTEGRATED | `research/adversarial_red_team.py::challenge_trade` called before simulator | Deterministic advisory checks; no empirical adversarial model |
| MASTER-004 | Digital Twin stress preview | INTEGRATED | `MasterTradingOrchestrator.stress_preview`; `simulation/digital_twin.py` | Deterministic OHLCV stress only; not exchange-calibrated |
| MASTER-005 | Bounded execution simulation | INTEGRATED | `simulation/execution_simulator.py::simulate_execution` | No queue reconstruction or broker adapter |
| MASTER-006 | Core lifecycle events, audit and health | INTEGRATED | `CoreRuntime`, `EventBus`, `AuditLedger`, `HealthMonitor` | Local in-process events and local audit storage; not distributed operations |
| MASTER-007 | Lazy master capability registration | BUILT + TESTED | `register_master_capabilities(core)` | In-process registry only; not a plugin sandbox |
| MASTER-008 | Explicit manual virtual-order staging | BUILT + TESTED | Optional `MANUAL_APPROVAL` account staging path | Core paper permission must be explicitly enabled; order remains pending; never approved/filled by orchestrator |
| MASTER-009 | Cross-module safety invariants | TESTED | Regression tests for risk quantity, side/entry alignment, red-team, permission and live-disabled flags | External penetration test and broker isolation review still open |
| MASTER-010 | Blueprint and implementation traceability | DOCUMENTED | `docs/MASTER_INTEGRATION_ARCHITECTURE.md` | 45 logical roles and ~30 analytics remain design estimates; current scope is trading-first |

### Stage 12 boundary

Stage 12 closes an orchestration gap; it does not complete the full trading system. Data ingestion still requires an approved feed and licensed point-in-time dataset. Market-regime, options-flow and microstructure metrics remain heuristic or offline until calibrated. Strategy candidates are not promoted. EVOLVE remains supervised and cannot alter risk or permission controls. The master cycle can optionally stage a virtual order only after an explicit permission check and only in a `MANUAL_APPROVAL` account; it never approves or fills it. Live trading remains disabled.

## Stage 13 — Specialist Evidence & EVOLVE Governance

| ID | Requirement | Status | Implementation / evidence | Boundary |
|---|---|---|---|---|
| SPEC-001 | Eight named specialist evidence lanes | BUILT + TESTED | `intelligence/specialist_roles.py::SPECIALIST_ROLES` | Role contracts only; not eight autonomous agents |
| SPEC-002 | Evidence-backed proposal adapter | BUILT + TESTED | `adapt_specialist_evidence()` | Requires caller-supplied reason, evidence reference and invalidation; never invents signals |
| SPEC-003 | Independent confirmation | BUILT + TESTED | Single directional opinion is paired with explicit HOLD | Consensus still decides WAIT; no automatic signal promotion |
| SPEC-004 | Duplicate/unknown role rejection | BUILT + TESTED | Stage 13 regression tests | External identity of evidence sources is not authenticated here |
| EVG-001 | Governed EVOLVE research service | BUILT + TESTED | `evolve/governance.py::GovernedEvolveService` | Research lifecycle only; no generated-code execution |
| EVG-002 | Human approval and audit trace | BUILT + TESTED | Proposal/approval/start/completion events in hash-chained audit ledger | Local audit storage; production key/identity controls remain external |
| EVG-003 | Protected controls remain outside EVOLVE | TESTED | Snapshot invariants for risk, permissions and live trading | No control mutation interface exposed |
| INT-013 | Evidence-to-master orchestration entrypoint | BUILT + TESTED | `MasterTradingOrchestrator.run_cycle_from_evidence()` | Caller supplies all evidence; risk and red-team remain authoritative gates |

### Stage 13 limitations

The eight specialist lanes are typed evidence adapters, not autonomous LLM agents. The Stage 13 work does not claim a completed 12-agent EVOLVE runtime, live market intelligence, calibrated probabilities, strategy promotion, or production-grade shadow trading. Champion–Challenger comparison remains evidence-gated and promotion-authority-free. All external data, security, recovery, and multi-day shadow gates remain open.

## Stage 14 evidence hardening (2026-11-01)

| Requirement | State | Acceptance / boundary |
|---|---|---|
| STRAT-LAB-14: Champion–Challenger eligibility | BUILT / TESTED | Both candidates require verified dataset-manifest evidence, matching SHA-256 dataset fingerprints, out-of-sample results, included costs, minimum trade sample, finite metrics and internally consistent trade counts. Comparison never authorizes promotion. |
| SPEC-14: Independent specialist evidence | BUILT / TESTED | Two directional specialist roles cannot count the same evidence reference as independent confirmation. Missing roles remain missing; no synthetic votes are generated. |
| EVOLVE-SBX-14: isolated research workspace | EXISTING / TESTED | Existing artifact-only workspace remains non-executing, offline and non-trading. This stage does not add arbitrary code execution. |
| SHADOW-LIFECYCLE-14: virtual order lifecycle | EXISTING / TESTED | Existing virtual account lifecycle remains the only supported order lifecycle. No broker route or live order is introduced. |
