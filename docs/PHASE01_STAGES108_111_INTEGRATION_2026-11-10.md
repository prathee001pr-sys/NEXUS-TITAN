# NEXUS TITAN — Phase 01, Stages 108–111

Date: **2026-11-10**. Artifact: **offline additive integration candidate**. No live order, no order router, no broker credentials, no automatic AI strategy promotion. Does not merge `main` or change GitHub visibility.

## Scope and provenance

- Source foundation: Stage98 GitHub tracked-source export, commit `8b132a69e431759709c384c1eb4eb61c4e089bc1` (538 tracked files in export; local manifest SHA-256 comparison found **0 modified original files**).
- Local Stage99 v3 + Stage100–103 + Stage104–107 official **offline** ZIPs were layered one at a time, with ZIP CRC and recorded SHA256SUMS verification. Existing Stage99–105 source/test git blobs match GitHub Stage105 commit `34846f8f2e76effd62f0847ae0bff5a7da8afd11` for paths inspected.
- Stages106–107 are **local-only, unmerged/unverified in remote CI** and remain a requirement to deploy this Phase01 candidate. Local ZIP content identity does not certify GitHub ancestry or real-market validation.
- Only **new** `stage108`–`stage111` source, tests, docs, and bounded test runner added. No old runtime, risk, permissions or execution source modified, and no external packages added.

## Stage implementation

| Stage | Module | Engineering responsibility | Proof / non-goals |
|---|---|---|---|
| 108 | `operations/stage108_upgrade_compatibility.py` | Links Stage104 catalog, Stage105 preview, Stage106 OOS review, Stage107 negative-case report. Strict synthetic + no-live lineage; registers six public reference categories | Rejection of source/permission promotion and cross-stage mismatch; hashes are not market authenticity |
| 109 | `operations/stage109_effective_dated_stt.py` | Offline effective-date STT calculations for option sale, expiry exercise and futures sale, with optional hypothetical other charges and conservative paise rounding | Rate boundary 2026-04-01; **not** exact broker fees/tax rounding |
| 110 | `operations/stage110_deterministic_execution_replay.py` | Deterministic event-sequenced **synthetic L1** quote/fill/cancel replay; separate displayed liquidity, lots, time, price protection, stale quote, fill ceilings | Does **not** claim L2 order books, real fills or exchange evidence |
| 111 | `operations/stage111_phase01_acceptance.py` | Joins Stage108 compatibility + Stage110 replay + Stage109 cost + Stage105 preview + immutable unapproved research proposal; one explicit `review_stage111_pipeline()` entry point | Accounting reconciliation on synthetic inputs only; always `NO_GO`, no code execution or automatic strategy promotion |

## Reference-to-module decisions

- **Bhav**: useful effective-dated cost/data design, no copied third-party implementation. The Bhav cost constants inspected were outdated relative to **NSE/FATAX/73524 (31 Mar 2026)**; this model uses the confirmed 2026 STT boundary. No broker commissions automatically inferred.
- **NautilusTrader**: deterministic event sequencing and book-consumption ideas, without Rust stack or a competing engine.
- **LEAN**: conservative partial fill/price-protection contract ideas. Full option combinations, assignment and margin support are deliberately deferred to Phase03/04.
- **Qlib + RD-Agent**: source/experiment hashes, fixed seed, proposed/rejected research state; **no** automatic code execution, heavy ML import, evaluation claims or strategy promotion.
- **Jesse**: deterministic seed and robustness-contract inspiration only; Monte Carlo/bootstrapping is **not** implemented in Phase01.

## Statutory tax assumptions

Official NSE reference: <https://nsearchives.nseindia.com/content/circulars/FATAX73524.pdf>

| Transaction | 2024-10-01 through 2026-03-31 | From 2026-04-01 |
|---|---:|---:|
| Option premium sale (seller, on premium) | 0.10% | 0.15% |
| ITM option exercised (purchaser, on intrinsic value) | 0.125% | 0.15% |
| Futures sale (seller, on traded value) | 0.02% | 0.05% |

`Stage109` accepts **2024-10-01 onward only**, so it does not apply the wrong rate to older years. It rounds synthetic STT up to **the next paise** per modeled transaction as an explicit conservative approximation, not the actual NSE/broker rounding policy. Brokerage, GST, stamp duty, SEBI and exchange charges are user-provided **hypothetical extra paise** and remain unverified, not a complete statutory cost model. Prospective external market/broker import must be blocked pending separate validations.

## Risk & Veto scope

- Stage107 records **declared synthetic negative fixtures**, not that the runtime independent Risk & Veto controls actually vetoed an order.
- Stages108/111 explicitly refuse a promoted `risk_veto_runtime_certified`, `trade_authorized`, `live_trading_enabled`, `strategy_promotion_enabled`, or broker-verified report.
- No real-market source, independent liquidity, STT broker settlement, 15-year NIFTY/BANKNIFTY licensed history, exchange-level fills, or live-order readiness is claimed.
- For paper trading, the **existing** Risk & Veto must be independently tested before any intent gateway; this package does not write/route to that gateway.

## Execution and reproducibility

1. Verify all ZIP SHA256SUMS, Stage98 historical manifest, and known Stage99–107 blobs.
2. Run the four focused test files with `PYTHONPATH=src python -m pytest -q -o addopts='' -W error tests/test_stage108* tests/test_stage109* tests/test_stage110* tests/test_stage111*`.
3. Run full regression with `PYTHONPATH=src python -m pytest -q -o addopts='' --disable-warnings tests/`, recording warnings separately; existing legacy tests can generate deprecation or SQLite warnings.
4. Require Python 3.11, 3.12, 3.13 GitHub CI + independent Secret Scan after **privacy-safe authenticated Git CLI** push to new stacked draft branches. Not done in this offline artifact.
5. Stage next-phase acceptance only after the exact existing Stage107 **Git history**, repository HEAD, license/data provenance and independent test gates have been confirmed.

## Decision

**Local code and full offline regression can be accepted as a research candidate; GitHub release/CI green and deployment remain pending.** No `main` merge, repository visibility changes, real-money broker integration or live permissions are authorized.
