# Phase 7 — Options Research Order Reconciliation (2026-11-02)

## Purpose

An **offline, pure, bounded** reconciliation layer on top of the Stage 17
`simulate_historical_option_fill` output. It compares multiple simulated
fragments of **one** option order and makes a cash/inventory **scenario
projection**. It does not connect to `VirtualAccount`, broker execution,
authoritative risk permissions or live trading.

API:
`nexus_titan.simulation.options_order_reconciliation.reconcile_options_research_order`

Inputs:
- `ResearchFillEvent(event_id, observed_at, fragment)` in strictly
  increasing, timezone-aware chronological order.
- A single NSE OPTIONS point-in-time contract with operator-declared reviewed
  source metadata, strike/CE-PE/side, and requested lots.
- Configurable `starting_cash` (default **₹50,000**, not fixed),
  `starting_inventory_quantity` (default 0), and explicit optional
  `IndianCostConfig`.

## Core invariants

1. **No double fills:** unique event IDs; positive expected requested quantity
   equals remaining quantity from the previous fragment; fills cannot exceed
   the remaining order; filled and unfilled quantities must be lot-aligned.
2. **No invented fees:** UNFILLED events have no execution price, charges or
   notional. Each filled fragment's price, notional, fees and friction are
   cross-checked with the declared cost schedule.
3. **No fake risk authorization:** any fragment carrying a non-zero live order
   count or a true strategy-promotion flag is rejected.
4. **Expiry/effectivity:** all events must be inside the contract's date window,
   prior to expiry and on the same India-local date.
5. **Conservative fees:** the engine separately computes the sum of
   per-fragment charges and a hypothetical VWAP order-level cost. It reserves
   the **larger** estimate rather than incorrectly summing both models.
   Brokerage-specific minimums, per-order rounding and actual statutory
   schedules still need external evidence and reconciliation.
6. **Capital / long-only inventory:** BUY premium+reserved fees cannot exceed
   virtual cash. SELL is accepted only when the declared *existing long-option
   inventory* covers the **entire requested quantity**, so naked short-sale
   margin is not accidentally implied. These are post-simulation checks,
   **not an order admission gate**.
7. Output is immutable and always carries
   `live_orders_transmitted=0` and
   `approved_for_strategy_promotion=False`.

## Example

```python
from datetime import timedelta
from nexus_titan.simulation.options_order_reconciliation import (
    ResearchFillEvent, reconcile_options_research_order,
)

# 'first_fragment' is a PARTIAL result for four lots; 'second_fragment'
# is a second simulated result requesting exactly the residual lots.
events = [
    ResearchFillEvent("sim-001", observed_at, first_fragment),
    ResearchFillEvent("sim-002", observed_at + timedelta(seconds=1), second_fragment),
]
report = reconcile_options_research_order(
    events,
    order_id="research-order-1",
    contract=reviewed_contract,
    strike=100.0,
    option_type="CE",
    side="BUY",
    requested_lots=4,
    starting_cash=75000.0,
)
assert report.live_orders_transmitted == 0
```

**All example prices, quantities, balances and source references are
synthetic research fixtures; they are not actionable trading levels.**

## Not implemented / release blockers

- Source-of-truth broker/exchange fill IDs, settlement/position reconciliation,
  durable replay protection across process restarts, per-order brokerage
  attribution, order admission permission, real inventory provenance,
  multi-order cash reservations, margin/SPAN/ELM, P&L, financial reporting,
  late/cancelled fills, or time-in-force state transitions.
- Strict event ID uniqueness operates only **inside one invocation**; it is
  not a durable exactly-once ledger.
- Caller-created immutable fragment objects can be fabricated even when
  internally consistent. They are not cryptographic evidence of an exchange
  fill; the function is for **offline scenario research only**.
- Regulatory charges are *indicative*, broker-specific order caps/rounding and
  real signed contract-note fees not independently verified. Capital is not
  actual collateral/margin and SELL inventory identity is caller-provided.
- No automation/promotion, order execution, broker network, or change to
  authoritative Risk & Veto. No changes to `main`. Draft review stack:
  PR #6 → #7 → #8 → #9 → this candidate.

Next engineering increments: durable mock-ledger/replay testing with explicit
versioned events; multi-order virtual reservation; charge-source validation;
real broker-data reconciliation in a supervised paper-only environment.
