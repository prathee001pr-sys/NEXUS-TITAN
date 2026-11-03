# NEXUS TITAN — Stage60 Purged OOS F&O Research Evidence (Offline / Synthetic)

**Date:** 2026-11-03  
**Parent:** Stage59 draft PR #51  
**Branch:** `feature/stage60-purged-fo-oos-research-2026-11-03`  
**Classification:** research-only, no genuine multi-year F&O data, NO actual fills, P&L, licensed vendor attestation, broker connections, approval or strategy promotion.

## Scope and rationale

Existing NEXUS TITAN already has `BacktestEngine`,
`split_chronologically`, `evaluate_out_of_sample`,
`rolling_walk_forward_validation`, `run_backtest`, Stage26/44
OPTIONS historical quote-chain preflights, Stage58 conservative
order-book/fee execution stress and Stage59 strict futures OHLCV
CSV preflight. This stage deliberately **does not clone these modules**.

A futures **OHLCV candle is not a real executable order book**.
It does not contain available bid/ask depth, spread at the signal
timestamp, true queue position, price impact, executed order fills,
brokerage contract-note tariff, exchange margin or actual portfolio
capital. Running a standard long-only equity cash backtester on
index-futures OHLCV and naming its output a verified NIFTY/BANKNIFTY
F&O performance result would misstate the evidence.

Stage60 therefore adds the **OOS evidence-planning and leakage-review
foundation** with a fully fixed, simple, no-order directional
diagnostic. A future evidence-verified F&O strategy backtest remains
pending licensed historical quotes, official point-in-time contracts,
option chain, separately recorded executable depth and realistic
charges/margin. Do not equate Stage60 completion with end-to-end
backtesting completion.

## Implemented

### `src/nexus_titan/research/stage60_purged_oos.py`

`inspect_stage60_purged_oos(history, contract, calendar, config,
option_catalog=None)` accepts only an already inspected
`Stage59FuturesHistory` and matching `PointInTimeContractSpec`
/ `MarketCalendar` (India timezone).

- Rechecks futures symbol, underlying, expiry, **the exact source
  inspected lot size and tick value** preserved from Stage59,
  all timestamp/identity/source/grid consistency, single
  configured exchange session/expiry/effective window and the
  existing `inspect_candle_batch` OHLCV quality result. Its
  source flags remain declared claims; no external attestation.
- Fixed-parameter moving-average trend observation:
  `fast=3, slow=5` closes by default. At each HOLDOUT origin
  the diagnostic uses only prices available **at or before**
  that origin's close. Future label is the **next completed
  candle's close-vs-current-close direction**. This is a
  **directional label** and *not* the price of an order fill.
  The default fixed parameters are not trained/optimized by
  the function; changing them after observing holdout accuracy
  is data snooping and invalidates independent evidence claims.
- Chronological rolling folds:
  default initial past-history bars 12, mandatory embargo 2,
  held-out window 8 bars, up to 3 folds, at most 1000
  previously inspected single-session candles. The train
  segment ends BEFORE the embargo. Both forecast origin AND
  target label are required inside **the same** holdout
  fold; signals with a target outside the fold are excluded.
  Prior OOS data becomes past history in later folds, but
  no model fitting occurs here.
- No signal when fast and slow averages are equal; a
  nonneutral prediction followed by a flat next candle
  is counted as a MISS, not a win. Counts / hit-rate are
  in `Stage60Fold` and `Stage60OfflineResearchReport`.
- Defaults to 30 OOS predictions minimum before even marking
  the purely descriptive sample size as enough. If enough,
  the verdict is **EXPLORATORY_SAMPLE_ONLY**, never
  `ROBUST`, `APPROVED` or strategy promoted. A successful
  synthetic directional hit rate is not evidence of live
  profitability, independent repeatability or realistic
  execution.
- Optional Stage44 `HistoricalCatalogResult` **only**
  checks the declared option history temporal window and
  matching underlying symbol, plus negative authority flags.
  This does **not** synchronize individual futures bars
  with CE/PE quotes or make an options trading signal.
  Declared option metadata itself can be forged by a caller
  and still requires Stage26/44 importer and external vendor
  review. No option-execution simulation or option P&L is
  calculated in Stage60.
- `local_evidence_digest` is SHA256 over selected supplied
  research inputs and fold boundaries; not an identity
  signature, source-licence authentication or immutable
  audit proof.
