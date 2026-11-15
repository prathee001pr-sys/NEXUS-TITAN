# Stage38 — Durable Account Compare-and-Swap, Stale Writer Recovery

**Scope**: SQLite-backed `VirtualAccount` offline paper simulations.
No brokers, live trades, or independently authenticated external ledgers.

## Important defect

Before Stage38, two `VirtualAccount` instances could restore the same account
snapshot, then both write complete account state via SQLite
`INSERT OR REPLACE`. The later writer could overwrite newer orders, cash,
positions and approval evidence without an explicit conflict: a classic
**last-writer-wins lost-update** problem. SQLite commit atomicity alone
was not enough to protect semantic multi-process account state.

## Changes

- Added account_state `revision INTEGER NOT NULL DEFAULT 0` with migration
  for previously created SQLite tables.
- Every snapshot write validates `expected_revision` under the *same*
  `BEGIN IMMEDIATE` SQLite write transaction, increments revision and
  returns the committed version. On version mismatch, the transaction
  **rolls back** with `StaleAccountSnapshotError`.
- VirtualAccount caches the loaded generation, checks it before routine
  order, approval, fill, capital, cancellation, mark, stop/kill or emergency
  square-off entrypoints, and passes expected generation on all writes.
- After a stale write or generation mismatch, that process-local account
  object is considered unusable until the operator creates a fresh account
  handle and re-reads its latest durable state.
- Two different account IDs have independent revision counters.
- Stage37 durable strict policy remains non-downgradable and the new
  account revision is never treated as a broker-side approval.
- New synthetic tests cover stale writers, DB-level CAS, two concurrent
  handles, stale emergency exit denial and clean re-open/recovery.

## Known limitations — NOT production-ready

- Optimistic CAS prevents **stale concurrent snapshot overwrites**, but
  it is not an externally enforced queue, per-order distributed mutex,
  broker-backed ledger, authentication layer or malicious code defense.
- An account method may alter its in-memory state before a later
  concurrent write fails; the handle is invalidated and **must be
  discarded**, never trusted for further accounting decisions.
- Emergency square-off from a stale handle is denied until recovery; this
  favors preventing phantom positions or wrong-symbol closes. A real broker
  emergency path would need separate protected credentials and reconciliation.
- Tampering directly with SQLite can still bypass or corrupt local state.
  No signed external audit or independent history of balance reconciliation.
- Stage19 research ledger and VirtualAccount remain separate independent
  accounts, regardless of their human-readable account IDs.
- Real F&O data provenance, timestamps, microstructure and actual fills
  remain unverified and have intentionally been deferred for later.
- No real broker orders or automatic strategy promotion.

**Release verdict: offline research-only.**
