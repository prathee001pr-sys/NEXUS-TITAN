# NEXUS TITAN — Master Trading Upgrade Register (Blueprint v5.0)

**Review date:** 02 November 2026  
**Reference:** NEXUS TITAN Trading-Only Advanced Upgrade Blueprint v5.0  
**Review basis:** Stage 1–15 canonical local candidate, clean ZIP extraction, source inspection and regression validation.

## 1. Evidence and status rules

This register maps the v5.0 requirements to the code actually inspected. It deliberately separates software evidence from market-data, operating and release evidence.

- **BUILT + TESTED (LOCAL CANDIDATE):** implementation exists and the relevant code is covered by the 426-test candidate suite. This is not yet evidence that the same source tree is committed to the GitHub integration PR.
- **PARTIAL:** a bounded implementation exists, but one or more blueprint acceptance criteria remain incomplete.
- **EXTERNAL EVIDENCE REQUIRED:** code cannot establish the external fact by itself (for example, a data licence, exchange margin file, penetration test or multi-day market observation).
- **NOT VERIFIED:** there is not enough evidence to mark the requirement Tested or Verified.

No row is marked production-verified. A green unit-test suite does not establish profitable strategies, exchange-calibrated execution or readiness for real-money trading.

## 2. Baseline under review

| Item | Verified fact |
|---|---|
| Candidate archive | `NEXUS_TITAN_Stage1-15_Canonical_Integrated_2026-11-02.zip` |
| Candidate SHA-256 | Recorded in the release ZIP sidecar `.sha256` and external candidate manifest (kept outside this self-contained file to avoid a self-referential hash). |
| Source modules | 96 Python files under `src/nexus_titan/` |
| Test modules | 56 `test_*.py` modules |
| Regression result | 426 passed; 5 subtests passed |
| Additional checks | compile check and `scripts/run_project_validation.py` passed; release preflight passed code checks and found 0 secret-pattern matches |
| Package hygiene | release ZIP contains no SQLite runtime DB, `__pycache__`, or `.pyc` files |
| Release preflight | `BLOCKED_EXTERNAL_EVIDENCE` |
| Live trading | Disabled; no live broker/order route enabled |
| GitHub source boundary | PR #1 remains draft at Phase 6 integration head `1e9436f6b82baf55eb33d4b98ff0cf47dc6fd69c`; its GitHub Actions run #41388360519 reported 286 passed + 5 subtests. The full 426-test candidate is a separately tested local ZIP and is not yet the PR's source tree. `main` remains unchanged. |

## 3. v5.0 Master Trading Upgrade Register

