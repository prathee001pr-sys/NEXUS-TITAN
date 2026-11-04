# Stage74 — F&O long-option stress scenario lab (NO-LIVE)

Date: 2026-11-04. Draft branch stacked on Stage73 PR #65. **Not merged to main.**

## Actual implementation
- A bounded, deterministic **offline long CE/PE scenario lab** consuming Stage72 (unverified research-only) model/IV results and explicitly supplied matching NSE NIFTY/BANKNIFTY PointInTimeContractSpec.
- Reuses the existing Stage72 unrounded Black–Scholes–Merton research pricing function (European-style BSM) and the existing Indian cost engine for indicative *hypothetical* options buy/sell charges. No legacy simulation or risk modules replaced.
- Model reference spot is operator supplied but must reproduce the earlier Stage72 IV midpoint within a strict tolerance. Contract/expiry, instrument, F&O lot/freeze size, source hash format, quote midpoint, research-only authority defaults and cost tariff values are checked.
- Cases cover upside/downside underlying jumps, IV regime shifts, intraday time decay, widened hypothetical spreads and liquidity/slippage haircuts. Both positive and negative movements are stress *assumptions*, **not forecasts or calibrated probabilities**.
- Near-expiry cases (60 minutes or less remaining by default) and cross-session cases fail closed, since model parameters/settlement/microstructure cannot support reliable output.
- Indicative entry debit / model mark / hypothetical friction-adjusted exit proxy / hypothetical round-trip net are returned **only** as scenario algebra, with explicit no real order-book, no historical fills, no market P&L, no margin verification and no strategy promotion assertions.
- Includes adversarial synthetic tests for NIFTY/BANKNIFTY, CE/PE, invalid tariffs, forged authorization claims, mismatched spot/contract/strike, expired/near expiry, duplicated/extreme cases, spread uncertainty, and no-data CLI/CI smoke across Python 3.11, 3.12, and 3.13.

## What Stage74 does NOT prove
- No licensed or authenticated real NSE data, timestamp-signed quotes, complete order-book depth, broker orders/fills, regulatory settlement pricing, verified fee version, exercised options/STT treatment, actual portfolio or capital constraints.
- Its \`hypothetical_exit_price_after_friction\` is *invented as part of an explicit user-declared scenario*, **NOT an observed or tradable bid**. A liquidity haircut does not create executable depth. Positive hypothetical net cashflow is NOT a trading strategy's expected return or prediction.
- Repricing a synthetic spot under BSM is not calibrated to real smile/surface, futures basis, realistic volatility term structure, exchange matching, gamma-hedging, pin risk or market impact. Greeks are local model assumptions and particularly unreliable near expiry.
- No future leakage verification for all candidate features; Stage71 addresses only one point-in-time alignment pathway. No real shadow trials, empirical scenario probabilities, tail-risk attribution, champion/challenger deployment, autonomous self-learning updates or real wealth effects.
- Hashes are local labels on operator-declared evidence and **not digital signatures**.

## Unresolved P0 before any release
1. Reconcile the long-running stacked GitHub PR graph; protect main with owner-controlled reviews and passing CI; no force merges.
2. Prove global mandatory independent Risk & Veto + atomic capital/position authority across legacy entrypoints, with non-bypassability tests.
3. Validate official point-in-time F&O contracts, vendor identity/data licensing and exchange sessions against real history.
4. Provide independently verified quotes, realistic depth/fee/margin/settlement stress and prospectively signed shadow evidence before model promotion.
5. Explicit owner permission for any future live capability; **not requested or granted by this stage**.

**Stage74 result: research NO-GO** despite green unit tests. No broker, no orders, no money movement. Stage75 should address bounded integrated offline shadow-readiness and aggregate risk/scorecard audit, not declare production complete.
