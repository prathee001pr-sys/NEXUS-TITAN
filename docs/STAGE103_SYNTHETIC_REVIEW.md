# Stage 103 — Cross-stage synthetic research assurance and no-live authority gate

**Status:** additive read-only candidate; stacked on Stage102; NO LIVE.

- Requires exact frozen report types from Stage100, Stage101, Stage102 and existing Stage98 `DualMarketReview`.
- Cross-checks Indian F&O account ID, journal head + revision, cash, basis and realized accounting against the Stage98 Indian portion, as well as independently conserved isolated USDT crypto capital and hash chain head.
- Binds NIFTY/BANKNIFTY historical-source digest, same-underlying/expiry CE/PE scenario, paired chain source digest, IST quote freshness and immutable audit fingerprint.
- Rejects live flags, claimed official option chain, fabricated source authenticity, mismatched journal/account/market/currency, combined INR+USDT balances, missing or stale synthetic timestamps, malformed digests and false margin/expiry release claims.
- Returns a deterministic **synthetic research fingerprint**, not a digital signature or off-host attestation. Never approves orders, toggles risk permissions, enables trading or combines INR with USDT.

**Test gate:** strict focused suite, full exact Stage99-based regression, three-version CI and Secret Scan; only a stacked draft PR and explicit owner approval before any merge.