| ID | v5.0 requirement | Current code evidence | Current state | Remaining acceptance work |
|---|---|---|---|---|
| NT-DATA-01 | CSV/OHLCV and feed integrity | `data/canonical.py`, `data/csv_import.py`, `data/csv_ohlcv.py`, `data/quality.py`, `data/provenance.py`, `data/service.py`, `data/sessions.py`; regression tests cover malformed rows, OHLCV bounds, time ordering, duplicates and provenance gates. | **BUILT + TESTED (LOCAL CANDIDATE)** | Connect an approved data provider; verify licence, actual historical coverage, point-in-time contract master, official calendar and source authenticity. Synthetic sample data must remain promotion-ineligible. |
| NT-MKT-02 | Unified Market State Tensor | `intelligence/market_state.py::MarketState` and `MarketStateBuilder` provide immutable quality-marked state blocks, event/ingest timestamps, stale detection, missing-block flags and provenance warning. | **BUILT + TESTED (CONTRACT)** | Version the state schema; prove provider-to-state end-to-end lineage, clock/freshness policy and invalid-state handling on real feed replay. |
| NT-ANL-03 | Approximately 30 analytical components | Present subset includes SMA/EMA/RSI/MACD/ATR/Bollinger (`research/indicators.py`); VWAP, ROC, realized volatility, ADX, opening range, order-book imbalance, regime classification, OI summaries, IV skew and gamma exposure (`research/market_intelligence.py`). | **PARTIAL + TESTED** | Do not label the catalogue 30/30 complete. Add/verify candlestick and swing structure, support/resistance, breakout/pullback/failure, volatility expansion/compression, time-of-day effects, reliable event context, calibrated uncertainty and regime-specific attribution. Every feature needs warm-up, missing-data, point-in-time and leakage tests. |
| NT-OPT-04 | Options chain / Greeks / IV / expiry | `derivatives/options_engine.py` provides theoretical Greeks and bounded IV solving; `derivatives/chain_and_settlement.py` provides point-in-time quote validation, OI/spread checks, indicative SPAN/ELM arithmetic and expiry settlement handling. | **BUILT + TESTED (OFFLINE ANALYTICS); PARTIAL FOR MARKET USE** | Add licensed historical option-chain coverage, validated expiry/strike/lot-size metadata, official margin files and broker/exchange reconciliation. Indicative margins and theoretical Greeks are not official exchange values. |
| NT-STR-05 | Strategy research and walk-forward | `research/backtest.py`, `research/backtest_engine.py`, `research/v6_validation.py`, strategy lab and Monte Carlo tooling; chronological OOS/walk-forward and promotion blockers are tested. | **BUILT + TESTED (RESEARCH FRAMEWORK)** | Re-run on licensed point-in-time data; expand independent market fixtures and sample-size requirements. Existing synthetic/short samples are insufficient to promote a strategy. |
| NT-SIG-06 | Consensus + calibrated uncertainty | `intelligence/calibration.py` adds OOS-only Brier score, ECE and reliability bins; strict checks reject in-sample labels, duplicate IDs and invalid observations. Consensus output remains explicitly UNCALIBRATED. | **PARTIAL + TESTED (diagnostics only)** | Define/persist a predeclared outcome contract; connect predictions and resolved outcomes with lineage; validate sample size and regime reliability before any confidence label changes. |
| NT-RSK-07 | Independent Risk & Veto | `risk/authoritative_risk.py`, `risk/portfolio_risk.py`, `risk/risk_manager.py`, permission guard, virtual account and kill-switch controls; risk remains outside consensus authority. | **BUILT + TESTED (CODE-LEVEL)** | Independent security review, operational kill-switch drill and deployment-specific access-control review. Never allow EVOLVE or consensus to modify authoritative limits. |
| NT-EXE-08 | Execution simulator + reconciliation | `simulation/execution_simulator.py`, `virtual/microstructure.py`, `virtual/order_manager.py`, `virtual/durable_store.py`; supports virtual order lifecycle, fees, partial fills, persistence, idempotency and reconciliation fixtures. | **PARTIAL + TESTED** | Calibrate against licensed quote/trade/order-book data and broker contract notes; add queue position, exchange rejects, venue-specific tick/lot/freeze rules and robust multi-session reconciliation. |
| NT-TWIN-09 | Digital Twin / scenario lab | `simulation/digital_twin.py` provides deterministic OHLCV stress scenarios and repeatability tests. | **BUILT + TESTED (DETERMINISTIC)** | Calibrate shocks, spreads, liquidity and impact against real market observations; add scenario coverage and independent failure-injection review. Not an exchange-calibrated twin today. |
| NT-RED-10 | Adversarial Red-Team | `research/adversarial_red_team.py` supplies deterministic advisory challenges before simulated execution. | **BUILT + TESTED (ADVISORY)** | Measure false positives/negatives against a labelled scenario set; add independent challenge evidence. Red-Team is not a substitute for authoritative risk veto. |
| NT-EVL-11 | TITAN EVOLVE controlled loop | `self_improvement/agents.py`, `self_improvement/agent_runtime.py`, `self_improvement/agent_creation.py`, `evolve/governance.py`, `evolve/sandbox.py` and strategy lab provide supervised specialists, approved tool adapters, experiment governance and proposal-only workflows. | **PARTIAL + TESTED (GOVERNED FRAMEWORK)** | Demonstrate complete observe→attribute→diagnose→research→sandbox→compare→validate→approve→rollback lifecycle using reproducible evidence. No generated code execution or automatic production promotion. The 12 EVOLVE specialist classes are not 12 always-running trading bots. |
| NT-POST-12 | Post-mortem / attribution | `research/post_mortem.py` produces descriptive trade and outcome summaries; EVOLVE can capture research notes from post-mortem output. | **BUILT + TESTED (DESCRIPTIVE)** | Bind every result to strategy version, market-state snapshot, dataset fingerprint, costs, simulated fills and regime; test attribution on multi-session evidence. Reports are descriptive, not causal proof. |
| NT-EXT-13 | External Telegram signal intelligence | `data/telegram_ingest.py` provides allowlisted, read-only candidate ingestion, deduplication/edit tracking, quarantine and research-only storage. | **PARTIAL + TESTED (INGESTION GUARD)** | Configure and independently verify a real approved Telegram source; test authentication, rate limits, provenance and prompt-injection handling in deployment. No message may directly trigger an order. |
| NT-SEC-14 | Watchdog, audit, recovery, secrets | `operations/health.py`, `operations/watchdog.py`, resource manager, hash-chain audit, runtime recovery and Stage 15 safety regressions are present. | **PARTIAL + TESTED (LOCAL CONTROLS)** | Independent penetration/security assessment; encrypted production secret and DB handling; backup/restore and crash-recovery drill on target deployment; incident runbook exercise and identity/MFA/ACL review. Static scanning is not a security certification. |
| NT-SHD-15 | ₹50,000 virtual shadow gate | Virtual account supports explicit virtual capital; shadow ledger and session reconciliation framework are tested. Existing ₹50k result is a deterministic software fixture. | **FRAMEWORK BUILT + TESTED; SHADOW VALIDATION NOT VERIFIED** | Complete predeclared multi-day shadow window using licensed live data, immutable daily statements, fills/cost reconciliation, risk/incident evidence, minimum trade/session criteria and owner review. No live orders. |

## 4. Analytical catalogue — honest coverage snapshot

