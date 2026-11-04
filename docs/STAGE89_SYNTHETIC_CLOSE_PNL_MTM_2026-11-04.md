# Stage 89: synthetic long-option close, P&L and MTM

Stage89 extends the Stage86–88 selected Stage55 SQLite account. It does not introduce another trading engine, balance, position store or P&L ledger. Every economic value below is derived from the existing event journal and its signed risk-proof table. No live broker, real order, short position or EVOLVE permission change is introduced.

## Verified starting point and compatibility

GitHub PR #81 and the Stage88 branch were rechecked at `5ff1f434913700beb5a0d4bc236e33061e0fd271`, tree `2c575df2b663a5714655f2578e009b4538377d4d`. The local source tree matched. Direct-head CI run `41844909216` passed Python 3.11/3.12/3.13. The unmodified local suite reran with **2,390 passed, 0 failed**, with five pre-existing subtests counted separately.

Existing OPEN/FILL/CANCEL event serialization, Stage86 entry permit format, boundary digest, account scope, entry risk limits and one-way kill behavior are retained. Known selected-account v1 event tables are upgraded to allow a `CLOSE` kind in the same SQLite transaction **after** their head, journal and proofs are verified. Original rows/hashes remain unchanged. A crash rolls back the schema change. Unknown columns, custom indexes or triggers fail closed for a separately reviewed migration; they are never silently discarded.

## SELL-to-close contract

`SyntheticCloseRequest` is explicitly `SELL_TO_CLOSE`; it cannot express a short entry. A close identifies its original entry order and the full pinned contract identity: underlying, display symbol, CE/PE side, strike, expiry, lot, tick and research binding. The ledger independently rejects unknown positions, wrong contracts, excess quantity and invalid economics, including a faulty control plane that signs an invalid request.

Partial closes use whole contract lots. A complete residual close may consume all remaining odd units left by partial entry fills; this exception can only reduce the entire existing residual. Pending BUY remainders for that contract must first be cancelled. There is no implicit netting across entry orders and no new close order that may later create a short position.

Execution is at the exact signed synthetic bid. Bid/ask must be positive, ordered and tick-aligned; quantity and all money are bounded integers. Actual exit fees cannot exceed the signed estimate, and that estimate cannot exceed gross proceeds. Zero-price and expired-option settlement, optimistic improvements and modeled exit slippage are outside Stage89.

## Separate conservative authorization

The existing privileged local synthetic issuer adds two domain-separated HMAC types: signed option quotes and reduce-only close authorizations. A quote alone grants no mutation authority. A close authorization binds the request, quote, account scope, boundary, journal revision/tip, risk revision and short validity window. The ledger verifies signature, full contract, current holdings, fresh quote, expiry, exact bid and fee bounds under the **same `BEGIN IMMEDIATE` lock** as the mutation.

OPEN/FILL still require the original Stage86 risk permit; a close authorization cannot substitute for it, and an entry permit cannot authorize a close. A local realized-session-loss veto additionally uses the unchanged policy daily-loss threshold as a conservative session ceiling. This is not a calendar-aware daily reset, and signed entry telemetry remains mandatory. Positive close proceeds do not replenish the original research allocation or its lifetime filled-unit quota.

The kill switch continues to deny exposure-increasing OPEN/FILL. CANCEL and a fresh authenticated reduce-only CLOSE are allowed while stopped. Pre-stop close evidence becomes stale when the risk revision changes and must be reissued. Legacy rearm remains blocked. Closing may use a fresh quote after the original entry research becomes stale; this does not refresh entry permission.

Exact committed retries require the original, cryptographically valid close authorization and identical economics. They return `replayed=True` with the original allocation breakdown and current coherent account state, without adding proceeds/events. An expired authorization can acknowledge its already-committed operation only; it cannot perform another close. Missing/changed authorization, changed economics, or uncommitted stale evidence is denied.

HMAC authenticates possession of the existing local synthetic issuer key. It does **not** authenticate a human, independent deployed risk service, real exchange quote or secure process boundary. Same-process verifier-key custody and trusted replay clock remain deployment limitations. EVOLVE receives no key or authorization capability.

## Integer-cent cost method and invariants

The method is moving weighted-average cost pools **per entry order**. Each entry fill adds actual premium and entry fees to the remaining pools. For `q` closing units out of `h` held units:

