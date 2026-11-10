# Stage 101 — Strict one-session synthetic NIFTY/BANKNIFTY 1-minute bar preflight

**Status:** additive offline candidate; NO LIVE. Stacked on successful Stage100.

- Accepts explicit list/tuple of **1–375** immutable, synthetic NIFTY/BANKNIFTY OHLCV bars only, fixed-point positive INR paise prices and non-negative integer volume.
- Rejects NaN/fractional/bool prices, crossed OHLC, duplicate/missing/out-of-order 1-minute bars, different underlyings/sessions, timezone other than explicit IST, noncanonical minute ticks and weekend/outside 09:15–15:29 bounds.
- Returns a deterministic SHA-256 input digest, counts, session bounds and **only** synthetic structural checks. An exchange holiday calendar, real feed authenticity, proper licensed vendor coverage and 15-year 1-minute history are explicitly **not independently verified**.
- Market data never grants trading authority, promotes a strategy or changes the ledger.

**Test gate:** bounded focused suite with `-W error`, exact full regression, 3-version GitHub CI + Secret Scan. No main merge.
