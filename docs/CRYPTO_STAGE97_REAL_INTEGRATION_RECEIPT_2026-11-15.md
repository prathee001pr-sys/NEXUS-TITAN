# NEXUS TITAN — Stage97 Actual Crypto Research Precheck Integration / Recovery Receipt

**Review date:** 2026-11-15 · **Exact GitHub baseline:** PR #133 head `1994d8cd4822a4d45d8c4f6760fdb976e8cbd58a` · **Branch:** `feature/crypto-recovery-acceptance-candidate-2026-11-15` (uncommitted at time of receipt) · **Live trading:** NO-GO.

## What was actually built

1. The prior `crypto_research_preflight.py` (46 standalone tests) remains **read-only and synthetic**, and is not described as an execution permit.
2. Added `crypto_spot_research_gate.py`: requires **real** `MarketState`, two independent `SpecialistEvidence` roles, an actual Stage97 `CryptoPaperIntent` and independently replayed `CryptoPaperBook`. The function requires source/time/price correspondence (USD↔integer USDT cents), independently revalidates OHLC state and checks Stage97's local spot quantity, cash, exposure, session-loss and kill requirements. **No signing function, no `book.apply`, no order route.** Its receipt always forbids permission, orders, live trading and production readiness.
3. Added `test_crypto_spot_real_stage97_integration.py`: actual synthetic MarketStateBuilder → specialist evidence adapter → consensus → read-only spot risk precheck → **separate test-only exact-intent permit and explicit local approval** → Stage97 atomic paper ledger. Real synthetic buy, partial sells, closed P&L, restart, independent INR/USDT read-only review, forged/stale permit, no approval, kill/protective exit, tampered SQLite, stale data, wrong price and invalid consensus are covered.
4. The original Stage97 and Stage98 tests had `with sqlite3.connect(...)` patterns that **commit/rollback but do not close a connection**. Under Python 3.13 `-W error`, those unclosed connections generated `PytestUnraisableExceptionWarning` in later tests. The only changes in those two legacy tests are explicit `contextlib.closing` and preservation of the transactional `with db:` block. No Stage97 production risk/ledger/permission code was modified.
5. Retained the bounded recovery repeatability runner from the previous candidate (test files are fixed allowlisted; timeout is a failure). Its runner unit tests use mocked subprocesses; separate actual pytest executions were performed below.

## Material design discovery: generic lots vs spot microcoins

`TradingIntelligencePipeline` uses `AuthoritativeRiskEngine` with **whole-lot/units** and a portfolio capital/exposure model. Stage97 handles **microcoin-sized BTC spot quantities** and a separate USDT-cent ledger. Under a realistic USD $2,000 synthetic account and BTC price $50,000, the generic pipeline denies an integer 1-unit lot because it exceeds exposure. Feeding an artificial large capital value or silently converting lot quantities to microcoins would be a false risk-approval bypass.

The new additive gate **does not reuse generic `risk_quantity` as a spot quantity**, does not issue permits, and checks actual Stage97 spot units and head. It is intentionally a *local research precheck*, not an independent global Risk & Veto service and not a production risk boundary. Stage97 still requires separate signed test permits and enforces its own caps atomically. To finish issue #134 beyond this synthetic path, build a separately audited Crypto spot risk model and external authenticated operator identity without weakening any legacy limits.

## Exact tests and scope

- Source parity checked against authoritative GitHub blobs: `stage97_crypto_paper.py`, `stage98_dual_market_review.py`, `intelligence/pipeline.py` and patched `stage121_research_supervisor.py`. Existing Stage97/Stage98 legacy test original Git blob IDs also matched GitHub before test-only correction.
- Strict integration/guardian focused group: **156 passed**, 0 failed, 0 skipped, Python 3.13.5 with `-W error`; also `compileall` passed.
- Real (not mocked) recovery runner: **5/5** subprocess-bounded repetitions of the Stage121/123 fixed suite, each **38/38 passed**, total **190 successful test invocations**. All results retain `production_recovery_certified=false`; issue #131 remains OPEN.
- Prior broader reconstructed source checkout: **4,881 collected tests passed + 5 subtests** in eight bounded groups, after correcting the two test-only connection cleanup errors and using a normal Node-enabled environment. Two earlier Node skips were eliminated by rerunning with the normal PATH. This 4,881 run was before adding five further actual-integration checks, and the **final collected count is 4,886**; the five new cases passed in the later strict focused run. The reconstructed local checkout does **not** contain the six exact-final-HEAD provider-redirect tests from Work's previously pushed security patch; it is not a byte-identical entire GitHub HEAD. GitHub PR #133 independent CI still passed on its actual head.
- Full broad batches were run with warning visibility (`-W default`). Numerous inherited Python 3.13 `ResourceWarning` messages and some fork deprecations remained; **do not claim full `-W error` green**. Time-bounded intermediate attempts were superseded by completed split runs, not counted as passes.
- Stage97 genuine public-exchange connectivity, authenticated human approval, licensed data, external risk issuer, exchange fill/margin, actual Android-PWA syncing and representative production recovery sign-off are **unverified**. No profitability claim.

## Safety gates and next publication

- Publish only an additive, privacy-safe noreply Git CLI commit on the new feature branch with a **Draft PR stacked on stable-baseline PR #133**. Never merge `main`, change repository visibility or enable live orders.
- Run current authoritative Python 3.11/3.12/3.13 GitHub CI, old Core CI, calibration if triggered, full-history Secret Scan, reviewer/security/ledger tests before accepting the change.
- This is an **offline research integration candidate**, not a production Crypto trade system.
