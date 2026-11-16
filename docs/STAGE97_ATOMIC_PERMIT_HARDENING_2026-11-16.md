# NEXUS TITAN — Stage97 synthetic paper atomic-permit boundary hardening

**Review date:** 2026-11-16. **Parent:** Draft PR #141, commit `1c757b636a7e0de68b82c8f668f5fe34727dbef5`. **Mode:** synthetic research only, never live.

## P1 discovered defect: internal SQLite mutation without signed test permit

On the reconstructed source verified against GitHub's published Stage97 blob `0c1600848c8095e05581531e4e04f3acc7265bd7`, the underscore-prefixed `CryptoPaperBook._apply()` accepted a `TRADE` payload without a permit. A controlled temporary SQLite fixture recorded an unpermitted synthetic BUY (revision 1, 10,000 microcoins). The public `apply()` performed HMAC/expiry/approval checks **before** calling `_apply`, but `_apply` itself was callable and did not enforce them. This was a genuine research-paper authorization gap. It did **not** access a crypto exchange or send real orders.

## Minimal fail-closed correction

1. `CryptoPaperBook._apply()` now revalidates **every TRADE** inside the SQLite `BEGIN IMMEDIATE` transaction. It requires a typed exact-intent HMAC TEST permit, verifies the signature, original intent hash, journal revision/tip, expiration and quote age for fresh operations, conservative paper policy, explicit synthetic BUY approval or enabled RISKY mode, and exact fee/notional economics.
2. The public `apply()` passes its caller's time/approval/autonomy evidence into the atomic layer, which no longer trusts public-layer checks alone. Legitimate idempotent replay of the identical signed operation is preserved without imposing new expiry on an old acknowledged event. Atomic CAS, fee/cash conservation, replay validation and kill/stop behavior are unchanged.
3. Emergency `stop()` remains an exact no-permit `KILL` event, never a permit-free `TRADE`. The independent prior Stage97 immutable cash/exposure/loss/kill guard remains intact; nothing raises risk limits, enables live trading, or adds exchange connectivity.
4. Source diagnostic adds visibility for explicit `._apply()` and `getattr(..., "_apply")` calls, and blocks new unreviewed callsites. It updates the pinned Stage97 source Git blob and continues to issue a **NO-GO** result; static AST analysis cannot rule out dynamic or external callers.

## Verified tests

- Negative atomic admission: no permit, forged key/signature, missing time/approval, invalid economics/source/intent, stale revision/quote, extra event fields, invalid bypassed autonomous policy. Failure leaves SQLite journal unchanged.
- Positive preservation: signed paper BUY, duplicate ack/replay, protective SELL/kill, Stage97/98 integration, staged risk, crash/restart and conservative reviewer. Focused `-W error` suite: **126 passed**.
- Full **reconstructed** Python 3.13.5 `tests/`: **4,967 passed, 5 subtests passed, 0 failed, 4 warnings** in 152.54s, pytest exit 0. Counts overlap. Four warnings are previous Stage88/89 multithreaded `os.fork()` test-harness warnings; not suppressed.
- Historical published parent PR #141 Python 3.11/3.12/3.13 CI and Secret Scan were green. **This patch has not yet been committed and has no new-head GitHub CI**. Do not equate reconstructed regression with authoritative head validation.

## Residual boundaries — NO-GO

- The local test HMAC key does not authenticate an actual human identity; a caller possessing a legitimate signed TEST permit can still use Stage97 `apply()` according to original immutable limits. The *optional tighter* reviewed gateway remains bypassable by a valid direct Stage97 call; mandatory all-path *stricter* Risk & Veto and operator authentication are **not** achieved.
- The local journal has no external rollback anchor and no hosted operator identity. Process-level callers with filesystem or code access remain outside a hardened trust boundary.
- Live trading, derivatives leverage, production secret handling, venue market provenance, Rust, and any real-money order route are **NO-GO**.
- Do not merge this draft into `main` or change permissions/visibility without explicit owner authorization. Continue to track #131 (recovery), #134 (Crypto all-path risk), #135 (owner-only PWA) and #137 (licensed Indian F&O evidence).

**Decision:** P1 synthetic-paper unsigned-atomic-write bypass **locally corrected + tested**, optional stronger reviewer and production authorization **still BLOCKED**. Publish via authenticated GitHub noreply Git CLI and verify exact-head 3-version CI + full-history Secret Scan before review.
