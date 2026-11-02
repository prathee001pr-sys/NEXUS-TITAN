# NEXUS TITAN Phase 7 — Stage 8 Report

Date: 2026-11-01  
Input: Stage 7 Digital Twin & Execution package  
Scope: richer trade post-mortem, descriptive P&L attribution, component health monitoring, advisory watchdog policy and research resource budgeting.  
Mode: offline / historical / research / shadow only. No broker integration or live order route.

## Baseline and changes

- Extracted Stage 7 into a separate working directory; original Stage 7 archive was not modified.
- Stage 7 baseline test suite: 363 passed, 5 subtests passed.
- Added 9 Stage 8 regression tests. Final local suite: 372 passed, 5 subtests passed.

## Implemented

### 1. Extended trade post-mortem

Updated `src/nexus_titan/research/post_mortem.py` while preserving its existing public entry point and original report fields.

New descriptive fields:
- long/short trade counts;
- average winning and losing trade P&L;
- best and worst trade;
- average holding duration in bars;
- exit-reason counts;
- profit concentration among winning trades;
- optional regime buckets when entry-index regime labels are supplied;
- explicit minimum-sample warning (default threshold: 30 trades);
- explicit `DESCRIPTIVE_TRADE_LOG_NOT_CAUSAL` attribution label.

Fees are taken from the backtest result. Slippage remains an estimate supplied as `slippage_per_side`; it is not measured exchange slippage. Regime groups are not inferred: caller-provided labels are required. No regime labels were added to the synthetic dashboard fixture.

### 2. Component health monitor

Added `src/nexus_titan/operations/health.py`.
- Requires timezone-aware heartbeats.
- Tracks heartbeat age and consecutive failures.
- Reports HEALTHY, DEGRADED, STALE, CRITICAL or UNKNOWN.
- Does not restart, stop or mutate the monitored component.

### 3. Conservative watchdog policy

Added `src/nexus_titan/operations/watchdog.py`.
- Critical component => `OPERATOR_RECOVERY_REQUIRED`.
- Stale component => `HOLD_NEW_RESEARCH_TASKS` advisory.
- Degraded/unknown component => operator alert.
- Result explicitly states no automated restart, no trading-control change and no live order.

This is a decision policy/library, not a continuously running OS process supervisor. Actual orchestration, alert delivery and recovery drills remain future work.

### 4. Resource manager

Added `src/nexus_titan/operations/resource_manager.py`.
- Validates concurrent-job, memory and CPU budgets.
- Returns ALLOW, THROTTLE or REJECT for research workload admission.
- Accepts externally sampled resource values; it does not sample the OS itself.
- Never kills processes or interrupts trading controls.

### 5. TITAN EVOLVE handoff compatibility

Verified that the extended post-mortem can be captured through existing `TitanEvolveEngine.capture_post_mortem` as a heuristic learning record. The record remains research memory with traceable source/evidence. It is not a proven trading rule and cannot change risk limits, permissions or live-trading state.

## Verification

- `PYTHONPATH=src pytest --override-ini addopts='' -q`: **372 passed, 5 subtests passed**.
- `python -m compileall -q src tests scripts`: passed.
- `PYTHONPATH=src python scripts/run_project_validation.py`: passed.
- `PYTHONPATH=src python scripts/run_advanced_backtest_suite.py`: completed and regenerated the report.
- Final report test evidence: 372 / 372 passed; source fingerprint is `2e2ae544e6cbb2d59e4532019cb42b47c16a6aa1fd7ef54c913bf4b6c6108200` (90 Python source files).
- G0, G3, G4 and G5 are code-verified in the generated report; G1, G2, G6, G7, G8 and G9 remain external-input-required (4 of 10 gates code-verified).

## Backtest evidence and limitations

- Bundled NIFTY file remains a synthetic 120 daily-bar QA fixture (2025-01-01 through 2025-04-30), not licensed exchange history.
- Manifest integrity is false and `allowed_for_strategy_promotion` is false.
- Eight strategies are evaluated; all remain DRAFT. The synthetic index data is not a valid equity-delivery execution model.
- Walk-forward and Monte Carlo evidence remain too thin for promotion; report states insufficient evidence.
- Futures sample contains only three illustrative trades. These figures are not evidence of tradable profitability.
- The ₹50,000 shadow account section is a deterministic one-run fixture, not multi-day paper observation. No live order was transmitted.
- Regime-wise attribution is available only when a caller supplies entry-index-to-regime labels. It is intentionally not fabricated from this fixture.
- Health/watchdog/resource modules are tested utilities, not a deployed persistent operations daemon or measured production telemetry system.

## Not implemented / external evidence still required

- Continuous background watchdog service, alert delivery, service restart orchestration and crash-recovery acceptance drills.
- OS-level resource sampling, container/process quotas, priority scheduling and memory-safe workload termination (termination remains disabled by design in this stage).
- Real broker fills, quote/tick data, queue position and execution-cost calibration for causal slippage attribution.
- Strategy regime labelling validated against licensed point-in-time market data.
- Licensed market history, official instrument master/market calendar, exchange margin and broker contract-note reconciliation.
- Independent security assessment and multi-day ₹50,000 shadow evidence.

## Safety

- No modifications to independent risk limits, permissions, approval tokens, kill switch or live-trading configuration.
- Watchdog and resource manager do not submit or cancel orders.
- No automatic strategy promotion or production code deployment.
- No live orders transmitted.
