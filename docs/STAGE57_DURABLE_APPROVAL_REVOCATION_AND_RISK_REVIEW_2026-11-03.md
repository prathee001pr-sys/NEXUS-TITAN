# NEXUS TITAN — Stage57 Durable Paper Approval Revocation & Risk Evidence Review

**Date:** 2026-11-03  
**Parent:** Stage56 Draft PR #48  
**Source branch:** `feature/stage57-durable-paper-approval-revocation-2026-11-03`  
**Scope:** synthetic/paper only; no independently verified human identity, real market feed, broker, privileged service or live orders.

## Why this increment matters

Stage48 already has a one-use HMAC-SHA256 token and local durable SQLite
replay protection for manual **synthetic paper BUY** approval. Its token
`actor` is a string signed with a secret. An HMAC **does not verify a human's
identity**. Stage56 added a separate, brokerless local synthetic Risk & Veto
screen, **not** a mandatory execution gateway. A signed Stage48 challenge
did not carry the Stage56 policy/quote evidence digest.

Stage57 makes two incremental, testable improvements while retaining
that critical distinction:

1. **Durable deny-only revocation** of token IDs and signer labels is
   enforced inside Stage48's actual `verify_and_consume` SQLite
   transaction. Revocation stays in force after process restart,
   and concurrent revocation vs consumption is serialized in the
   same database for cooperating clients.
2. A separate **read-only QA binding inspector** compares a current
   Stage48 pending paper challenge with a freshly re-screened Stage56
   synthetic quote/account/risk-policy observation and its expected
   previous digests. This is a diagnostic, *not an added requirement*
   in the Stage48 authorization callback; it does not issue a token
   or approve, submit, fill or cancel an order.

## Implementation

### `src/nexus_titan/core/security_gates.py` — revocation integrated

The existing `CryptographicApprovalVerifier` now owns two more local
SQLite tables, within its pre-existing replay database:

- `revoked_approval_tokens(token_id PRIMARY KEY, revoked_at_epoch)`
- `revoked_approval_actors(actor PRIMARY KEY, revoked_at_epoch)`

New methods:

- `revoke_token(token_id, now_epoch=None)` — durable permanent
  negative decision for the given token identifier.
- `revoke_actor(actor, now_epoch=None)` — durable permanent negative
  decision for all current and future tokens with that exact
  signer-label string.
- `local_revocation_status(token_id, actor)` — local read-only
  lookup of these two negative lists.

Both revocation writes use `BEGIN IMMEDIATE`, as does the **existing
`verify_and_consume`** path, which now checks both revocation
tables **before** writing the consumed-nonce record. A rejected token
is not consumed. A revocation that reaches the lock first vetoes the
pending token; if the consumption commits first, revocation cannot
undo that **already completed approval**. That is a deliberate
linearization boundary, not a promise to roll back accepted paper
orders or submitted fills.

Revocations are idempotent and deliberately provide **no automatic
un-revoke** or override flag. They are still only in-process API calls:
no independently authenticated administrative actor or authorized
key-holder has been implemented. A caller able to modify the replay
database or code is not stopped by an HMAC or SQLite row.

The Stage48 callback already uses `verify_and_consume`, so revocation
is applied to Stage48 signed BUY approvals *without changing existing
paper-order state transition or placing any live order*. Its existing
expiry, nonce-once, account/order snapshot binding, role and kill-switch
checks remain.

### `src/nexus_titan/operations/local_approval_risk_review.py`

`inspect_stage57_local_approval_binding(...)` re-evaluates the
Stage56 **local synthetic risk** with a supplied current clock and
compares it with an expected Stage48 challenge and risk-input/policy
digests. It checks:

- Stage48 pending-approval challenge account/order/target/snapshot
  shape and that it claims no verified outside authority;
- Stage56 synthetic intent `request_id` matches the Stage48
  `order_id` and synthetic account IDs match;
- fresh Stage56 risk screen is not vetoed (quote age, spread,
  drawdown, loss, capital, stop, etc.);
- exact expected Stage56 input/policy SHA256 values have not changed;
- resulting read-only QA review digest is stable under identical inputs.

The returned `Stage57ApprovalRiskReview` explicitly says:

