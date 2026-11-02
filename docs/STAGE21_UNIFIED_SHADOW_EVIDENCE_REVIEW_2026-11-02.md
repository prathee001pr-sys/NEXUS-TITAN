# Stage 21 — Unified Research Evidence & Independent Release Review Checklist

Stage 21 consolidates the **offline, BUY-only, synthetic research** validation
from stages 19–20 with untrusted external document submissions. It is **not**
a production release evaluator, SEBI compliance attestation, broker fill audit,
algorithmic trading permission, or strategy profitability certification.

## API

`nexus_titan.shadow.unified_readiness.prepare_unified_shadow_readiness`

Inputs:
- Existing `DurableResearchShadowLedger` and a bounded list of
  `DailyResearchShadowRecord` entries.
- Operator-supplied `MarketCalendar` for Asia/Kolkata with verified holidays
  and sessions, and the Stage 20 `ResearchRecoveryDrillReport` object.
- `ExternalEvidenceSubmission(category, evidence_id, reference,
  claimed_sha256, submitted_at)` for each document category.
- Explicit `claimed_closed_trades` count (default 0), `minimum_sessions`
  (default 20), `minimum_closed_trades` (default 30), `as_of` clock.

The module **rechecks** the Stage19 local ledger and Stage20 multi-day report,
compares the last day close to the current SQLite account state, validates
observations against the provided clock, and verifies the actual local backup
file by reopening the SQLite database. Forged recovery dataclass claims alone
cannot satisfy the recovery gate.

## Evidence collection categories

1. `licensed_market_data`: data-rights and lineage documents
2. `official_contract_calendar`: point-in-time NSE contract and session proof
3. `broker_cost_schedule`: charge/fee/settlement references
4. `execution_calibration`: timestamped depth, slippage and fill validation
5. `independent_security_assessment`: independent security report
6. `offsite_recovery_drill`: encrypted offsite restore evidence
7. `real_feed_multiday_shadow`: real-feed, independent multi-day paper logs
8. `owner_signoff`: explicit documented owner approval reference

Items require a distinct evidence ID, category, claimed 64-character SHA-256
and non-future timezone-aware submission time. These are **operator-provided
strings**. The software **does not download, hash, verify signatures, inspect
licence contracts or confirm reviewer independence**. A submitted record is
always classified `SUBMITTED_UNVERIFIED`, **never independently verified**.

## Decisions: conservative by construction

| Decision | Meaning |
| --- | --- |
| `BLOCKED_STRUCTURAL_VALIDATION` | Daily records, local recovery, research ledger, coverage or submitted metadata failed |
| `BLOCKED_EXTERNAL_EVIDENCE` | Research checks passed, but required external document categories are missing |
| `INDEPENDENT_REVIEW_REQUIRED` | All **self-declared** documents present and structural checks pass; independent validation still outstanding |

`review_candidate=True` only means a person can begin the *external
evidence review*. It cannot authorize any live trading, broker connection,
strategy promotion, or production deployment. The report always states
`live_trading_enabled=False`,
`automatic_strategy_promotion=False`,
`external_authenticity_verified=False`, and
`official_market_data_verified=False`.

A human-supplied count of `claimed_closed_trades=30` may pass a **review
preparation** threshold but is **not** proof of 30 genuine completed
round-trip trades. Stages 19–20 are BUY-only and do not validate real fills,
sell positions, margin, price discovery or trading returns.

## Example (test fixtures, not real NSE evidence)

```python
from datetime import datetime, timezone
from nexus_titan.shadow.unified_readiness import prepare_unified_shadow_readiness

report = prepare_unified_shadow_readiness(
    ledger=research_ledger,
    daily_records=operator_day_closes,
    calendar=operator_reviewed_nse_calendar,
    recovery=local_recovery_drill,
    evidence_submissions=external_claimed_documents,
    claimed_closed_trades=0,  # no verified round trips in BUY-only research
    as_of=datetime.now(timezone.utc),
)
assert not report.live_trading_enabled
assert not report.automatic_strategy_promotion
print(report.release_decision, report.blocked_checks)
```

## Outstanding safety and operational gates

- Independently authenticate historical/live market data providers, contract
  master revisions, NSE holidays and depth timestamps.
- Obtain actual broker reports and validate statutory fees, SPAN/ELM,
  exercise/assignment and futures/options lifecycle.
- Conduct supervised **real-feed** multi-day paper validation including
  closed trade inventory and profit attribution.
- Demonstrate security assessment and encrypted *off-host* restore under
  deliberate failure conditions. Stage 20's local backup test is not enough.
- Obtain human authorization, Risk & Veto integration review, deployment
  security controls and deliberate rollback plan before considering
  permissioned broker actions.

**All upstream PRs remain draft** (#6 → #7 → #8 → #9 → #10 → #11 → #12).
This Stage 21 work is separately staged; `main` remains unchanged,
and no live trading path is present.
