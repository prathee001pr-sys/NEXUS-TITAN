# Stage77 — Brokerless F&O synthetic gateway foundation (RESEARCH ONLY / NO-GO)

2026-11-04. Stacked on Stage76 draft PR #68; \`main\` is unchanged. Long CE/PE NIFTY/BANKNIFTY research only, no external broker access.

## What is actually implemented
- A local in-process \`Stage77BrokerlessFOSyntheticGateway\` wrapper that re-evaluates Stage76's **operator-declared** risk policy and telemetry at each simulated reservation and fill; the constructor requires an **empty** Stage55 single SQLite book with a matching capital/account scope and stricter-or-equal reserve caps.
- Accepts an exact Stage75 research packet reference and a bounded synthetic long-option quantity/lot/price/fee declaration whose sum equals the Stage75 research-only debit. Stage55 performs the actual **single-database** atomic hold, partial synthetic fill, cancellation and cent-exact cash conservation. Stage77 never creates or transmits a broker order.
- Duplicate order IDs and fill operation IDs are rejected by the local Stage55 journal; corrupt/replayed SQLite state fails closed. Cancellation of an in-process synthetic order is permitted even when research risk telemetry switches to kill/ill-health so that **local** funds can be released.
- Restart with a **nonempty** book is deliberately refused: pending orders are not automatically adopted, since Stage77's intent-to-packet binding is in RAM and cannot be independently recovered. A separate audited recovery workflow is necessary.
- Synthetic tests include NIFTY CE lot/debit validation, partial/full fill and fee conservation, risk recheck, kill-switch, simulated cancel, duplicate/replay, policy drift, damaged DB state and restart fail-closed.
- Separate no-input, no-broker CI smoke on Python 3.11, 3.12 and 3.13.

## Crucial architectural limitations
- This is **NOT** a mandatory global F&O risk gateway. Raw \`VirtualAccount.submit_order\`, \`approve_order\`, \`execute_fill\`, Stage33 \`PaperIntentGateway\`, crypto virtual trading and Stage53/55 direct methods are still separately callable. There is no actual code-path fence, no broker credential custody and no evidence of global non-bypassability.
- Stage76 risk checks and Stage55 SQLite writes happen **sequentially**, not within one authenticated risk-and-capital transaction. Caller-supplied Stage75 packets, Stage76 pulses, lot sizes, quotes and source hashes can be forged. Holding a synthetic book's cash does **not** reserve other virtual books' capital or prevent a concurrent risk-policy change. Opening another independent Stage55 SQLite book cannot be ruled out.
- No real market source, order-book depth, official contract expiry/lot metadata, live quotes, trade matching, exchange charges, margin, signed human authentication or audited model promotion. Fills exist only in a private fake-money ledger.
- Stage55 can still be called directly by code with a Python reference to the isolated book, bypassing Stage77. Python class privacy does not constitute a security boundary.
- At-the-spot lost research context cannot be recovered automatically; no resume/square-off promise. Direct Stage55 journal integrity cannot detect malicious full-chain rewrite. No real F&O positions/Greeks P&L or broker reconciliation.
- A local risk pass is permission to mutate a **test-only book**, not permission to run even real-feed paper trading. All receipt authority fields remain false and verdict stays \`STAGE77_LOCAL_SYNTHETIC_LEDGER_ONLY_NO_GO\`.

## Next P0
- Resolve stacked draft PR and main-root histories with explicit owner-reviewed merge-candidate CI; protect \`main\`.
- Design and test **one** independently enforceable risk/capital authority with mandatory single-entry routing, signed identity and authenticated quote/risk/cash state. Close every legacy order/fill bypass; add concurrent writers/kill-switch race and durable recovery tests.
- Verify licensed point-in-time NSE F&O datasets, contract/expiry/holiday metadata, actual fees/depth/margin, and supervised signed prospective shadow trials.
- Explicit owner approval required for any future paper/live deployment or strategy promotion.

**Release: NO-GO. Main untouched. Zero broker orders.**
