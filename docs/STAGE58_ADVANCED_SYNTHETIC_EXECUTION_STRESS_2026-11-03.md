# NEXUS TITAN — Stage58 Advanced Synthetic Execution Stress & Transaction Costs

**Date:** 2026-11-03  
**Parent:** Stage57 draft PR #49  
**Branch:** `feature/stage58-synthetic-execution-stress-2026-11-03`  
**Classification:** read-only historical/synthetic simulation; no broker, order gateway, capital transaction, licensed data or production authority

## Design choice: reuse existing code

The codebase already includes:
- `src/nexus_titan/virtual/microstructure.py`: conservative order-book spread crossing, impact, latency drift, queue-ahead and displayed-depth participation with lot-size partial fills
- `src/nexus_titan/cost/charges.py`: configurable **indicative** Indian brokerage, STT, exchange charges, SEBI, stamp duty and GST tariff
- `src/nexus_titan/simulation/options_research_execution.py`: one historical option snapshot fill gated on source-declared option-chain/contract metadata
- `src/nexus_titan/simulation/options_order_reconciliation.py`: option research fragment/order cost reconciliation

Stage58 does **not** duplicate or replace those existing modules. It adds
a reusable, **read-only, multi-snapshot synthetic scenario layer** for
NSE FUTURES and OPTIONS using the same microstructure and fee calculations.
It does not turn either existing shadow-account runner or Stage55 isolated
synthetic ledger into a real execution system.

## Implementation

### `src/nexus_titan/simulation/stage58_execution_stress.py`

`simulate_stage58_synthetic_execution(observations, contract, calendar,
side, requested_lots, costs, microstructure, order_type, limit_price,
max_spread_bps, max_observations)`

Enforces:
1. Explicit `PointInTimeContractSpec` with NSE F&O segment, positive lot,
   freeze quantity and max-lots-per-trade constraints, source-declared
   reviewed contract, active effective-date and nonexpired contract.
   **`source_verified=True` is caller-declared metadata, not
   independent NSE evidence**. No actual contract master is bundled.
2. Explicit `MarketCalendar` in `Asia/Kolkata`, with no after-hours
   or holiday quotes simulated. Its holiday/session configuration
   still needs official point-in-time verification. A default empty
   holiday list is NOT an authentic exchange calendar.
3. One to 40 chronological displayed-depth/quote observations by
   default, unique event IDs, time-zone-aware timestamps identical
   to their book's timestamp, matching contract symbol/tick,
   source-declared separately collected bid/ask depth (not OHLCV
   turnover/volume/OI), positive quote age bounded by the
   `MicrostructureConfig`, configurable spread ceiling, and
   bounded quote/volatility/volume extremes. An invalid *later*
   observation vetoes the entire trajectory before any simulated
   fragment is emitted.
4. BUY/SELL and MARKET or tick-aligned LIMIT requests, whole-lot
   quantities. No naked short or margin admission is represented:
   a SELL is **only a hypothetical execution fragment**, not
   permission to sell inventory that the user does not possess.
5. Calls the existing `MicrostructureSimulator` at **at most one
   simulated fragment per strictly increasing displayed book event**.
   Existing queue-ahead and participation rules limit fillable
   depth and emit partial fills. A no-depth, stale, halted or
   nonmarketable observation does not create an invented fill
   or charge. One snapshot cannot be reused as magically replenished
   depth by feeding it multiple times.
6. Uses the *explicit* `IndianCostConfig` version and effective date
   for each filled fragment. Rejects tariff configurations that are
   invalid even in a zero-fill scenario and refuses fees from
   schedules not yet effective on that quote date. **Do not claim
   these indicative rates match official broker contract notes**.
   Physical settlement, exercised options and broker-dependent fees
   remain outside this model.
