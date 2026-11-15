# Stage 37 — Opt-in Durable Strict Paper Account

**Scope**: only `VirtualAccount` offline paper simulations; not brokerage or a
security boundary against malicious Python/SQLite administrators.

## Implemented

- `VirtualAccount(..., strict_paper_mode=True)` only when
  `state_dir`, `MANUAL_APPROVAL`, enabled pretrade risk and a configured
  approval callback are supplied.
- Durable SQLite column `strict_paper_mode` is saved at initial account
  creation, **before any orders**, and on every subsequent snapshot. Existing
  mode cannot be downgraded by normal snapshot persistence. Reopening the
  same account without the new argument retains stored strict policy.
- A legacy account that already has a persisted snapshot cannot be silently
  made strict through a constructor flag. Its operator must explicitly call
  `enable_strict_paper_mode()` after passing flat account/manual/risk/auth
  checks; migration rejects active pending orders or inventory.
- Each normal `submit_order`, `approve_order` and `execute_fill` checks
  the local durable strict policy. Normal orders in strict mode require
  manual approval with intact order-hash evidence at fill time. A caller's
  in-memory `strict_paper_mode=False` toggle cannot bypass the saved flag
  through the public APIs.
- All ordinary SELL entries are limited to owned positions; a second
  unfinished SELL for the same symbol is denied. Existing internal
  emergency SELL and emergency square-off remain available.
- Strict policy never allows `AUTO_PAPER` or `LIVE_DISABLED`.
- Legacy synthetic fixtures remain available. This change does **not**
  force them into strict mode.

## Testing and discovered issues

Added 19+ synthetic tests including manual approval, forged order state,
removed/changed approval, SELL inventory, restart, strict-downgrade attempts,
migration preconditions, risk tampering, emergency exits and previous
simulation compatibility. Initial test runs identified a real persistence
defect: freshly created strict accounts were not saved before their first
order. That was fixed; strict mode now writes its initial snapshot
immediately. Legacy migration test also uses a genuinely persisted baseline.

## Security limitations

1. This is opt-in. Legacy account entrypoints still work for research and
   older tests. `PaperIntentGateway` remains a separate opt-in adapter.
2. Per-account Python dictionaries, risk configuration and callback are still
   writable by the process. This is **not** trusted identity, external
   signature verification or a secure broker-side order authorization.
3. Durable account writes currently use last-writer-wins SQLite snapshots
   without a per-account compare-and-swap revision. Multiple processes may
   overwrite each other's work. **Stage38 must address this before any
   multi-process paper validation claim.**
4. `VirtualAccount` and the research options ledger are still separate,
   non-atomic accounts; equality of their IDs means no shared portfolio.
5. Risk calculations depend on caller-provided prices, exposures and market
   data. No genuine F&O vendor depth, one-minute contract history, licence
   verification or broker fills are proven.
6. No automatic strategy promotion and no real-money trading.

**Release verdict: offline research-only, not production-ready.**
