# NEXUS TITAN V2

NEXUS TITAN is a modular, trading-first AI research and virtual-trading system.
The V2 repository preserves its original Core, data, security and baseline
backtest modules while integrating selected capabilities from the V6 Phase 6 ZIP and Phase 7 advanced research modules.

## Current branch status

The Phase 6/7 code snapshot is a research and virtual-trading development branch.
Do not treat this ZIP as a production release. Phase 7 safety-hardening changes and
local regression evidence are recorded in the Phase 7 reports. The latest locally validated integrated package is Stage 12; it remains a research/shadow development branch, not a production release. Stage 12 adds a governed master orchestration boundary over the existing modules.

See:
- [Phase 7 Stage 8 Post-mortem & Operations Report](docs/PHASE7_STAGE8_POSTMORTEM_OPERATIONS_REPORT_2026-11-01.md)
- [Phase 7 Stage 7 Digital Twin & Execution Report](docs/PHASE7_STAGE7_DIGITAL_TWIN_EXECUTION_REPORT_2026-11-01.md)
- [Phase 7 Stage 6 Strategy Evaluation & Red-Team Report](docs/PHASE7_STAGE6_STRATEGY_EVALUATION_REDTEAM_REPORT_2026-11-01.md)
- [Phase 7 Stage 5 Specialist Integration Report](docs/PHASE7_STAGE5_SPECIALIST_INTEGRATION_REPORT_2026-11-01.md)
- [Phase 6 integration status](docs/PHASE6_INTEGRATION_STATUS.md)
- [ZIP compatibility test report](docs/PHASE6_ZIP_COMPATIBILITY_TEST_REPORT.md)
- [ZIP source map and collision policy](docs/PHASE6_ZIP_SOURCE_MAP.md)
- [Master requirements register](docs/MASTER_REQUIREMENTS_REGISTER.md)
- [Original V2 data/backtest design notes](docs/HISTORICAL_BACKTEST_ENGINE.md)

## Main capabilities in the integration branch

- Core runtime, events, four-layer memory, permission boundary and audit trail.
- CSV/SQLite historical candle store and data-quality/session validation.
- Original V2 long-only backtest and Moving Average Crossover baseline.
- Phase 6/7 advanced backtest, technical indicators, eight strategy candidates,
  rolling walk-forward validation, Monte Carlo stress analysis and multiple-testing checks.
- Phase 7 dataset provenance, point-in-time instrument master, options chain validation,
  indicative margin/settlement analytics, microstructure and persistent shadow-account support.
- ACE declarative agent registry and SQLite-backed Agent Runtime.
- TITAN EVOLVE learning store, 12 supervised specialists, research ingestion,
  optional LLM synthesis, scheduled research and review-only code proposals.
- Indicative Indian transaction-cost model, portfolio risk sizing and deterministic veto.
- Theoretical options Greeks, isolated crypto virtual account and durable paper-order lifecycle.
- Read-only dashboard API and offline command-line runners.
- Blueprint v5.0 Stage 3 Market State Tensor and conservative Signal Consensus.
- Stage 4 offline T01-T04 analytics: regime/volatility, opening range, OI/PCR, IV-skew/gamma proxies, VWAP and order-book imbalance.
- Stage 5 deterministic specialist-to-risk integration pipeline; research candidates require explicit authoritative risk approval and never submit orders.
- Stage 6 Champion-Challenger comparison and deterministic adversarial trade checks; promotion remains human-gated.
- Stage 7 deterministic market stress fixtures and bounded execution simulation.
- Stage 8 descriptive trade attribution, optional regime buckets, component health monitor, advisory watchdog and bounded research resource manager.
- Stage 9 append-only shadow evidence ledger, hash-chain verification, session cash reconciliation and fail-closed multi-session readiness gate.

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
- Approval replay protection uses a durable SQLite store; signing keys must be held
  outside the database in an environment secret/secret manager.
- Naive CSV timestamps default to Asia/Kolkata; pass `--source-timezone` for other markets. Ambiguous/nonexistent DST wall times are rejected unless an explicit UTC offset is supplied.
- Backtest strategy callbacks receive only a read-only prefix through the current candle, preventing ordinary look-ahead access via the callback argument.
- Short-option backtests are intentionally blocked until a verified portfolio SPAN/ELM
  margin model is integrated.
- Watchdog and resource manager are advisory libraries, not a deployed OS process supervisor; they do not kill processes or automatically restart services.
- Post-mortem regime grouping requires caller-supplied regime labels; calculated attribution is descriptive, not causal.
- Passing unit tests does not prove profitability, data provenance or production readiness.

The sample files `data/market_sample.csv` and `data/nifty_daily_sample.csv` are synthetic smoke-test fixtures, not real NSE history. Do not use them for trading conclusions.

The integration PR remains draft until source/API parity, risk/accounting edge cases,
security, data licensing and end-to-end acceptance checks are reviewed.

## Phase 7 validation

Install the project before running tests:

```bash
python -m pip install -e ".[dev]"
pytest -o addopts=
python scripts/run_advanced_backtest_suite.py --json-out reports/phase7_advanced_backtest_report.json
```

