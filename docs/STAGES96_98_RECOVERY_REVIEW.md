# NEXUS TITAN Stages 96–98 additive candidate (NO LIVE)

Base must be exact Stage95 commit `f780456ae0db027e9ec31594d07f0656ac420515`; do not apply to the stale main branch or to the unrelated historical Stage89–120 integrated ZIP. These three modules are additive, leave Stage55 and risk/permit code unchanged, and are deliberately brokerless.

- **96:** Read-only reconciliation of selected Indian F&O snapshot and optional exact-head signed synthetic MTM; official drawdown, expectancy and profit factor stay unavailable absent externally validated trade and valuation series. No assumed market prices.
- **97:** Separate one-instrument, long-spot-only *synthetic* BTC-USDT paper book. Own SQLite DB, explicit limits, replay-checked hash chain, signed LOCAL TEST permits, local paper approval, permanent kill, conservative fee/quantity rounding, no exchange adapter/credentials. Local HMAC does not prove human identity, independent market data, or external integrity anchor. Unrealized equity uses an explicitly synthetic mark.
- **98:** Read-only dual-market report requires independently validated INR and USDT snapshots; never combines INR and USDT cash/P&L or shares their ledger, risks or kill.

**Restrictions:** No real exchange order placement, broker live route, realtime data authenticity claim, profit claim, main merge, repository visibility change or force push. The newer Stage97/98 scope differs from the original 4 Nov road map where those IDs covered options expiry and futures margin; the original expiry and margin requirements remain open and unimplemented.

**Known blockers:** Before marking fully complete, test the exact Stage95 checkout against Python 3.11/3.12/3.13, run full regression, independent security scan, credential-safe Git commit, sequential Draft PR/CI. This standalone candidate is not a confirmed full repo integration or successful GitHub deployment. Nothing is permitted to silently upgrade the Stage95 signing authority.