7. Computes fragment notional, actual **simulated** fee-per-fragment,
   signed execution shortfall against displayed midpoint and
   spread/impact/latency diagnostics. It also independently estimates
   fees on aggregate filled VWAP/quantity. A **conservative fee reserve**
   selects the higher of fragment fee sum and aggregate estimate,
   **not the sum** (which would double-count tariffs).
8. Conservative friction = selected fee reserve + sum of
   *positive* fragment midpoint shortfalls. A passive queue fill
   with price improvement is reported with negative shortfall
   but **not treated as negative trading cost/profit**.
9. Returns immutable scenario and fragments with exact fill counts,
   fill ratio, residual quantity, cost-schedule version and explicit
   NO-LIVE / NO-IDENTITY / NO-AUTHENTICATED-DATA / NO-GLOBAL-RISK
   flags. Does not reserve a cent from any of Stage19/43/49/53/55
   databases. It does not compute P&L, trade expectancy, options
   Greeks, margin requirement or strategy promotion evidence.

### Tests and smoke

- `tests/test_stage58_execution_stress.py`: equity-index FUTURES and
  OPTIONS BUY/SELL side-specific charges, zero-depth no-fee veto,
  liquidity-limited partial then filled scenarios, queue-ahead
  passive fills and optimistic mid-price avoidance, marketable
  limit guards, fee schedule edition/effective date, no double-count
  between fragment/aggregate tariffs, price impact and depth
  stress sensitivity, no historical/session calendar/expiry
  shortcut, duplicate/out-of-order/mismatched quote snapshot
  clocks, displayed-depth source mismatch, frozen lot limits,
  later invalid snapshot rejecting entire event sequence,
  invalid/outlier input, no live permissions and deterministic
  repeatability.
- `scripts/run_stage58_execution_stress_smoke.py`: does not write
  files, connect market providers or call trading APIs. Uses two
  synthetic top-of-book quotes for an illustrative NIFTY-like
  OPTIONS contract, demonstrating **baseline complete 4-lot
  simulated fill**, a stressed participation/market-impact run
  with no greater fill quantity, and a no-depth/no-fee run.
- Stage52 read-only source inventory includes the Stage58 scenario
  class as a structural check. This is NOT an independent security
  or live-data source-provenance attestation.

## Financial/reporting meaning

The model's **conservative_execution_friction** is an estimate of
transaction-cost drag for the filled fragments, NOT total economic
loss, exact real broker charges, a verified quote or evidence that
a strategy is profitable. A stressed scenario filling fewer lots
cannot be compared as though its P&L were identical to the baseline;
unfilled remainder is an opportunity cost/risk state that needs
separate assumptions.

Existing Stage55 isolated cash ledger uses different synthetic
order-event semantics and is deliberately NOT automatically mutated
by Stage58. A future verified integration requires one authoritative
capital/execution ledger, authentic time-synchronized quotes and
fills, independent identity, formal risk controls and explicit
owner-approved reconciliation.

## Verification

```bash
python scripts/run_stage58_execution_stress_smoke.py
python -m pytest -q tests/test_stage58_execution_stress.py
python -m pytest -q
```

Only after FINAL PR-head CI Python 3.11/3.12/3.13 and existing
Stage25 synthetic integration smoke pass should Stage58 be called
a **verified offline development milestone**. Earlier green tests
on stacked draft PRs are not proof of an integrated `main` branch.
No real licensed NIFTY/BANKNIFTY F&O historical feed has been
integrated or backtested here. The project remains TRADING-ONLY,
with all real-money/live execution and autonomous strategy
promotion unavailable.

## Next proposed Stage59

Integrate a provider-independent historical F&O **data quality and
licensing gate** with verified point-in-time contract master,
exchange calendar, signal timestamps, corporate events and
strict missing/duplicate/stale quote detection. User-provided
historical data can be added after the foundation stage and
license/source suitability confirmed. Avoid guessing NSE lot
sizes, margin or fees from today's values for older contracts.

**Keep PR DRAFT/UNMERGED; `main` unchanged until owner and
prospective merged-tree review.**
