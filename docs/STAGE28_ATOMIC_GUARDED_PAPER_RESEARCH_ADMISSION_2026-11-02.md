# Stage 28 — Atomic Guarded Paper Research Admission (Risk & Veto)

**Scope:** Isolated Stage19 durable SQLite research ledger + Stage23 BUY-only
historical-options paper simulation, **not** a broker router, system-wide
permission enforcement, real shadow account or production Risk OS.

## Problem

Prior Stage23 `guarded_options_research_buy()` evaluated paper permission,
AuthoritativeRiskEngine, exact-contract portfolio risk and Red-Team **before**
calling Stage19 `ledger.reserve_buy()`. But legacy `reserve_buy()` could be
called directly and the risk evaluation was separated from the cash reserve by
another transaction. Direct legacy research callers remain intentionally valid
for old synthetic/backtest experiments; they are **not** approved trading
entrypoints.

## What changed

- Stage19 `DurableResearchShadowLedger(..., guarded_paper_mode=True)` creates
  a new **guarded** account. An existing legacy account must be empty and
  explicitly migrated with `enable_guarded_paper_mode()`. Open reservations
  or inventory prevent migration; it does not change the old account silently.
- SQLite `account_safety` mode is **persistent, per-account and included
  in state hash-chain evidence**. Reopening without the constructor flag does
  not downgrade an already guarded account. Destroying or editing safety
  metadata without corresponding audit updates is rejected by the ledger's
  integrity check.
- `reserve_buy()` on a guarded account **fails closed**.
- Stage23 `guarded_options_research_buy()` detects guarded mode and calls
  `reserve_buy_guarded(..., GuardedBuyAdmission(...))`.
- The protected method inside the same SQLite `BEGIN IMMEDIATE` recomputes
  `Action.PAPER_TRADE` permission, authoritative sizing, exact-contract
  sizing and independent Red-Team spread/liquidity veto using **currently
  unreserved account cash**. It also checks flat inventory, no other OPEN
  reservations, order contract/lot/freeze/tick and fee/cash limits. On failure,
  the entire SQLite transaction rolls back.
- Two separate handles to the same guarded account cannot both reserve
  against the same flat account; only one guarded BUY may be pending, a
  deliberately conservative research-only limitation.
- Historical offline Stage19 users continue using legacy mode, retaining
  backwards compatibility and their existing test fixtures.

## Example

```python
# Synthetic research only, not broker execution.
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
ledger = DurableResearchShadowLedger(
    "research_only.sqlite3",
    account_id="OFFLINE-PAPER-EXPERIMENT",
    starting_capital=50000,  # configurable synthetic balance
    guarded_paper_mode=True,
)
# ledger.reserve_buy(...)     -> DENIED
# guarded_options_research_buy(ledger=ledger, paper_trading_enabled=True,
#   ... previously vetted option-chain history, contract, depth & parameters)
# -> rechecks permission/risk/veto inside ledger SQLite transaction.
```

Do not place vendor market data, credentials or real broker account information
in the repository. A prior nonempty ledger cannot be automatically upgraded.

## Security and data limitations (BLOCKING)

1. **These are research-only checks.** The caller provides simulated
   option quotes, depth, daily-loss/drawdown counters and risk inputs.
   The ledger does **not independently authenticate their source or
   owner-level permissions** and is not sufficient to bind live orders.
2. A Python application and its own writable SQLite file are not resistant
   to a malicious administrator or an attacker who can modify code or
   recompute audit hashes. Cryptographically signed external approval,
   least-privilege broker credentials, controlled identity and secure
   configuration management remain unimplemented.
3. Legacy research API remains intentionally supported for compatibility,
   and other pathways (`VirtualAccount`, Stage24 long SELL, raw simulator,
   other adapters) are **not universally forced** through this new guarded
   account policy. Never describe this stage as a fully unbypassable
   *global* order router.
4. The preflight still assumes synthetic/unverified timestamped historical
   chain/depth and operator-declared point-in-time metadata. It does not
   prove genuine exchange fills, live margin, actual bid/ask liquidity,
   regulatory/statutory fee accuracy, external account reconciliation,
   data licencing or positive trading returns.
5. The independent `Action.LIVE_TRADE` permission is unchanged and
   **never enabled**. No broker account adapter or order transmitter exists
   in this stage. Strategy promotion remains denied.
6. SELL-to-close continues through Stage24 independent research logic and
   requires its own permission; its atomic global integration is pending.

## Remaining work

- Build and review a **single brokerless paper-account admission routing
  boundary** and move every real shadow order action (including exits and
  emergency close) through it; disallow legacy API in that deployment mode.
- Make risk status authoritative across asynchronous/restarting components,
  enforce kill-switch permissions and fail closed on stale account snapshots.
- Tie order intent, identity, market-data evidence, risk config version,
  monotone timestamp and one-shot authorization to an immutable audited
  decision receipt; require concurrency/replay/restart tests.
- Inspect real licensed historical options/futures data when available;
  perform 1-minute gaps/point-in-time metadata checks and realistic
  validation; keep all real-money controls disabled.

**Release verdict: RESEARCH-ONLY / NOT PRODUCTION-READY**.
Complete source tests and Stage25 synthetic end-to-end research audit continue
running in GitHub Actions Python 3.11 / 3.12 / 3.13.