```json
{
  "token_issue_authorized": false,
  "order_submission_authorized": false,
  "independent_human_identity_verified": false,
  "external_market_quote_authenticated": false,
  "signer_key_isolated_in_trusted_service": false,
  "stage48_challenge_integrates_stage56_review": false,
  "legacy_apis_globally_fenced": false,
  "live_trading_enabled": false,
  "production_ready": false
}
```

**CRITICAL:** The Stage48 signed token still binds to the old Stage48
order snapshot, **not automatically to the Stage56 QA input digest**.
The Stage57 reviewer is NOT wired as an unbypassable requirement before
Stage48 approval, and the Stage56 quote/market, account state and
reference time can all be provided or forged by the caller.
Do not call its digest cryptographic risk attestation.

### Tests and offline smoke

- `tests/test_stage57_approval_revocation_risk_binding.py` covers
  token/actor revocation before real Stage48 local paper approval,
  no order-fill side effects, wrong role/expiry existing regressions,
  idempotent permanent revocation, invalid labels/times, process
  restart, replay persistence, two cooperating SQLite verifier
  objects concurrently revoking/consuming one ID, and historical
  consumption remaining unaffected by a later revocation.
- It also tests Stage57 positive **local QA consistency** and vetoes
  on changed quote, risk policy, cash/kill switch, stale input, wrong
  account/order, malformed challenge, mismatched expected hashes,
  and confirms no approval token/order or paper ledger mutation from
  the review function.
- `scripts/run_stage57_approval_revocation_smoke.py` creates
  disposable synthetic Stage48 paper account and HMAC key. It creates
  two pending paper BUY intents, revokes one token ID and a second
  signer label, checks both approvals denied, demonstrates a
  non-authoritative Stage56 QA binding review and confirms **no
  orders filled or broker orders sent**.
- Stage52's no-write source inventory now expects the Stage57
  review type and the three new verifier methods. Structural source
  presence is not an independent security attestation.

## Security and governance limits

| Control | Verified local scope | Outstanding trusted scope |
| --- | --- | --- |
| HMAC signature + expiry | Stage48 existing token verification | independent human ID / delegated roles |
| One-use nonce | SQLite replay row | authorization at actual broker boundary |
| Permanent negative token/actor revocation | same SQLite replay DB as nonce | authenticated revocation administrator, key custody |
| Concurrent revocation vs nonce use | one SQLite `BEGIN IMMEDIATE` serialization | upstream order/fill rollback or external broker freeze |
| Fresh risk-policy / quote-digest comparison | Stage57 advisory QA recheck | mandatory verifier-bound order and market data |
| Stage43–55 capital authority | separate local research and paper books | globally atomic capital, fee, partial-fill and budget controls |
| Live market/NIFTY/BANKNIFTY futures-options | NOT connected | licensed point-in-time quote/history and margin metadata |
| Global Risk & Veto | NOT enforced | protected execution service, mandatory credentials |
| Live/real-money trading | disabled | owner approval plus independent production sign-off |

A revoked label does not map to a real authenticated person; multiple
labels could represent the same human and no identity-provider account,
MFA enrollment, signed human session, revocation trust policy, key
rotation or secure signer custody has been implemented.

The revoke methods are **deny-only**; direct API callers could deny
someone else's local label. Production administrative authorization is
a separate essential design problem.

Existing direct `VirtualAccount.submit_order`/`execute_fill` and
other legacy trading methods remain separately callable. Stage48
manual callback and Stage57 evidence review do not globally control
them. The approved black/silver TITAN digital-human face artwork also
remains to be connected to the final frontend.

## Test instructions

```bash
python scripts/run_stage57_approval_revocation_smoke.py
python -m pytest -q tests/test_stage57_approval_revocation_risk_binding.py
python -m pytest -q
```

For completion evidence require **final PR-head** GitHub Actions CI
success on Python 3.11/3.12/3.13 and the existing Stage25 synthetic
smoke. Passing these tests establishes only offline QA behavior and
does not authorize live trading or strategy promotion.

## Recommendation for Stage58

Build real-exchange-*independent* execution/cost/slippage simulation
for future NIFTY/BANKNIFTY F&O historical data, with explicit market
contract/fee metadata inputs, partial fills, liquidity limits,
exchange calendar and bad-data veto checks. Use synthetic fixtures
until the owner supplies verified licensed real data. Do not
connect brokers or enable real trading.

**Keep this PR DRAFT and UNMERGED, preserve `main`, and require
owner/combined-tree/security review before integration.**