The advanced suite runs pytest and records the actual test summary in the G0 gate.
Other gates remain unverified until their explicit independent evidence inputs are supplied.
The sample data is synthetic and cannot qualify a strategy for promotion.

## Stage 10 — Integration & Release Audit

Stage 10 improves the offline validation runner so it reliably exposes the `src/` package to pytest even when the project has not been installed editable. It also refreshes the release-readiness report and master register. This is packaging/validation hardening, not evidence of live-market readiness.

## Stage 3 — Market Intelligence Foundation

The Stage 3 additive update introduces an immutable, quality-marked Market State contract and a conservative Signal & Consensus engine. Missing or stale evidence is never silently converted into a directional signal. Consensus can produce only a `TRADE CANDIDATE`; independent Risk & Veto and paper-execution controls remain mandatory. See `docs/PHASE7_STAGE3_MARKET_INTELLIGENCE_REPORT_2026-11-01.md` and `docs/MASTER_REQUIREMENTS_REGISTER.md` for scope and evidence. The bundled market sample remains synthetic and cannot promote strategies.

## Stage 11 professionalization
- Security and trust-boundary baseline: `SECURITY.md`
- Offline operator runbook: `docs/OPERATIONS_RUNBOOK.md`
- Evidence-aware release preflight: `python scripts/release_preflight.py --json-out reports/release_preflight_stage11.json`
- Python 3.11/3.12/3.13 CI workflow: `.github/workflows/ci.yml`
- Stage 11 audit: `docs/PHASE7_STAGE11_PROFESSIONALIZATION_REPORT_2026-11-01.md`

The preflight intentionally reports `BLOCKED_EXTERNAL_EVIDENCE` until independent security, licensed data, recovery, multi-day shadow and owner sign-off evidence exist. This is not a production-ready/live-trading release.


## Stage 12 — Master Integration A-to-Z

The new `nexus_titan.core.master_integration.MasterTradingOrchestrator` composes the existing state/consensus/risk pipeline, adversarial Red-Team, deterministic Digital Twin preview, bounded execution simulator, CoreRuntime events/audit and component health. `register_master_capabilities(core)` registers lazy capability factories.

Run the Stage 12 integration tests with:

```bash
pytest tests/test_master_integration.py tests/test_phase6_dashboard.py
```

Optional virtual-order staging is disabled by default. It requires `Settings(paper_trading_enabled=True)`, an injected `VirtualAccount` in `MANUAL_APPROVAL` mode, and a clean kill-switch state. The order remains `PENDING_APPROVAL`; the orchestrator never approves or fills it. No live route exists. See `docs/MASTER_INTEGRATION_ARCHITECTURE.md` and `docs/PHASE7_STAGE12_MASTER_INTEGRATION_REPORT_2026-11-01.md`.

## Stage 13 — Specialist Evidence & EVOLVE Governance

Stage 13 adds eight typed specialist evidence lanes and an evidence adapter that connects caller-supplied role evidence to the Stage 12 master orchestrator. Missing or duplicate role evidence is never silently filled in; a single directional opinion requires independent confirmation. These are role contracts, not eight autonomous agents.

`GovernedEvolveService` adds audit-traced research notes and experiment lifecycle management. A human approver is required before an experiment can start. Code execution, strategy promotion, and live trading remain disabled through this service.

Run targeted checks with:

```bash
PYTHONPATH=src python -m pytest -q tests/test_stage13_specialist_governance.py
python scripts/run_project_validation.py
python scripts/run_advanced_backtest_suite.py --json-out reports/phase7_advanced_backtest_report_stage13.json
python scripts/release_preflight.py --json-out reports/release_preflight_stage13.json
```

Stage 13 remains a research/shadow development package. Its bundled market sample is synthetic; strategy promotion and production release remain blocked pending external evidence.

### Stage 14 — evidence hardening

Stage 14 adds stricter Champion–Challenger eligibility (verified-manifest assertion, valid/matching dataset SHA-256, out-of-sample evidence, costs, sample-size and metric consistency) and prevents directional specialist roles from double-counting the same evidence reference. Strategy promotion remains disabled. See `docs/PHASE7_STAGE14_EVIDENCE_HARDENING_REPORT_2026-11-01.md` and `reports/release_preflight_stage14.json`.

## Stage 15 — Evidence provenance

Stage 15 adds canonical SHA-256 evidence envelopes and freshness checks for specialist evidence before the master orchestration path. A digest verifies payload integrity, not source authenticity or licensing. See `docs/PHASE7_STAGE15_EVIDENCE_PROVENANCE_REPORT_2026-11-01.md` for scope, limitations, and verification.

## Stage 1–15 canonical integration candidate (2026-11-02)

The cumulative Stage 1–15 source has been reconciled in a clean candidate workspace. The final combined regression suite reports **412 passed, 5 subtests passed**. See `docs/PHASE7_STAGE1_15_CANONICAL_INTEGRATION_AUDIT_2026-11-02.md` and the machine-readable backtest/preflight reports in `reports/`.

This candidate remains research/shadow-only. External market-data licensing, independent security, recovery, multi-day shadow and owner-signoff gates remain open. This locally packaged candidate is not the same as the current GitHub Phase 6 integration branch; the existing PR remains draft and `main` has not been changed.