- Every report explicitly sets false:
  `dataset_source_authenticated`,
  `licence_authenticated`,
  `official_historical_lot_master_authenticated`,
  `exchange_calendar_authenticated`,
  `options_quotes_cross_instrument_synchronized`,
  `executable_depth_verified`,
  `margin_and_funding_verified`,
  `execution_costs_or_broker_fills_verified`,
  `real_fo_backtest_performance_verified`,
  `strategy_promotion_authorized`,
  `capital_ledger_updated`,
  `independent_global_risk_veto_enforced`,
  `live_trading_enabled`, `production_ready`.
  `live_orders_transmitted=0` always.

### Stage59 integration change

`src/nexus_titan/data/stage59_futures_history.py` now carries
`inspected_contract_lot_size` and
`inspected_contract_tick_size` in the frozen successful
preflight result, derived from the exact source-declared
contract used for validating the original futures CSV.
Stage60 refuses a later downstream request with different
lot/tick metadata. This is **same-declaration consistency**,
NOT independent verification against historical NSE circulars.
Existing Stage59 code/tests remain backward compatible.

### Tests, source inventory and script

- `tests/test_stage60_purged_oos_research.py`:
  synthetic NIFTY/BANKNIFTY; exact train/embargo/holdout
  boundaries and no cross-boundary targets; deterministic
  rising and flat scenarios, zero-signal/zero-denominator,
  future-target mutation does not alter earlier predictions,
  no P&L/order APIs, changing future tail does not alter
  earlier fold, insufficient sample remains NO-PROMOTION,
  unsigned/forged vendor/lot/tick/source/expiry claims blocked,
  changed holiday calendar, false option-source promotion,
  deliberately missing/malformed options catalog metadata,
  per-fold deterministic results and no source-file mutation.
- `scripts/run_stage60_purged_oos_smoke.py`: produces
  disposable fabricated 46-bar NSE-like FUTURES CSV for
  NIFTY and BANKNIFTY, runs the Stage59 integrity importer,
  performs Stage60 OOS diagnostic (three 8-bar held-out
  folds each, with two embargo bars), prints only local
  directional metrics and explicit negative trading flags.
  Never transmits broker orders, connects vendors or writes
  real user databases.
- Stage52 no-write `release_security_audit.py` source
  inventory now recognizes Stage60 report/config types.
  AST structural inventory alone is not a runtime security
  proof and cannot fence legacy direct order/fill APIs.

## Limits that still BLOCK project production

1. **Real licensed historical NIFTY/BANKNIFTY F&O data**:
   absent; no official vendor feed or 15-year historical
   option/futures series ingested.
2. **Historical point-in-time instrument master and holidays**:
   operator-declared; current lot/tick checks are not
   independently authenticated.
3. **Real option/futures execution**: no historical true
   depth, authenticated fills, fee schedule by date/broker,
   margin/funding, option exercises, futures roll slippage
   or multi-leg portfolio reconciliation.
4. **Validated trading performance**: none in Stage60.
   Directional next-close hit rate is NOT a backtest
   profit factor, net ₹P&L, Sharpe or executable edge.
5. **Global security**: existing Stage43/48/49/53/55
   capital/order domains are not one authoritative ledger,
   older Python APIs remain bypassable; real human identity,
   mandatory independent risk control, broker credential
   isolation and production owner approval still missing.
6. **Git integration**: multiple stacked draft branches
   remain unmerged and require prospective combined-tree CI,
   semantic conflict resolution and documented owner review.

## How to reproduce

```bash
python scripts/run_stage60_purged_oos_smoke.py
python -m pytest -q tests/test_stage60_purged_oos_research.py
python -m pytest -q
```

Only call this a tested Stage60 offline coding milestone
after the **final PR HEAD** GitHub Actions CI succeeds for
Python 3.11/3.12/3.13 and existing Stage25 synthetic smoke.
Neither CI nor self-declared data evidence authorizes
real-money trading, shadow performance claims, strategy
autopromotion or a production release.

## Recommended Stage61

Complete a **no-fill prospective validation and data-evidence
coverage scorecard** joining Stage58 cost/depth research with
Stage59 futures and Stage26/44 options metadata, ensuring no
cross-instrument apparent execution if bid/ask depth or contract
evidence is missing. Add risk/governance checks and explicit
reviewable blockers; preserve real-data upload as a separate,
owner-controlled step. Only after genuine licensed market
history is supplied should real-data performance be evaluated
with correct fees, slippage, expiry, lot, margin and OOS gates.

**Leave PR DRAFT/UNMERGED; do not touch live trading or `main`.**
