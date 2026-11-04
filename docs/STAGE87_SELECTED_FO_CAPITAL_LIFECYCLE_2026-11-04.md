# Stage 87: one authoritative capital/order lifecycle in the selected environment

`SyntheticFOExecutionGateway` is a stateless adapter over the existing, risk-enforced Stage55 book. It creates no second balance, coordinator ledger or in-memory active-order authority. Every permitted OPEN/FILL and deny-only CANCEL updates the same SQLite cash, reservation, order journal and risk-proof tables. An unprotected legacy book cannot be supplied to this adapter.

The account enforces gross committed capital = paid premium + paid fees + outstanding holds, as well as conservative per-underlying limits. Filled orders no longer free their already-paid capital for another full allocation. The exact reviewed instrument allocation also bounds the sum of filled units plus pending units across request IDs. Cancelling an unfilled order releases its allocation; cancelling a partially filled order retains its filled units and costs. A new full-lot request cannot reuse that filled allocation. Configuration is immutable: replenishing/refreshing a spent research allocation requires a future explicitly reviewed migration, not an automatic reset.

Partial fills use actual integer-cent prices and costs, release limit-price improvement, and retain the unspent fee buffer only while units remain pending. Final fills and cancels release unused fees. Per-order paid-notional/fee fields in coherent snapshots reconcile exactly to the same account totals. No second debit is applied to another virtual ledger.

## Idempotency and recovery

For selected books, an exact retry of a committed operation ID returns the current coherent account/order acknowledgement with `replayed=True`; it adds no event, proof or capital hold and grants no new permit. Different economics under that ID are denied. The kill switch is still checked before OPEN/FILL retry acknowledgement. Legacy unprotected duplicate-request behavior remains unchanged. The Stage86 duplicate test was updated to assert this explicit selected-account improvement rather than rejection.

Nonempty restart now works through the stateless adapter. Opening the same book requires the same pinned boundary and key and verifies all historic signatures and cash/hold replay. Expired historical permits remain audit evidence; new fills require a fresh permit at the current journal/risk head. No pending order becomes approved merely by being recovered. A committed operation whose response was lost can be retried without duplicate accounting.

The write transaction rolls back events, permits, cash and reservations together when a crash is injected before the event or after event/proof insertion but before the head update. Settlement and cancellation interruption preserve the original hold. Concurrency tests cover identical retries, four racing distinct requests, exact-head rejection, explicit fresh-risk retry, quota limits and cash invariants.

## Scope and release limitations

This is the single authoritative account **inside the selected synthetic F&O environment**. Stage19 research, legacy VirtualAccount, Stage49/53 books and crypto are not migrated or made cross-database atomic. Crypto accounting and permissions remain separate and their cash isolation is tested. There is no live broker, authenticated real quote/contract master, actual futures margin settlement, short-option lifecycle, mark-to-market equity, option expiry settlement or sell-to-close path in this selected adapter. Paid premium is a gross committed debit, not realized trading loss or net P&L. Research scenario limits remain synthetic assumptions, not independently measured market risk.

The existing ledger scope includes its canonical path. Moving a funded SQLite file to another path/PC needs an explicit migration procedure; source code remains portable, with no additional runtime dependency. HMAC key custody, host/process isolation, authenticated operator control, genuine data licences and prospective shadow evidence remain release blockers. No global risk/capital or real F&O readiness claim follows from these tests.

Local full-regression results and exact-commit three-version CI are recorded on the draft PR after execution. The stage adds 19 tests, covering the actual adapter and persistent book rather than fabricated intermediate receipt objects.

Final local result: **2,368 passed, 0 failed**, 19 new tests; 5 subtests are separate. Compilation, package dependency/import review, `pip check` and whitespace validation passed. Exact published-commit Python 3.11/3.12/3.13 CI must pass before Stage88 starts.
