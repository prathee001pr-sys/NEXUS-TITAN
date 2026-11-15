# Stage 71 — F&O point-in-time futures/options alignment (research NO-GO)

Date: 2026-11-04. Base: **Stage70 draft PR #62**. Research-only. No change to \`main\`.

## Implemented

- New pure/read-only \`stage71_fo_asof_alignment.py\` joins Stage59 **bounded verified-structure futures CSV** outputs with Stage44 **bounded verified-structure options catalog** outputs.
- **Look-ahead prevention for the joined feature:** each option-chain snapshot can reference only the most recent futures bar whose **open + full candle interval is at or before the option observation**. A just-opened/incomplete bar is NEVER treated as a completed close. Same India market date is mandatory.
- Fail-closed on NIFTY/BANKNIFTY underlying mismatch; out-of-order/duplicate option snapshots; futures/source-count mismatch; stale candle; bad hashes; invalid input limits; forged external authorization flags. No partial aligned dataset returned on failed QA.
- Explicit source digests, option snapshot dates, option quote count, futures bar open/close and lag for each paired observation; deterministic SHA-256 evidence label.
- Synthetic two-underlying tests using **actual Stage59 and Stage44 local CSV preflights** and adversarial lookahead/mismatch/stale/authority/lag tests.
- CI matrix 3.11, 3.12, 3.13 runs Stage71 conservative no-input smoke. Full test runner exercises the new synthetic fixture tests.

## Limits (critical)

**Not** licensed NSE real market data. Source licences, contract master, calendars, order book and vendor identity remain unauthenticated operator declarations. Option chains and futures candles may originate from different vendors or synchronized clocks; Stage71 cannot prove those are independent or real. Stage59 and Stage44 outputs are ordinary typed Python data, **not tamper-proof attestations**. A hash of declared source bytes is not a digital signature. No trading model training, Greeks calibration, complete market-window coverage, exchange tick depth, backtest returns, fill/P&L, paper/live order, strategy promotion or independent risk approval is provided. Cross-source as-of alignment controls **one look-ahead pathway**, not every source of feature or label leakage.

## Remaining P0

Integrated main-root reconciliation and protected-branch review; independent source/vendor/licence/contract/calendar validation; verified historical F&O full-chain coverage; separate spot/futures/options clock and effective-dated instrument checks; global mandatory Risk & Veto; atomic capital/position books; signed prospective real-feed shadow outcomes; owner approval. No automatic activation or live order.

**Release verdict: NO-GO.** Stage72 should build Greeks/expiry/IV intelligence on top of validated, completed observations with audit and no lookahead.
