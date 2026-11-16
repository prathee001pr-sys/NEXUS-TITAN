# NEXUS TITAN — Crypto/Recovery Candidate, Resumed Integrated Acceptance

Original Work/preflight candidate from 2026-11-15 has been preserved, not rewritten. Exact Stage97, Stage98, market state, consensus, risk and recovery source interfaces were separately checked against GitHub's stable-baseline branch.

## Built in this continuation

- Original research preflight and bounded recovery runner retained.
- **New strictly typed synthetic BTC-USDT spot research gate** validates independent specialist evidence, finite/correlated OHLC price in integer quote cents, timestamps, provenance, real Stage97 account replay, cash/exposure/kill/loss limits and microcoin quantities. It is read-only and never signs a permit.
- **New real-component integration tests** prove typed research → consensus → separate test-only exact-intent signed permit → Stage97 atomic synthetic buy, partial sell, closed trade, restart and cross-market read-only review. Negative paths include stale/missing/wrong risk evidence, tampering, price mismatches, lack of explicit local paper approval and kill.
- **Test cleanup-only fixes** close two sqlite3 connections that otherwise raised `ResourceWarning` with Python 3.13 strict warnings; no production risk policy altered.
- **Five real repeated recovery runs** passed (38 tests each). This does not close recovery #131 or certify production recovery.

### Validation

See `docs/CRYPTO_STAGE97_REAL_INTEGRATION_RECEIPT_2026-11-15.md` for exact counts, source provenance, limitations and outstanding acceptance gates. Python 3.13.5 strict focused **156 passed**; reconstructed broad 4,881 passed plus five subtests before five extra integrated checks; later new checks passed focused. GitHub CI remains to be run after feature-branch publication.

### Restrictions

No automatic authority, no live trading, no risk permission changes, no API-published commit (email privacy), no `main` merge and no deployed PWA changes. A synthetic receipt or local QA HMAC test permit is not authenticated human consent or exchange market evidence.
