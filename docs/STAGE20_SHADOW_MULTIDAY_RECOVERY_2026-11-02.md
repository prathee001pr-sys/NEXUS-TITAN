# Stage 20 — Research Shadow Multi-Day QA & SQLite Recovery Rehearsal

**Implementation scope:** Offline, opt-in validation on top of the **separate,
BUY-only research ledger** from draft PR #11. No changes to the authoritative
VirtualAccount, broker adapters, risk/veto controls, production permissions,
or strategy promotion.

## Recovery drill

Use `run_research_shadow_recovery_drill(ledger, backup_path=...)` for an
on-machine SQLite *online backup* and independent restore/reopen check.

- Verifies the source's existing Stage19 audit/state chain **before** backup.
- Uses SQLite's `Connection.backup` rather than directly copying a possibly
  active WAL database file.
- Reopens and verifies a temporary backup through the Stage19 ledger's
  existing invariants. Checks its full account state against pre/post
  source snapshots, including cash, held funds, open/closed orders, inventory
  and audit event count.
- Refuses to overwrite source or an existing destination. Uses an exclusive
  file link after successful validation to create the requested backup.
- If an independent writer changes the account during the drill, it **fails
  closed** rather than labeling a mismatched snapshot recovered.
- The source DB is not restored over or intentionally mutated, and the backup
  remains available as a separate SQLite file for inspection/recovery.

A successful local rehearsal is **not** disaster recovery evidence across
machines, filesystem corruption, disk loss or malicious administrator access.
Backup secrecy/encryption, rotation, offsite storage, restore-time objectives,
multi-process race tests and external security assessment are still pending.

### Example (synthetic-only research account)

```python
from nexus_titan.shadow.research_reservation_ledger import DurableResearchShadowLedger
from nexus_titan.shadow.research_recovery_validation import run_research_shadow_recovery_drill

ledger = DurableResearchShadowLedger(
    "data/research_sim.sqlite3",
    account_id="RESEARCH-ONLY", starting_capital=75000.0,
)
drill = run_research_shadow_recovery_drill(
    ledger, backup_path="backups/research-2026-11-02.sqlite3",
)
assert drill.passed and drill.live_orders_transmitted == 0
```

The backup parent directory must already exist and the backup name must be
new. Do not use this backup as a substitute for operator-controlled copies.

## Multi-day evidence gate

`inspect_multiday_shadow_evidence` consumes an ordered sequence of
`DailyResearchShadowRecord` items: India trading date, post-session
observation timestamp, `ResearchLedgerStatus`, expected day cash delta
and the owner's evidence reference.

It rejects or flags:
- Missing configured trading days between provided start and end, duplicate
  dates, out-of-order dates and dates on market holidays/weekends.
- Observations before the *configured* exchange session close, wrong local
  trading day, naive timestamps, missing references.
- Changing account ID or opening capital, negative/nonfinite amounts,
  inconsistent reserved versus available cash, increasing cash in this
  BUY-only research ledger and unexplained day-close cash delta.
- Regressing audit/terminal-order counts or synthetic BUY-only inventory.
- Unresolved overnight research orders/reservations unless the explicit
  opt-out is provided. Opting out never turns on live permissions.
- Forged promotion flags or nonzero live-order count.

Only the date window **between the first and last submitted day-close
records** is checked. The calendar is operator-supplied; no NSE official
holiday/half-day schedule is embedded or independently authenticated.

```python
from nexus_titan.shadow.research_recovery_validation import (
    DailyResearchShadowRecord, inspect_multiday_shadow_evidence,
)

report = inspect_multiday_shadow_evidence(
    recorded_day_closes, calendar=reviewed_nse_session_calendar
)
assert report.is_structurally_valid
assert not report.data_source_authenticity_verified
assert not report.external_broker_reconciliation_verified
assert report.live_orders_transmitted == 0
```

**Important distinction:** Stage20 checks *internally consistent
operator-supplied snapshots*, not a source-authenticated audit trail of
broker fills or per-day P&L. `expected_cash_change` is a manual
independent comparator; it is not a documented exchange settlement.
A passing report proves no actual NSE market sessions were observed.

## Unverified external release gates

- Licensed historical and live NSE option-chain/depth data and official
  point-in-time contract master/holiday calendar.
- Current verified broker charge schedule, execution slippage,
  margin/assignment/exercise and settlement reconciliation.
- Genuine multi-day paper/shadow evidence with verified data lineage.
- Independent security assessment, offsite encrypted recovery drill,
  operator signoff and active Risk & Veto integration.

**Live trading remains disabled.** Current branch is stacked on draft
PR #11 → #10 → #9 → #8 → #7 → #6, and does not alter `main`.
