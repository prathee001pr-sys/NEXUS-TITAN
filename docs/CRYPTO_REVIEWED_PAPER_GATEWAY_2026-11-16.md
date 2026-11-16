# NEXUS TITAN — Stage97 Reviewed Synthetic Paper Gateway (Research Only)

**Date:** 16 November 2026. **Parent:** Draft PR #139, exact head `da50b5e9a9375ff1c36e3bcaa73f2b36a3ef50fd`. **Target:** isolated stacked Draft PR only; `main` unchanged.

## Additive implementation

- New `src/nexus_titan/operations/crypto_spot_reviewed_paper.py` defines `submit_reviewed_synthetic_paper(...)`, an **opt-in**, synthetic BTC-USDT local paper route. It requires actual `MarketState`, two distinct `SpecialistEvidence` roles, actual Stage97 `CryptoPaperIntent` and `CryptoPaperBook`, explicit `CryptoSpotReviewPolicy`, independently supplied **signed local TEST permit**, and explicit local human-approved BUY boolean.
- It calls the existing `review_synthetic_crypto_spot_risk()` before `CryptoPaperBook.apply(...)`. This denies missing/fake/stale review evidence, less strict policies, bad timestamp, invalid quote, stopped account or mismatched journal tip, without issuing any new permit.
- The signer **is not** implemented, called, or passed a secret in this gateway. Only the Stage97 existing atomic `apply()` rechecks permit signature, intent binding, expiry, idempotency, account cap, kill and ledger replay. This prevents permit/journal race from bypassing Stage97 even after a positive research review.
- A protective SELL after kill remains possible with a separately signed test permit; no autonomous mode is exposed. Successful receipt records only the synthetic local paper journal transition. It explicitly denies authenticated-identity, globally mandatory Risk & Veto, live trading or production readiness claims.

## Critical known limitation — independently demonstrated by test

The existing direct `CryptoPaperBook.apply()` API **can still be called without** this *optional stricter* review; it enforces the original Stage97 immutable limits and its independent local signed-test permit, but not the new lower review caps. New regression test `test_opt_in_limitation_stage97_direct_book_apply_does_not_require_new_stricter_policy` demonstrates this intentionally. Therefore **mandatory all-entrypoint independent Risk & Veto is NOT achieved** and issue #134 stays OPEN. This code is NOT a production authorization gateway and cannot be promoted without a deliberately reviewed future all-path architecture and authenticated operator session.

## Local verification

- Reconstructed Stage224 + Stage121 hardening + PR #138 + PR #139 sources were assembled from preserved archives. Exact source hash parity to GitHub was confirmed for Stage97 (`0c1600848c8095e05581531e4e04f3acc7265bd7`), BTC research gate (`87db9e08bce476349e4c0a809d97f2a8d1fe4bc3`), independent review (`89c06bc373184c8ce24280ae33170d8a979f0358`) and Stage121 supervisor (`5327b04f4dd4928d3221b31bafacb7549b8906d9`). This does **not** imply the reconstructed whole tree equals GitHub PR #139.
- New route tests include BUY, partial/full SELL and restart, P&L conservation, missing/forged/wrong-account/stale/expired signed permits, no human approval, wrong source/price/role/quote age, lower policy veto, disabled book, racing kill, protective close, duplicate replay and explicit all-entrypoint review bypass limitation.
- Targeted local Python 3.13.5 `-W error` **313 passed, 0 failed, 0 skipped** across new and existing Crypto, Risk & Veto and Stage121/123 recovery tests.
- Actual bounded local recovery runner **3/3 successful**, approximately 6.0–6.5 seconds per trial, actual Stage121/123 tests (not simulated subprocess results), but only synthetic research and not operational representative-host reliability.
- Broader reconstructed regression groups 0, 1 and 3 finished with **424 + 479 + 473 = 1,376 passed** and 2 warnings. Group 2 did not complete within the execution session and remaining groups were not run. **Do not claim complete post-change full-suite green.** The authoritative PR #139 parent GitHub Python 3.11/3.12/3.13 CI and Secret Scan were successful, but new code is pending its own CI.

## Follow-up acceptance

1. Publish only on feature branch with GitHub noreply author/committer; open a **Draft stacked PR** against PR #139's head branch.
2. Verify exact-head Python 3.11/3.12/3.13 GitHub CI, Secret Scan and independent review of direct API exposure.
3. Leave production operator identity, venue routing, external market evidence, true all-path risk enforcement, live trading, private PWA backend and main merge **BLOCKED**.
