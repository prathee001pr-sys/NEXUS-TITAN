# Stage147 — Metadata-pinned atomic Crypto review caps (research-only)

Status: **candidate, not yet merged or production-approved**.

## Motivation
The Stage97 synthetic BTC-USDT journal authenticates a local TEST permit and its own account limits, but the higher-level `CryptoSpotIndependentReviewPolicy` is opt-in. The existing test `test_opt_in_limitation_stage97_direct_api_does_not_enforce_new_stricter_policy` proves that a signed direct `book.apply` call can bypass that additional review.

## Design
This candidate adds an optional `atomic_review_policy` constructor argument for **new synthetic accounts only**. It accepts the existing typed `CryptoSpotReviewPolicy`, rejects policies exceeding hard Stage97 limits, and pins the exact policy into the existing SQLite account settings SHA. Reopening a stricter account without the same policy is refused by the journal metadata check; reopening legacy accounts as stricter without an explicit migration is also refused. No existing V1 account settings hash is changed.

The independent policy's quote-age, order-notional, total-exposure, realized-loss and fee constraints are checked in `_assert_atomic_trade_authority` while `_apply` holds SQLite `BEGIN IMMEDIATE`. This covers the existing public `apply()` and direct underscore-prefixed `_apply()` mutation paths for new strict-mode books. Duplicate permit replay remains governed by the original authenticated journal replay, and KILL / protective SELL remain available as guarded operations. The previous Stage97 HMAC TEST permit is still required for every TRADE, so the new policy cannot authorize trades by itself.

## Security and scope limitations — DO NOT MISREPRESENT
- **This remains optional and only applies when a new account is explicitly created with the stricter policy**. Existing V1 synthetic accounts remain on their original controls and cannot be silently migrated. Global mandatory all-account Risk & Veto is **NOT COMPLETE**.
- This additional risk fence is enforced using the current process's immutable typed policy and local journal metadata. It is **not** proof of an independent service boundary, authenticated human identity, broker control, exchange authorization, or tamper-proof execution outside the trusted Python process.
- Local test permits are not production risk approvals. No broker route, exchange API, live trading, remote signing authority, or deployable authentication is introduced.
- Policy checks do not constitute licensed point-in-time market evidence or real executable bid/ask validation.
- Python callers able to arbitrarily monkeypatch the runtime are not a trusted production security boundary. Formal deployment isolation remains a separate issue.

## Acceptance
- Run `tests/test_stage147_atomic_crypto_review_policy.py` with `-W error`, including direct public and private-path bypass attempts, restart downgrade, stale quote, loss/exposure/fee caps, immutable journal, one-way emergency stop and signed protective SELL.
- Run existing Stage97/98 research review, independent risk, strict F&O, recovery and full project regression without weakening safety tests.
- Publish only via Git CLI noreply identity on a separate feature branch, open a Draft PR, independently confirm exact-head GitHub CI 3.11/3.12/3.13 and full-history Secret Scan.
- Keep #134 OPEN until production-grade global enforced risk/identity and all relevant execution paths are covered.

## Stage97 independent source-audit re-review — 2026-11-17
The Stage147 source addition intentionally changes the Git blob of
`src/nexus_titan/operations/stage97_crypto_paper.py` from
`af3b87dbbfc718bc3ac2d46da1eb546c4b440de0` to
`ce6d362d1f6f1b18ec17402cded64db8b08444b6`. The former was the
Stage97 pre-Stage147 audit pin. The Stage97 source-inventory diagnostic
therefore correctly returned `BLOCKED_SOURCE_DRIFT` and eight fail-closed
tests rejected it in the Replit 2026-11-17 initial Stage147 run:
4,993 passed, 8 failed, 1 skipped, 5 subtests passed.

An additive source-integrity re-review pins only the **exact** Stage147
candidate blob in `stage97_execution_surface.py`, retains the old pin as
`STAGE97_PRE147_GIT_BLOB`, and keeps the reviewed gateway blob unchanged.
The scan's discovery rules, unknown/direct `apply` and `_apply` call
inventories, source-drift rejection and NO-GO verdict logic are unchanged.

The mandatory all-account independent Risk & Veto guarantee remains **FALSE**.
For the current source, the correct static verdict is
`BLOCKED_PUBLIC_DIRECT_STAGE97_APPLY` even when the hash pin matches. This
is not a waiver, safety signoff, real human identity verification or production
authorization.

Acceptance requires all old source-tampering / reflective access / direct
execution detection tests, two new pin+drift regression tests, Stage147
strict atomic tests, existing Stage97 and Stage142 suites and full regression
to pass. Then verify exact-head Python 3.11/3.12/3.13 CI and full-history
Secret Scan before any signoff. Keep this branch as Draft and `main` untouched.
