# Stage 24 — Offline Long-Options SELL/Exit, FIFO Realized P&L and Reconciliation

**Status:** Research-only implementation, subject to independent review. All
values in automated tests are synthetic. No licensed NSE market data, real
broker fills, paper broker session or production orders are involved.

## What is implemented

Stage 24 adds `src/nexus_titan/shadow/long_option_exit_research.py` to
**the existing Stage 19 SQLite research ledger** without changing its public
BUY/Reserve or Risk & Veto implementation.

1. `simulate_and_settle_long_exit(..., paper_trading_enabled=True)`: opt-in
   `Action.PAPER_TRADE` policy check; zero trade permissions by default.
   Validated NSE research quote-history and separately declared timestamped
   bid-side depth are passed to Stage 17 simulator with `side="SELL"`.
   Only **currently owned long CE/PE options** of the *exact same contract
   identity* can be closed; no naked short positions, new option shorts,
   futures, margin borrowing, actual orders or auto-promotions.
2. `reconcile_options_research_order(side="SELL")`: independently rechecks
   partial/filled quantities, lot multiples, remaining units, estimated
   brokerage/STT/GST/exchange/stamp fees, event ID and replay boundaries
   using the existing Stage18 order statement.
3. A **single SQLite `BEGIN IMMEDIATE` transaction** records the exit
   order, globally unique simulated event ID, net cash proceeds, remaining
   inventory and immutable-in-application SHA-256 chained audit event.
   It replays and rechecks *all* buys and exits **before committing**.
   No new position or fee is recorded for an `UNFILLED` attempt.
4. **FIFO cost basis** for every existing Stage19 BUY is reconstructed
   from original audit `debit_cents` (gross BUY premium **plus estimated
   entry fees**) and the linked contract/instrument key. On a partial SELL,
   entry cost is allocated in integer cents to the oldest units, with the
   remainder preserved for the final slice; rounding cannot create or
   destroy remaining basis.
5. `realized_net_pnl = SELL gross proceeds - SELL estimated fees -
   allocated full BUY cost`. Losses are negative (never silently clipped).
   `report_research_long_portfolio(ledger)` shows remaining quantity/cost
   and **realized** net P&L; no external price source is used for unrealized
   mark-to-market.
6. Local SQLite restart and Stage20 backup/reopen preserve all previous
   BUY/SELL cash and positions. Replay validates cross-order event IDs,
   positive quantities, chronological BUY/SELL audit ordering, FIFO
   attribution, accumulated realized P&L and **cash/inventory conservation**.
   Backdated sell attempts fail without state mutation.

### Synthetic example: no exchange fill, no broker order

```python
from nexus_titan.shadow.long_option_exit_research import (
    simulate_and_settle_long_exit, report_research_long_portfolio,
)

# research_ledger already holds a Stage 23 simulated *long* option position
exit_result = simulate_and_settle_long_exit(
    ledger=research_ledger,
    order_id="DEMO-EXIT-001", event_id="SYNTH-EXIT-001",
    history=synthetic_exit_option_chain_history, contract=declared_contract,
    calendar=operator_supplied_nse_calendar, observed_at=research_timestamp,
    strike=100.0, option_type="CE", lots=2,
    depth=synthetic_bid_side_displayed_depth,
    paper_trading_enabled=True,
)
portfolio = report_research_long_portfolio(research_ledger)
assert exit_result.live_orders_transmitted == 0
assert not portfolio.approved_for_strategy_promotion
```

This `paper_trading_enabled` switch opts into **local research accounting
only**. It does not turn on a broker, route a paper account order or grant
real-money trading.

## Important integration limitation

**Existing Stage20 and Stage21 "BUY-only" day-close validators do NOT
support legitimate cash increases and inventory decreases caused by an
exit.** They intentionally continue to reject these changes and are
**not weakened in Stage24**. The new Stage24 portfolio report provides
post-exit *per-account trade accounting*; a later versioned multi-day
validation path must explicitly account for SELL proceeds, FIFO inventory,
realized P&L and unmatched trades before claiming cross-session reporting.

The existing Stage23 BUY admission guard still requires a flat research
account, and Stage19 direct `reserve_buy` remains a separate research API.
Stage24 does not make overall order admission globally risk-authorized.
Unrealized P&L, exercise/assignment/expiry settlement, margin, short options,
tax treatment, market-data licences, independently reviewed broker charges
and realistic queue/execution calibrations remain pending.

## Validation and evidence discipline

The release gate remains **BLOCKED_EXTERNAL_EVIDENCE** or
**BLOCKED_STRUCTURAL_VALIDATION** until genuine independently reviewed
market data, risk authorization, broker-charge evidence, historical
validation, real-feed multi-day shadow records and operator signoff exist.
The audit chain detects accidental changes only, not a malicious
administrator with database write access. The Stage24 replay uses
private Stage19 transaction/audit helpers in a deliberately narrow,
local SQLite research adapter; refactoring should introduce a
versioned public interface before production integration.

The branch is a stacked **draft** successor to PR #15; `main` stays
unchanged. Do not auto-merge, enable broker access, or promote strategies.
