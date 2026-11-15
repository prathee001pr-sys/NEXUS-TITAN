# NEXUS TITAN Stage105 — Conservative synthetic F&O execution-cost preview (NO LIVE)

**Parent:** Green Stage104 feature branch. Additive, non-executable, fixed-point paise-only options spread/slippage/partial-fill research.

- Requires exact immutable Stage104 catalog, Stage101 window, Stage102 option-chain report and original bounded synthetic quotes. **Replays** the exact Stage102 structural validation and checks full report equality, including chain SHA-256.
- Requires a typed paper *intent*, not a signed trade order or authorization. Models BID on sell, ASK on buy, adverse-only slippage, visible synthetic volume participation, round-down lots and explicit unfilled quantity; estimated fees are *user-supplied synthetic assumptions*, not statutory charges or verified broker data.
- Conservative integer arithmetic, bounded quantities/turnover/fee, lot alignment, no opportunity to fill an absent contract, no quote timestamp drift accepted, no negative execution price. Reports **never** claim executable liquidity, actual fills, verified statutory fees, profit or trade authority.
- Does not call Stage55 book operations, modify cash/collateral/positions, touch real broker/exchange, or sum INR and USDT.

**Acceptance gate:** Focused -W error and full exact-checkout pytest, privacy-safe commit, stacked Draft PR, 3-Python CI and Secret Scan. Real slippage distributions and historical limit-order fills remain unverified.
