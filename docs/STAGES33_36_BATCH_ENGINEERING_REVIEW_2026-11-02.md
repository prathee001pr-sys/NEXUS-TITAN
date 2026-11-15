# NEXUS TITAN — Stage 33 to Stage 36 Sequential Engineering Batch Review
**Date:** 2026-11-02 · **Status:** Offline research only · **Base:** Stage32 PR #24

## User-directed stage limit
The request was to continue through Stage39 **only if appropriate**, otherwise finish
through Stage36, test and review. The verified engineering review concludes
**STOP AT STAGE 36 FOR NOW**. Stages37–39 must not be described as complete:
global, externally enforced Risk & Veto and independent identity remain
unimplemented. Deeper feature development without that boundary would make
the system wider, not adequately safer, and historical licensed F&O data has
intentionally been postponed until later.

## Stage-by-stage implementation

| Stage | GitHub draft PR | Implementation | Regression CI |
|---|---|---|---|
| 33 | [#25](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/25) | Opt-in `PaperIntentGateway`; default-deny permission, strict manual BUY intent, owned SELL-to-close intent, pending SELL double-close rejection, separate guarded ledger integrity preflight | 970 tests +5 subtests (Python 3.11,3.12,3.13) |
| 34 | [#26](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/26) | Guarded Stage24 options SELL-to-close repeats PAPER_TRADE permission, ledger audit validation and no open BUY reservation under SQLite BEGIN IMMEDIATE. Fix Stage28 guarded-mode audit event compatibility in FIFO replay, retain legacy compatibility | 978 tests +5 subtests |
| 35 | [#27](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/27) | `PaperIntentEvidence` frozen unsigned SHA256 risk/order/ledger fingerprint; revalidation detects order changes, risk-policy drift, altered ledger, kill or approved fill. Does not authenticate signer | 990 tests +5 subtests |
| 36 | Draft stacked PR after Stage35 | End-to-end synthetic offline temporary-account CLI and regression tests for BUY manual approval, order-evidence expiry, SELL-to-close, state reconciliation, restart, kill-switch recovery and valid-contract direct reservation denial | Full 3-version Python GitHub CI + separate 16 synthetic safety assertions |

All draft PRs stack sequentially; none is merged to `main`.
All external market data uploads are **untouched**, source provenance unverified.
All tests are synthetic and do not demonstrate actual options profitability.

## Stage34 defect discovered and fixed

The first Stage34 E2E test failed: Stage28 added a legitimate
`ENABLE_GUARDED_PAPER` audit event, but Stage24 FIFO replay treated all
unknown audit events as potentially cash-changing and rejected the ledger.
The updated replay explicitly accepts this event only with correct
`no_live_routing` flag and a persistently guarded account. Corrected
Stage34 three-version CI is green. This is material evidence that staged
integration testing found a previously hidden compatibility problem.

## Stage36: scope of synthetic integration audit

Run `python scripts/run_stage36_synthetic_paper_e2e.py` **only in a development
environment** if you want a synthetic smoke check. It operates solely in
`TemporaryDirectory`, outputs JSON, and does not load real market data.
It asserts no broker/live authority, no automatic strategy promotion, and
no authenticated production identity. Its test suite includes a valid
NSE-style **synthetic** contract for direct guarded-ledger reserve bypass
check; rejecting malformed values alone is not treated as sufficient proof.

## Remaining critical blockers

**P0 Global safety**
- `VirtualAccount.submit_order` and Stage19 legacy research APIs remain
  public and callable. Opt-in `PaperIntentGateway` is **not** globally
  mandatory. Existing `require_pretrade_risk_check=False` is permitted in
  legacy synthetic unit tests; it must never be used in any production-like
  account.
- Cross-ledger accounting is not one atomic journal. Matching account IDs and
  independent preflight do not establish equivalent risk, inventory or cash
  between `VirtualAccount` and Stage19.
- External identity attestation, signed one-time intent/approval receipts,
  immutable externally witnessed logs and OS/provider secret isolation
  do not exist. Stage35 fingerprint is **unsigned**, easily recomputed
  by anyone able to modify code or account state.

**P0 Execution/data**
- Real contract-specific NIFTY/BANKNIFTY options/futures depth, historical
  1-minute fills, individual expiries, strikes, lots, corporate/calendar
  updates and licensed source authenticity have not yet been validated.
- Paper simulator does not prove real slippage, liquidity, fills, margin,
  taxation/broker charges or trade profitability; shadow live observation
  remains pending.
- Emergency exits use simulated prices; real broker order placement and
  broker-side kill control are intentionally absent.
- Crash consistency across multiple `VirtualAccount` processes isn't a
  shared globally locked risk service.

## Gate for later Stages37–39

Only resume when a reviewed **single enforced brokerless paper admission
boundary**, synchronized durable account state, signed/externally verified
approval mechanism and complete sell/kill/recovery policy test plan are
designed and independently verified. Do not treat four green stage milestones
as 100% functionally complete. Security must not depend on an untrusted
in-process flag.

**Final verdict: Stage36 R&D milestone only; production-ready = NO;
real-money trading = OFF; human merging/review required.**
