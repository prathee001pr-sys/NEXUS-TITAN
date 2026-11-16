# NEXUS TITAN — Independent Synthetic BTC Spot Research Risk Review (NO LIVE)

**Date:** 2026-11-16 · **Expected parent PR:** #138 · **Exact parent commit:** `298ffe060db3e15a7b215d444866aefffa2a79cb` · **Target:** stacked Draft PR only.

## Scope and value

This is an **additive, read-only, synthetic-only** check that re-evaluates real `MarketState`, two independent `SpecialistEvidence` lanes and a real `CryptoPaperBook` through the existing Stage97 spot research gate, then applies an *additional tighter* review policy to the same journal head. It is not an execution permit or independent production risk engine.

1. `CryptoSpotReviewPolicy` requires explicit bounded integer caps for a single notional, total book exposure including estimated fees, lifetime realized loss, quote age, and fee rate.
2. The four comparable review caps **cannot exceed** the immutable Stage97 account's corresponding caps. The fee-rate review cap can only veto when the account's configured fee is greater than that cap; it cannot alter Stage97 fees.
3. The reviewer independently checks the actual journal head again after research consensus (a changed revision/tip causes a denial), and derives currency/exposure from Stage97's real ledger. Its SHA-256 policy fingerprint is **not** authenticated provenance or a signature.
4. Only BUY entries are subject to added new-entry exposure/order/fee/loss caps. A separately signed protective SELL remains possible after an emergency stop, subject to Stage97's independent signed-permit, position and atomic ledger checks.
5. Neither approval booleans nor generic portfolio whole-lot sizing are accepted as BTC microcoin authorization. The reviewer **never signs permits, calls `book.apply`, places paper/live orders or changes risk/permissions**.

## Verification evidence (local synthetic checkout)

- Exact Stage97 source and Stage97 research gate Git blob IDs on the reconstructed checkout matched PR #138 GitHub source: `0c1600848c8095e05581531e4e04f3acc7265bd7` and `87db9e08bce476349e4c0a809d97f2a8d1fe4bc3`.
- `PYTHONPATH=src python -m pytest -q -o addopts='' -W error` across the new independent-review tests plus Stage97 Crypto real-integration, legacy paper, Stage98 dual-market, Stage121/123 recovery, recovery-runner and Stage211–215 independent-veto tests: **288 passed, 0 failed, 0 skipped**, Python 3.13.5.
- Added negative cases for booleans/invalid policy, attempted relaxation of Stage97 caps, tighter order/exposure/freshness/fee/lifetime-loss veto, changed SQLite journal revision, unapproved/missing signed permit, kill and protective signed close, and unchanged account on read-only review.
- Separate, bounded local Stage121 `hang_once` CPU-contention experiment: 5/5 completed in 4-worker load under 4-CPU cgroup quota. Each intentionally timed out once before recovery and had a valid SQLite journal; **no production reliability sign-off**.
- Previous exact PR #138 GitHub CI (Python 3.11, 3.12 and 3.13) and Secret Scan were green. **This new candidate has NOT been committed or tested in GitHub CI.** Never promote local results to all-runner certification.

## Risk/permission controls

- `CryptoSpotIndependentReviewReceipt` explicitly sets signed permit issued, paper order submitted, exchange order submitted, live trading, production readiness, and independent production risk certification to **false**.
- Stage97's immutable risk policy and exact-intent HMAC test permit remain the only local paper mutations. Human approval flags in synthetic tests are not cryptographically authenticated identities.
- This additive read-only reviewer cannot compensate for unresolved all-path independent Risk & Veto, authenticated operator identity, licensed market data, real venue execution, hosted PWA evidence sync or representative production-host recovery tests.
- This is **not** Stage214's caller-attested global `IndependentVetoReceipt` becoming production authority; no such promotion has occurred.

## Next release checks

1. On the exact branch, rerun the focused strict suite with Python 3.11/3.12/3.13 and full GitHub CI/Secret Scan.
2. Run complete **post-change** strict or warning-visible broader regression and independently review risk/stop recovery behavior.
3. Integrate the separate authenticated, mandatory all-path Risk & Veto architecture only after independent safety approval. Do not enable live trading or force a main merge.

**Verdict:** Local synthetic research gate **BUILT + FOCUSED TESTED**; GitHub integration, complete Crypto and operational acceptance **OPEN**. PR must remain Draft and `main` unchanged.
