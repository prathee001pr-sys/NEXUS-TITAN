# NEXUS TITAN — Stages 37–39 Combined Safety Engineering Review
**2026-11-02 · Synthetic research-only · Unmerged stacked GitHub draft PRs**

## Summary

This batch deepens an **opt-in, brokerless paper-only account**, adds a
durable optimistic concurrency barrier against stale overwrite, and tests
several modules together with *temporary synthetic accounts*. It does
**not** finish a secure global trading order router or prove real F&O
profitability.

| Stage | Code delivered | Evidence |
|---|---|---|
| 37 | Opt-in `VirtualAccount(strict_paper_mode=True)` with durable initial policy, manual-only approval and risk, no normal fill without intact manual approval, long-only SELL, one-way strict migration and emergency exit support | [Draft PR #29](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/29), 1,014 tests + 5 subtests green in Python 3.11/3.12/3.13 |
| 38 | Per-account SQLite `revision`, `BEGIN IMMEDIATE` optimistic CAS; stale handle rejected and must reopen, including emergency action, with parallel-writer tests | [Draft PR #30](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/30), 1,025 tests + 5 subtests green on three Python versions |
| 39 | Offline adversarial lifecycle audit: guarded research + strict virtual account + manual gateway + unsigned paper-intent evidence + stale-writer rejection + no naked SELL + durable recovery + emergency stop | New stacked draft PR after Stage38; latest CI required |

## Stage37 integration issue caught by tests

The first iteration of the strict-account feature only persisted its
setting when the *first order* was written; an empty account could be
reopened without its required strict policy. The corrected implementation
persists strict mode **on construction**, before any orders, and verifies
the legacy-to-strict migration only from a genuinely persisted baseline.
The revised synthetic CI passed.

## Stage38 lost-update fix

Two separate `VirtualAccount` objects can load the same old SQLite
snapshot. Before the revision gate, the second could overwrite
newly committed cash, orders or positions with stale data. The new
optimistic CAS checks the committed `revision` inside the account
snapshot write transaction and rejects outdated versions rather than
overwriting them. Reads before mutation also validate freshness.
If another writer commits between the precheck and write, the final
CAS still rejects the stale writer. The stale in-memory object is
**quarantined** and needs a new account instance.

This does not provide locking or atomicity across *different*
research-ledger databases, broker accounts, external services or
cloud processes.

## Stage39 synthetic audit

`scripts/run_stage39_strict_paper_adversarial_audit.py` uses
`TemporaryDirectory`, synthetic dummy contract/account credentials,
and only local Python/SQLite operations. It emits structured JSON with
a pass/fail field per check and explicit negative claims for
production readiness, market-data authenticity, global routing and
authenticated identities.

Checks include: strict policy saved before an order, guarded research
audit, initial flat preflight, default-deny paper permission, unfilled
manual BUY, unsigned evidence valid only while pending, unapproved
fill rejection, evidence invalidation after approval, approved
simulated BUY, stale-process overwrite denial, no naked/oversized
SELL, duplicate pending SELL denial, manual SELL authorization,
reconciliation and restart, strict mode survival, emergency
SELL-to-close, persisted kill-switch and stale emergency-handle
fail-closed, no gateway BUY after kill, AUTO_PAPER escalation denial.

**No external market data, no licensed vendor source, no live market
connection, no genuine broker execution.**

## Unresolved blocking requirements

- **Global mandatory admission**: strict mode is opt-in; existing legacy
  `VirtualAccount` and Stage19 research APIs are intentionally retained
  for historical synthetic tests. The Stage33 PaperIntentGateway also
  remains opt-in.
- **Independent authority**: SHA256 evidence is not signed by an external
  identity provider. A malicious Python process or DB owner can forge
  or corrupt local inputs and approvals.
- **Cross-ledger capital**: VirtualAccount and the SQLite options
  research ledger still have independent cash/inventory journals. Matching
  account IDs do **not** create a global atomic risk book or guarantee
  same risk exposure.
- **Market realism**: historical 1-minute contract-wise NSE options and
  futures depth, OI, bid/ask, strike/expiry/lot source provenance, data
  licensing and actual exchange execution remain unverified. No
  claims of live-simulation profitability, real brokerage fill quality,
  broker-side margin reconciliation or strategy promotion.
- **Recovery/incident response**: a stale account must be reloaded
  before emergency simulation; actual brokerage emergency position
  closure needs protected external reconciliation and an independently
  authenticated broker-side kill pathway.
- **User interface**: the previously approved premium black/silver
  dashboard reference is unchanged; this batch does not implement
  a new UI/voice control surface.

## Recommended next work

Do not jump to live trading. First independently review all draft PR
dependencies and merge order, enforce a single paper-only deployment
entrypoint with no legacy bypass in that deployment configuration, design
independent identity and risk policy service, integrate a unified
cash/positions reconciliation boundary, then verify real licensed
F&O historical market data and execute longer shadow validation. Continue
to preserve historical data upload for the user-approved final step.

**Release verdict: RESEARCH-ONLY / NOT PRODUCTION-READY.**
No merge to `main`, real-money trading, or auto-promotion without explicit
operator approval and validated evidence.
