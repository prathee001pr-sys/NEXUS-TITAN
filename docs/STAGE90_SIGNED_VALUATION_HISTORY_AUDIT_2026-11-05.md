# Stage90: locally signed synthetic F&O MTM history eligibility (NO-LIVE)

## Scope

This stage extends Stage89's existing selected single-SQLite synthetic NIFTY/BANKNIFTY long-option account **without modifying its journal, order lifecycle, risk policy, execution gateway, cash accounting or risk signatures**.

Stage89 can return a *point-in-time* signed-quote valuation but deliberately withholds profit factor, expectancy and drawdown for lack of an independently eligible historical equity series. Stage90 adds a **read-only, locally signed, in-memory history audit**. It does not imply that real-market returns, profitable strategies, prospective performance or production readiness have been established.

## Contracts and boundary

- Each checkpoint contains the complete typed Stage83 journal snapshot, Stage89 signed source quotes, the reproduced Stage89 mark, a previous-checkpoint SHA-256, its own digest and an HMAC authenticated under the existing local synthetic boundary's key with a separate Stage90 domain.
- Capture uses the existing book's coherent `synthetic_valued_snapshot` read. It has no write path, no new capital authority, no persistence and no broker connection. The issuer must possess the existing local test key. A mere public market quote, quote signature or old risk permit cannot authorize checkpoint creation.
- Verification recomputes a valuation from its historical typed snapshot and signed quote evidence **at the recorded observation time**, checks Stage83 cash and basis conservation, checks domain-bound HMAC/digest, forbids false real-market claims, and requires monotone valuation time, risk revision and book revision. No duplicate/repeated quote epochs while positions are open.
- An optional current-book anchor requires the final checkpoint's scope, account, journal tip, revision and risk revision to match a freshly obtained current ledger snapshot.
- Bounded input: at most 512 checkpoints, at most 500 signed quotes per mark. Caller supplies a maximum time gap. Missing/forked/reordered marks, stale/invalid signatures, altered cash, impossible equity and mixed account scopes block.
- **No statement of complete journal ancestry** is made for intervening old revisions. Each old snapshot is attested by a same-process synthetic test issuer, not independently reconstructed from an immutable historical database or witnessed by an external service. Stronger requirements must precede deployment.
- The only optional derived metric is `exploratory_synthetic_drawdown_percent`. It becomes eligible for **synthetic research only** after at least three valid marks spanning two seconds by default and satisfying the configured maximum gap. Short/incomplete evidence returns `None`. It cannot populate or promote the Stage89 official `max_drawdown_percent`.
- `profit_factor` and `expectancy_cents` stay `None`: no independently reviewed closed-trade cohort or prospective OOS eligibility has been established.
- A no-position all-cash account can be marked with an empty quote tuple, with 0% *exploratory synthetic* drawdown if the bounded history requirements pass. This does not show trading success.

## Usage

```python
from nexus_titan.operations.stage90_signed_valuation_history import (
    capture_stage90_checkpoint, inspect_stage90_history,
)

# Local synthetic test issuer and stage89 book/boundary only.
first = capture_stage90_checkpoint(
    book, boundary, issuer_key=local_test_key, quotes=(signed_quote_1,)
)
second = capture_stage90_checkpoint(
    book, boundary, issuer_key=local_test_key,
    quotes=(signed_quote_2,), previous=first,
)
# Capture a third independent timestamp and quote, then:
audit = inspect_stage90_history(
    boundary, (first, second, third),
    current_snapshot=book.snapshot_local_synthetic_portfolio(),
)
assert audit.real_market_evidence_verified is False
```

## Known NO-GO conditions

There is no durable checkpoint storage or external checkpoint signer, calendar/session reset, independent process isolation, full event ancestry across historical snapshots, genuine licensed market data/depth/fees, complete F&O expiry/settlement/short/futures lifecycle, cross-ledger capital authority or operational deployment. Exact checkpoint identity authenticates the existing local *synthetic* issuer only. Stage90 never changes entry permits, kill behavior or EVOLVE permissions.

Acceptance: all prior Stages1–89 regression tests plus new provenance/chain/gap/accounting/no-write/security cases must pass on Python 3.11/3.12/3.13. Do not merge to main without owner-reviewed integration and a production NO-GO audit. Stage91 is not started.
