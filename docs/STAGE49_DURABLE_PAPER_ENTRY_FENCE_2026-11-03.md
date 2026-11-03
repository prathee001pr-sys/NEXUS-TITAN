# NEXUS TITAN — Stage49 Durable Synthetic Paper-Entry Fence

**Date:** 2026-11-03  
**Branch:** `feature/stage49-durable-paper-entry-fence-2026-11-03`  
**Parent:** Stage48 draft PR #40  
**Classification:** OFFLINE COOPERATIVE ADMISSION / NON-PRODUCTION

## What changed

The project has two distinct paper/research accounting books:
`VirtualAccount`'s durable SQLite state and
`DurableResearchShadowLedger`'s research reservations. Their writes
are **not** one atomic cross-database transaction, and both can be called
through older Python entrypoints. Stage49 **does not falsely claim** to
unify those ledgers.

Instead, Stage49 builds a third, *operator-selected local SQLite coordinator*
for a strictly bounded new synthetic-paper BUY path over the Stage48 signed
manual session and Stage47 Risk & Veto. This is defensive crash fencing
for **cooperating Stage49 clients only**, not a production capital service.

### New components

- `src/nexus_titan/operations/durable_paper_fence.py`
  - `Stage49DurablePaperFence(session, db_path=...)` requires an explicit
    separate coordinator SQLite path and a signed Stage48 paper session.
  - Binds one account ID, starting paper capital (exact cent precision)
    and virtual/research/replay/coordinator file paths to a durable scope
    fingerprint. A changed account, capital amount or path layout refuses
    reuse. The coordinator cannot share DB files with the other three.
  - Checks Stage45's read-only *virgin-flat* preflight, independent ledger
    integrity, account identity and exact cent current cash comparison.
  - Rejects malformed request identifiers, invalid quote notional and
    notional above account starting cash before registering an attempt.
  - Requires Stage47's authoritative risk/contract cap, local Red-Team
    veto and synthetic quote freshness/depth/spread criteria.
  - Uses SQLite `BEGIN IMMEDIATE` to serialize the **coordinator's own**
    one-entry-per-account attempt and double-checks two book balances.
  - **COMMITs a permanent `PREPARING` marker BEFORE calling Stage48.**
    When Stage48 creates a pending manual virtual order, finalizes marker
    to `PENDING`; if the next step fails, retains `PREPARING` or writes
    `UNKNOWN`. All these states **block a retry indefinitely** pending
    a manual recovery audit. This is conservative and deliberately allows
    false-positive lockout instead of losing an uncertain order.
  - One lifetime BUY attempt per coordinator scope; no local method for
    resetting/removing this marker. Stage49 does NOT grant user a trade
    approval or auto-fill simulated orders.
  - Immutable `Stage49AdmissionStatus` explicitly reports all true
    production/global authority markers as **false**.

- `tests/test_stage49_durable_paper_fence.py`
  - Variable virtual capital (not fixed to ₹50,000).
  - Exact cents, first admission and repeat/alternate command id rejection.
  - Two simultaneous distinct coordinator clients sharing one SQLite DB.
  - Simulated crash after a marker commit and after a virtual-order commit.
  - Uncertain external result, stale session, persistent restart refusal.
  - Cash drift, top-up mismatch, corrupt coordinator scope, alias/symlink
    defense, untrusted quotes, oversized notional and expired paper enablement.
  - Continues Stage48 signed manual paper approval without clearing the
    coordinator marker. Does not place fills or live orders.

- `scripts/run_stage49_paper_fence_smoke.py`: isolated temporary local
  test-only synthetic accounts, one pending paper BUY, duplicate and
  restart rejection; prints no token secrets and creates no real orders.

## Important unresolved security / accounting gaps

1. **NOT a unified capital authority:** Stage49 coordinator records
   intended notional and a one-shot admission lock; it does **not**
   reduce or reserve cash in both independent ledgers. It cannot
   reconcile real fill fees, slippage, margin, option inventory or P&L.
   An actual single-source-of-truth ledger or rigorously isolated risk
   budgets and reserve/commit/release workflow is still required.
2. **NO cross-DB atomicity:** a PREPARING marker and a subsequent
   VirtualAccount order are two different transactions. Crash recovery
   conservatively leaves unresolved markers, never auto-retries.
   The research ledger remains independent. Committing marker before
   the order limits duplicate *Stage49* requests but does not prove
   true capital conservation across the two books.
3. **NO global enforcement:** a caller can still use Stage43/45/47/48 or
   direct legacy virtual/research APIs, or select a different
   coordinator path. This is cooperative fencing, not a protected
   OS-level service, independently verified risk microservice,
   immutable security boundary or broker-side authorization.
4. Stage48 signed approvals prove HMAC key possession, **not external
   identity**; signer isolation, revocation, human identity providers
   and approval/fill-time rechecks remain separate P0 work.
5. Inputs are synthetic local quotes; **not genuine licensed historical
   or live market data**. Stage49 only admits Stage47 synthetic
   `EQUITY_DELIVERY` BUY QA. No NIFTY/BANKNIFTY F&O, live exchange
   quote, real margin, actual broker execution or strategy promotion.
6. Existing paper SELL/protective exits are NOT replaced, and Stage49
   does not alter the independent order-fill lifecycle. The coordinator
   should be viewed as an additional narrow new-BUY entry safeguard.
7. Existing draft PR stack remains unmerged; final owner review and
   combined post-merge CI are outstanding. GitHub reported `main`
   unprotected in Stage46; inspect and enforce protection/rulesets.

## Verification

```bash
python -m pytest -q tests/test_stage49_durable_paper_fence.py
python scripts/run_stage49_paper_fence_smoke.py
python -m pytest -q
```

Require final-head GitHub Actions 3.11, 3.12 and 3.13 **all green**
before calling this offline coding milestone tested. Passing tests do not
establish production readiness.

## Next work

Stage50 should focus on attaching the approved black/silver dashboard
to **read-only** vetted paper metrics, approvals and risk veto evidence;
write actions should remain restricted until a proper independent
capital-authority, authenticated identity and global risk architecture
has been reviewed. Real market datasets can be imported later as the
user explicitly requested.
