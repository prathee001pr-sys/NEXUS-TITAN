# Stage 19 — Durable Research Shadow Reservation Ledger (2026-11-02)

This module adds a **separate research-only SQLite store** to the Phase 7
simulation chain. It neither replaces nor modifies the existing
`VirtualAccount` and `DurableAccountStore`, and has no connection to
live trading, broker APIs or the authoritative Risk & Veto engine.

**Entry point:**
`nexus_titan.shadow.research_reservation_ledger.DurableResearchShadowLedger`

## Design

- File-backed SQLite, transaction-scoped `BEGIN IMMEDIATE` for serializing
  cross-process reservations on one local filesystem. A single transactional
  commit writes reservation changes, simulated fills, inventory and audit.
- Multiple BUY research orders reserve cash from the **same shared account**.
  Each request specifies a maximum option premium per unit, an explicit
  fee buffer and whole-lot quantity. No cash is debited until settlement.
- `reserve_buy` requires independently reviewed point-in-time NSE OPTIONS
  contract metadata *declarations*. It never obtains real exchange permissions.
- `settle_buy` accepts Stage 18 `ResearchFillEvent` fragments, **recomputes**
  Stage 18 order reconciliation, checks reserved premium ceiling, fees and
  available capital, and closes the research order atomically.
- The full remaining reserve is released on settlement, even for partial fills.
  A partial outcome is **terminal** in this prototype; it cannot be continued
  against the same order ID. The original order ID cannot be reused.
- `cancel` releases all held funds without any simulated fill, and is also
  terminal. Cancelling twice or settling twice is rejected.
- Account-scoped unique replay IDs persist in SQLite. Duplicate/replayed
  `event_id` values **across research orders and process restarts** fail
  in one transaction (no cash or event changes survive a failed commit).
- The audit chain links operation events with SHA-256 and a digest of the
  resulting account/reservation/inventory/replay state. This can detect
  accidental corruption; **unencrypted/unkeyed hashes cannot stop a
  malicious database administrator from replacing the whole database**.
- The ledger is intentionally **BUY-only**. It credits synthetic long-option
  inventory, but selling existing inventory, options shorts, margin/portfolio
  risk, broker cash settlement and MTM/P&L are not implemented here.

### Example — all values and instruments synthetic

```python
from nexus_titan.shadow.research_reservation_ledger import (
    DurableResearchShadowLedger,
)
from datetime import datetime

ledger = DurableResearchShadowLedger(
    "data/research_shadow_ledger.sqlite3",
    account_id="RESEARCH-INDIA-PAPER",
    starting_capital=75000.0,
)
ledger.reserve_buy(
    order_id="study-0001", contract=reviewed_option_contract,
    strike=100.0, option_type="CE", lots=2,
    as_of=datetime.fromisoformat("2026-11-02T09:16:00+05:30"),
    max_unit_premium=6.0, fee_buffer=25.0,
)
# events: Stage 17/18 simulator-generated research-only fragments, including
# unique event IDs. No actual broker fill/event is inferred from them.
statement = ledger.settle_buy(
    order_id="study-0001", contract=reviewed_option_contract,
    strike=100.0, option_type="CE", events=events,
)
snapshot = ledger.status()
assert snapshot.live_orders_transmitted == 0
assert not snapshot.approved_for_strategy_promotion
```

### Evidence and production blockers

The inherited Stage 17/18 fragments, metadata and source references can be
operator-forged even if internally consistent. This ledger **cannot certify**
real trades, provider licensing, market depth, costs, order routing or profit.
The ledger does not:
- verify third-party exchange signatures, signed broker fill IDs or ledger
  retention against external tampering;
- implement persistent Risk & Veto order authorization or connect to any
  trading account;
- guarantee multi-machine/network-filesystem SQLite atomicity, cross-device
  replication, disaster recovery backups or cryptographically authenticated
  snapshots;
- reconcile actual broker contract-note fees, SPAN/ELM margin, short options,
  option assignment/exercise, realized P&L or tax reporting;
- calculate market-value equity, release/promotion confidence or live-trading
  readiness.

All earlier PRs remain draft (#6 → #7 → #8 → #9 → #10), and this new PR
must also remain draft until independent validation/signoff. No changes to
`main`, actual capital, risk controls, broker permissions or live trading.