```
allocated entry premium = remaining premium * q // h
allocated entry fees    = remaining entry fees * q // h
exit proceeds           = q * signed bid
gross realized P&L      = proceeds - allocated entry premium
net realized P&L        = gross P&L - allocated entry fees - exit fees
```

Allocations round down using integer division. The final close consumes every remaining cent. Previously allocated costs are never reused. No floating-point average is stored. Entry premium is open cost basis until closed; it is not a realized trading loss.

Example tested through actual module calls: 25 units filled at 545 with fee 5, then 25 at 550 with fee 8. Pools are premium 27,375 and fees 13. A 25-unit close at 600 with fee 7 allocates premium 13,687 and entry fees 6: gross profit 1,313, net profit 1,300, remaining basis 13,688 + 7. Closing the remainder at 500 with fee 3 realizes net -1,198. The full position's net is +102, with gross +125 and total fees 23. These are fabricated integer-cent engineering amounts, not genuine NSE prices, charges or returns.

Replay checks, after every event:

```
initial cash + gross exit proceeds = cash + paid entry premium + all paid fees
cash + remaining open cost basis  = initial cash + realized net P&L
available cash                    = cash - reserved cash
filled units                      = closed units + held units
entry costs                       = allocated costs + remaining costs
```

Cash may exceed its starting balance after a valid profitable close, while the existing allocation limits remain unchanged. Risk proofs and CLOSE events commit atomically with the head; no P&L cache is authoritative. Recomputed unkeyed event/head hashes cannot make altered economics pass the signed evidence binding.

## Read-only MTM and performance

`mark_to_market` accepts complete, synchronized, signed synthetic quotes for every open entry position. It rejects missing/extra/duplicate positions, wrong contracts/quantities, invalid or altered signatures, future/stale times and quotes predating the relevant fill. Quotes remain labelled synthetic and unverified as market evidence.

The report includes per-position held quantity, remaining cost basis, reference bid, market value, unrealized gross/net P&L and estimated exit cost. Portfolio totals include realized net P&L, available cash, reserved capital and gross held-position market exposure. Conservative net-liquidation equity is:

```
cash + held market value - estimated exit costs
= initial cash + realized net P&L + unrealized net P&L
```

Reservations are already part of cash and are **not subtracted again** from total equity. No MTM call writes an economic journal event, changes cash or realizes P&L. Reports carry their exact ledger revision/tip and valuation time.

Performance reports expose gross/net realized P&L, open unrealized net P&L when marked, all actual simulated fees, available/reserved cash, remaining basis and current synthetic equity. A closed trade is a fully closed original entry position, not each partial close; win/loss/breakeven use its cumulative net P&L. Without complete open-position quotes, unrealized P&L/equity remain unavailable. Profit factor, expectancy and drawdown remain unavailable until a reviewed lifecycle/valuation-history eligibility protocol exists. No invented values or permanent MTM equity curve are added.

## QA and remaining limits

Final local full regression: **2,446 passed, 0 failed**, including **56 new Stage89 cases**; five existing subtests remain separate. Compilation, package import/dependency audit (154 modules / 272 internal edges), `pip check` and whitespace checks passed. Exact published-head Python 3.11/3.12/3.13 CI is verified after publication and included in the completion report.

Coverage includes CE/PE closes on both NIFTY and BANKNIFTY, partial/full/residual closes, over-close, unknown/cross-contract positions, lots/ticks/fee/rounding, entry/exit cost conservation, MTM price changes, stale/corrupt/unauthenticated evidence, kill behavior, signature-domain separation, concurrent requests, exact retries, restart, transaction rollback, actual process death before commit and after committed lost responses, journal corruption and atomic v1 migration. The two initial focused-test failures were a helper lookup for an unknown ID and an incorrect expected fee arithmetic value; both were corrected and the complete suite passed. No failed regression remains.

Real F&O shadow deployment remains **NO-GO**. Genuine licensed data/depth/contracts/fees, independent signer/operator/process security, prospective validation, cross-ledger authority, calendar-aware risk state, governed allocation refresh, external rollback checkpoints and operational deployment remain unresolved. Futures/short options, actual brokers/live orders, expiry/zero-price settlement and global ledger migration are unsupported here. POSIX abrupt-death tests are skipped on hosts without fork; runtime code and injected rollback tests remain portable.

Stage90 has not been started. A suggested next review is signed valuation-history provenance and eligibility rules for performance metrics, together with proper calendar-aware realized-risk state; its scope requires the user's next instruction.
