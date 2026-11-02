# Stage 40 — One-way Gateway-only Paper Account Mode

**Scope:** Isolated offline simulation, opt-in. No broker adapter, data-provider
calls, live order authorization or strategy promotion.

## Problem found in Stage 39

Stage37 strict mode correctly required manual approval and risk validation,
but it still allowed direct `VirtualAccount.submit_order()` by authorized
application code without Stage33's guarded-ledger preflight. The Stage33
`PaperIntentGateway` was strictly optional, so code could bypass
research-ledger checks even when the intended paper-deployment policy
was to use that gateway.

## Implementation

- Add persistent SQLite `account_state.gateway_only_mode` with migration
  defaulting to **OFF**, preserving existing development/backtest fixtures.
- Explicit opt-in `virtual.enable_gateway_only_mode(guarded_research_ledger)`
  requires Stage37 durable **strict paper** mode, manual approval/risk/auth
  callback, an entirely flat virtual account and a healthy Stage28 guarded
  research ledger with the **same account ID**.
- The guard is **one-way**: SQLite snapshot saves refuse to change a persisted
  gateway-only account back to legacy mode, even with a stale local flag.
- An opted-in account's normal `virtual.submit_order(...)` rejects direct
  order submissions. Stage33 gateway uses
  `virtual._submit_guarded_paper_intent(research,...)`; that in-process
  adapter repeats explicit PAPER_TRADE permission, research ledger integrity,
  virtual reconciliation, account match, kill lock and BUY flat preflight.
- For owned SELL-to-close, gateway delegates to the same adapter, while
  Stage37's no-naked-SELL and duplicate-pending-SELL controls still apply.
- Approved pending orders still need the existing human approval callback
  before a simulated fill. Emergency/internal protective SELL exits
  do **not** depend on the normal submission path.
- Persistent policy survives SQLite restart and Stage38 CAS revision
  protections remain active. Legacy accounts remain untouched.

## Security boundary and limitations

- This is an **application-level software guard**, not an unbypassable,
  independently authenticated security boundary. Anyone able to modify
  Python runtime state, call the private adapter, replace local code, or
  tamper with SQLite can still circumvent local checks.
- Existing VirtualAccount legacy accounts and Stage19 direct research
  ledger APIs remain separate. Other entrypoints have not been globally
  migrated. Gateway-only is **explicitly opt-in**.
- There is no single atomic cash/risk book across VirtualAccount and the
  research option ledger. A preflight reads two different SQLite databases
  and does not provide cross-ledger transactional isolation.
- An approval callback is **configured**, not an external signed human
  authentication challenge. This is not suitable for autonomous live
  trading or security-critical account permissions.
- Exchange-quality historical F&O quotes, liquidity depth, slippage,
  fees and point-in-time contract data remain unverified.
- All current tests use synthetic offline inputs. No live data downloads,
  broker orders, real money or automatic promotion.

**Release verdict: development-stage research safety only.**
