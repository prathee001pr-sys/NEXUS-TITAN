# Phase 7 — Options Research Execution Bridge (2026-11-02)

## Purpose

Pure offline scenario evaluation from the **already-validated** historical
option-chain snapshots in draft PR #8. This changes neither production trading
path nor the authoritative Risk & Veto controls. Live orders transmitted: **0**.

`simulate_historical_option_fill` requires:

- `ResearchOptionChainHistory` (from `assemble_research_option_chain_history`);
  **the entire history is revalidated** to avoid forged dataclass bypasses.
- An NSE OPTIONS `PointInTimeContractSpec` with operator-declared reviewed
  metadata, a supplied NSE session calendar, exact observation timestamp,
  contract strike and CE/PE option type.
- `OptionDisplayedDepth` containing **independent displayed bid/ask quantities**
  and timestamp with evidence reference and an explicit source declaration.
  Historical volume/open interest **is not a substitute for top-of-book depth**.
- Side, lots and MARKET or LIMIT order type; optional existing
  `MicrostructureConfig`, `IndianCostConfig`, and strict quote-depth skew limit.

### Behavior

- Rejects invalid source declarations, fake promotion permission, bad history,
  stale/unsynchronized depth, wrong contract/expiry, and bad order parameters.
- Respects tick, lot, freeze and per-trade limits; marketable orders consume
  **at most the configured percentage of displayed depth**, rounded down to
  whole lots; insufficient depth gives an explicit UNFILLED result.
- Reuses `MicrostructureSimulator` for spread crossing, volatility-based
  impact, latency drift and conservative partial fills. Passive LIMIT orders
  have no invented queue-trade volume, so fills are not presumed.
- Calls existing `calculate_indian_trade_costs` for **filled quantity only**,
  keeping BUY and SELL schedule components separate.
- Reports execution price, filled/residual lots, notional, fees,
  *signed* shortfall relative to mid-quote and
  `total_estimated_friction = fees + shortfall`. This metric does not double
  charge the spread; it can be negative for price improvement and is **not P&L**.
- No-fill events incur zero estimated fees and do not create positions.
- Returns immutable research results with `approved_for_strategy_promotion=False`
  and `live_orders_transmitted=0`.

### Example

```python
from nexus_titan.simulation.options_research_execution import (
    OptionDisplayedDepth, simulate_historical_option_fill,
)
from datetime import datetime

t = datetime.fromisoformat("2026-11-02T09:16:00+05:30")
depth = OptionDisplayedDepth(
    as_of=t, bid_quantity=400, ask_quantity=400,
    source_reference="evidence/reviewed-depth-feed",
    source_declared_verified=True,  # operator declaration only
)
result = simulate_historical_option_fill(
    history, contract=reviewed_contract, calendar=reviewed_calendar,
    observed_at=t, strike=100.0, option_type="CE", side="BUY",
    lots=2, depth=depth,
)
assert result.live_orders_transmitted == 0
```

**All example quotes, metadata and trading levels are synthetic.**

## Release blockers

- A supplied `source_declared_verified` flag and source string **do not
  authenticate** vendor identity, data licence, or source packet timestamps.
- Tick-derived model fills are estimates; depth can be cancelled before execution.
  No multi-level order book, trade-print replay, broker queue position, exchange
  latency measurements, market halts, auction behavior, real margin or lifecycle
  reconciliation are established by this function.
- `IndianCostConfig` is indicative, not a broker contract note or verified
  effective-date charge schedule. Fragment-level fees may differ from broker
  order-level rounding/caps.
- No automatic trade placement, position bookkeeping, P&L, stop execution,
  strategy promotion, or authorization. Shadow trading still needs explicit
  human risk/release review and separate multi-day evidence.
- All upstream PRs remain draft: Stage 1–15 PR #6, option-chain importer PR #7,
  historical continuity PR #8, then this PR. Do not merge into `main`
  without external gates and signoff.
