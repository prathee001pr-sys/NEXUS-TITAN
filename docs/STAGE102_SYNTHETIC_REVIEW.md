# Stage 102 — Synthetic CE/PE paired option-chain preflight

**Status:** additive offline candidate; stacked on Stage101; NO LIVE.

- Consumes the typed Stage101 checked synthetic minute window and a bounded explicit 2–100 row synthetic NIFTY/BANKNIFTY CE/PE option-chain snapshot.
- Validates unique strike/type/expiry contract IDs, all CE/PE pairs per strike, same lot size per strike, quote age <= configured 30 seconds, common IST as-of, non-expired relative to synthetic date, un-crossed bounded prices, <=50% synthetic spread, positive OI and correct INR/source identity.
- Detects duplicates, mismatched contract/expiry, missing paired sides, stale/future/mixed-time quotes, invalid lot sizes and unexpected market currencies.
- Returns only structure, SHA-256 and pairing counts. **Does not** verify actual NSE option chain, official expiry calendar, IV/Greeks, real liquidity, margin, real-market performance or broker authorization.

**Test gate:** focused and full regression, Python 3.11/3.12/3.13 CI + Secret Scan; stacked draft PR only.
