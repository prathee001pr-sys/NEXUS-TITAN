# NEXUS TITAN — Stage 53: Single-DB Synthetic Capital Budget Prototype & Risk Architecture

**Date:** 2026-11-03  
**Parent:** Stage52 draft PR #44  
**Branch:** `feature/stage53-synthetic-capital-authority-2026-11-03`  
**Classification:** local synthetic accounting prototype, not a shared production capital authority

## Problem and exact scope

The previous Stage43/45/47/48/49 path uses distinct persistent databases
for virtual account orders, research shadow reservations, token replay
and a cooperative one-shot admission marker. Their cash fields are
NOT an atomic shared budget, and older Python methods remain directly
callable. Stage52's source inventory deliberately keeps
`production_release_allowed=false`.

Stage53 **does not mislabel those independent databases as solved**.
Instead, it builds an **isolated, bounded prototype** showing one possible
future authority's cent-exact durable accounting invariant.

### Implemented files

- `src/nexus_titan/operations/synthetic_capital_authority.py`
  - `Stage53SyntheticCapitalAuthority` stores *only its own* research
    budget holds in a local SQLite database, never modifies or authorizes
    Stage43 VirtualAccount, Stage19 research shadow ledger, Stage49
    coordinator, real brokers or market infrastructure.
  - Explicit account ID, starting amount in exact integer **cents**
    (not a fixed ₹50,000), and immutable `Stage53BudgetPolicy`.
    Default single hold ceiling is 20% of initial capital; aggregate
    held ceiling is 50%. These are **QA prototype settings**, not
    recommended trading risk sizes or safety guarantees.
  - A single SQLite `BEGIN IMMEDIATE` transaction checks all existing
    holds and the configured caps, refuses reused request IDs, appends
    an audit event, increases the held-total and commits atomically
    **within that one synthetic database only**. Same-file cooperative
    instances see the same budget, and restart preserves state.
  - Each audit event records an unkeyed SHA256 chain linked to the
    prior one, sequence number, request ID and cent amounts. The
    inspected held sum must equal the journal, revision and head.
    This helps catch mismatches and simple tampering but **cannot**
    establish adversarial integrity if the attacker can rewrite the
    whole SQLite DB and recompute unkeyed hashes.
  - `inspect()` checks the full local history and reports
    verification or failure with untrusted balances set to `None`.
    It never converts a failed audit to available capital or grants
    order submission approval.
  - Deliberately NO release/rollback of holds; later releases must
    prove exact fill, cancellation, fees and multi-book state via
    a separately reviewed reconciliation mechanism. This can
    lock otherwise available synthetic budget after a failed
    workflow. That conservative denial is a planned limitation.
  - DB path scope binds account, starting cents, risk policy and path.
    Symlinks and configured known other-ledger aliases are rejected.
    **It is not an OS-enforced service**: callers can choose another
    database path, edit Python code or call legacy virtual APIs.
  - Receipt/status always indicate `trading_authority=false`,
    `global_legacy_entrypoints_fenced=false`, external identity
    false, cross-DB atomicity false, real data false and live orders 0.

- `tests/test_stage53_synthetic_capital_authority.py`
  - Capital amount variability (illustrative starting ₹12.5k, ₹50k,
    ₹175k and other exact cent amounts), accounting invariants,
    single/aggregate cap denial, replayed request ID and invalid
    number/identifier/policy rejection.
  - Two independent Python budget instances concurrently writing
    the SAME SQLite path: only one 30%-hold may pass when their sum
    would exceed the 50% aggregate cap.
  - Concurrent small holds both commit safely and reconstruct an
    ordered audit hash chain.
  - Restart persistence; wrong account, changed capital, changed
    policy, path aliases and symlink rejection; corrupt head,
    event, journal and reservation fail closed.
  - Explicit absence of any trade/approval/fill/release methods,
    live broker claims, strategy promotion or cross-DB truth.
  - A disposable temporary-account CLI smoke.

- `scripts/run_stage53_capital_authority_smoke.py`: creates a
  standalone temporary SQLite budget ledger, records one illustrative
  ₹1,000 synthetic hold from ₹50,000, denies duplicate token and
  verifies restart persistence. Prints *only* synthetic accounting
  evidence, with no real order/price/broker connections.

- `src/nexus_titan/operations/release_security_audit.py` Stage52's
  bounded structural inventory now also checks the new Stage53
  source interface. This does NOT make it an independent release auditor.

## What Stage53 proves vs does NOT prove

| Case | Evidence / current limit |
| --- | --- |
| Exact-cent local budget accounting | implemented in ONE SQLite only |
| Concurrent same-file cooperative holds | serialized via `BEGIN IMMEDIATE` |
| Duplicate request IDs in same budget DB | fail closed, durable across restart |
| Altered journal/head within same DB | detected by local unkeyed chain checks |
| Authorized release after cancel/fill | **not implemented** |
| Atomic link to Stage43 virtual cash | **not implemented** |
| Atomic link to Stage19 research budget | **not implemented** |
| Atomic link to Stage49 admission marker | **not implemented** |
| Independent global veto boundary | **not implemented** |
| External human ID / signing / revocation | **not implemented** |
| Broker order execution / real-money permissions | **disabled and unimplemented here** |
| Real NIFTY/BANKNIFTY F&O feed | **not provided; deferred** |
| Public legacy API bypass prevention | **not implemented** |
| Production/real-time shadow readiness | **not verified** |

## Future architecture, separate from this bounded proof

A proper **single authority** should own all new-order budget
reservation, partial-fill settlement, execution fees, unrealized
exposure, margin, cancellation release and daily capital adjustments
under one isolated process, with an independently enforced risk
decision bound to an authenticated human or governed paper mode.

Mandatory entrypoints must be enforced outside the mutable in-process
legacy API boundary; risk checks must occur at admission **and**
approval/fill and require trusted, time-stamped point-in-time market
data. Cross-service messaging, retries and crash recovery require
idempotency and auditable replay or atomic one-ledger transactions.
Designing this is follow-on architecture work; this stage does NOT
automatically modify existing Stage43/49 databases or enable
runtime integration.

## How to test

```bash
python scripts/run_stage53_capital_authority_smoke.py
python -m pytest -q tests/test_stage53_synthetic_capital_authority.py
python -m pytest -q
```

Require final-head CI green on Python 3.11, 3.12, 3.13 before
declaring this offline coding stage verified. **CI is not proof
of a globally enforceable capital risk authority.**

## Governance and further work

PR #44 and prior stages are draft/unmerged. Stage53 must also remain
draft and unmerged until explicit owner review and prospective
merged-tree integration audit. Stage46 identified two
independent PR roots and calibration overlaps; owner must reconcile
those before any merge. Branch rulesets and security review remain
unverified and may be insufficient.

The next safe incremental work should bridge the single-DB capital
authority to an **isolated read-only comparison** of both existing
books, then design explicit reserve/commit/release and recovery.
Do not quietly connect it to live broker trading, approve releases,
reset holds, merge a PR or present a completed real-money system.