This table is a code map, not a claim of 30 completed and calibrated analytics.

| v5.0 group | Confirmed present in candidate | Not yet verified / incomplete |
|---|---|---|
| Price / structure (1–6) | SMA/EMA, RSI, MACD, ROC, VWAP, ADX, ATR, Bollinger and opening-range functions. | Dedicated candlestick taxonomy, swing-structure engine, support/resistance and robust breakout/pullback/failure classification. |
| Regime / volatility (7–11) | Trend/range classifier, realized volatility, opening-range and market-session/calendar foundations. | Calibrated volatility expansion/compression, robust intraday time-of-day behaviour and regime transition quality on actual data. |
| Options (12–17) | Chain quote integrity, OI summaries, theoretical Greeks, IV solver/skew, gamma exposure, spread and expiry/settlement calculations. | Licensed point-in-time chain history, exchange-verified contract/expiry metadata, official SPAN/ELM and execution-grade strike liquidity. |
| Flow / context (18–22) | Order-book imbalance and bounded microstructure simulator; read-only Telegram ingestion. | Reliable trade-flow classification, validated liquidity-gap features, authenticated FII/DII data and verified news/macro/event feed. |
| Decision / risk (23–27) | Evidence consensus, WAIT/NO TRADE, deterministic red-team, cost-aware backtest and portfolio risk controls. | Empirically calibrated uncertainty, robust trap/failure labels, validated after-cost expected payoff and portfolio/correlation risk on real multi-asset data. |
| Execution / learning (28–30) | Fill simulation, virtual ledger, session reconciliation, post-mortem and supervised EVOLVE evidence capture. | Empirical fill probability/quality, multi-session outcome lineage and regime-specific failure/performance evidence. |

## 5. Release gates and blockers

| Gate | Current evidence | Decision |
|---|---|---|
| G0 — Build reproducibility | Candidate ZIP re-extracted; compile and project validation passed. | **PASSED — local code evidence** |
| G1 — API / behaviour correctness | 426 tests passed; 5 subtests passed. Adapted modules still need independent line-by-line and contract review. | **PARTIAL — test suite passed; independent review open** |
| G2 — Data integrity / provenance | Local schema, hash and quality gates tested; bundled NIFTY sample is synthetic. | **EXTERNAL EVIDENCE REQUIRED** |
| G3 — Accounting arithmetic | Partial-fill fee golden and futures/options arithmetic fixtures passed in candidate audit. | **PASSED — bounded fixtures only** |
| G4 — Risk / approval safety | Stage 15 kill-switch, idempotency and approval-hash regressions pass. | **PASSED — code tests; external security review open** |
| G5 — Simplified execution | Deterministic virtual fills, lifecycle and accounting tests pass. | **PASSED — simplified simulation only** |
| G6 — Independent security | Static secret-pattern scan returned zero findings. No independent assessment supplied. | **EXTERNAL EVIDENCE REQUIRED** |
| G7 — Operations / recovery | Local watchdog/health/recovery code exists; target-environment restore drill not evidenced. | **EXTERNAL EVIDENCE REQUIRED** |
| G8 — Multi-day shadow | Single-session deterministic fixtures only; no licensed live-feed multi-day shadow record. | **NOT VERIFIED** |
| G9 — Owner sign-off | No final release sign-off recorded. | **NOT VERIFIED** |

The current release preflight result is `BLOCKED_EXTERNAL_EVIDENCE`; live trading remains disabled.

## 6. Next engineering order

1. **Source-of-truth alignment (P0):** put the complete 412-test candidate on a dedicated Git branch and run hosted CI against that exact commit. Keep PR #1 and `main` unchanged until the candidate source and audit evidence agree.
2. **Market-data evidence (P1):** resolve vendor licence, actual coverage, point-in-time instrument master, expiry/lot-size history and exchange calendar. Do not substitute synthetic fixtures.
3. **Feature and options validation (P2):** complete missing analytics and exercise options-chain calculations on licensed expiry-specific history; reconcile margin and charges to official/provider records.
4. **Decision calibration (P3):** add out-of-sample calibration and reliability tests; preserve `WAIT / NO TRADE` on insufficient evidence.
5. **Execution and operations (P4):** calibrate fill quality, spread, slippage and partial fills; run backup/restore, kill-switch and security drills.
6. **Shadow proof (P5):** only after P1–P4, start the ₹50,000 virtual multi-day shadow window with predeclared success/failure criteria.

## 7. Non-negotiable boundaries

- Existing V2/Phase 7 source and working interfaces are preserved; no rewrite for convenience.
- Eight T01–T08 specialist responsibilities are logical boundaries, not a requirement for eight separate always-on bots.
- The twelve EVOLVE specialist classes are not counted as active trading bots.
- No generated Python execution, dynamic import, self-deployment or automatic strategy promotion.
- Risk, permissions, kill-switch and user authority remain outside EVOLVE control.
- No broker/live order route; paper/virtual only. No real-money action is authorized by this register.
