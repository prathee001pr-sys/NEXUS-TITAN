# NEXUS TITAN — Stage59 Historical F&O Data Quality and Adapter Readiness

**Date:** 2026-11-03  
**Base:** Stage58 draft PR #50  
**Branch:** `feature/stage59-futures-history-quality-preflight-2026-11-03`  
**Classification:** local synthetic / operator-declared CSV structural preflight; NO REAL HISTORICAL DATA UPLOADED.

## Existing functionality reused rather than rewritten

The stack already includes provider-independent `OHLCVCandle`,
`CandleQuery`, `MarketDataSource`, `inspect_candle_batch`,
`MarketCalendar`, `PointInTimeContractSpec`,
`historical_fo_bundle.py` (Stage26 single options-chain contract)
and `historical_fo_catalog.py` (Stage44 multi-contract options-chain
catalog). These existing option-chain paths remain intact, with
previous CI regression tests preserved. The user intends to
source/upload genuine historical data later; this stage does
not fetch/import unknown GitHub datasets as authentic exchange data.

A genuine gap is the **NIFTY/BANKNIFTY FUTURES** intraday per-expiry
OHLCV partition, distinct from the options quote-chain manifests.
Stage59 builds that bounded research-only preflight.

## New module

`src/nexus_titan/data/stage59_futures_history.py`

- `Stage59FuturesCSVDeclaration`: explicit per-file SHA256, dataset
  identity, provider, rights/licence, calendar, contract references,
  single trading-day declared starting/ending candle opens, interval
  `1/5/15/30` minutes, a `DECLARED_WINDOW` versus `FULL_SESSION`
  coverage claim, and a dataset-class label.
- `preflight_stage59_futures_csv(...)`: validates an existing local
  CSV basename with no traversal/symlink, bounded size and rows,
  expected SHA-256 of the EXACT read bytes, UTF-8-sig encoding,
  **exact normalized CSV schema**, explicit offset-aware ISO times,
  fully ordered non-duplicate candle open timestamps, session-open
  grid alignment and every expected declared in-window slot.
- All data pertains to one NSE FUTURES contract with underlying
  **NIFTY** or **BANKNIFTY**, supplied point-in-time effective date,
  expiry, symbol, lot size, positive tick, and source-declared
  contract evidence. Every row must match that declared identity.
  A changed lot size/expiry requires a new separate partition.
- Uses exact `Decimal` positive price and tick alignment, positive
  OHLC bounds, nonnegative integral volume and open interest,
  and restrictive normalized decimal/integer grammar. The existing
  `OHLCVCandle` object and `inspect_candle_batch` quality gate
  are used again after CSV parsing.
- A `FULL_SESSION` claim is only accepted when the supplied
  **single exchange session**, on that one trading day, is
  completely covered by one interval-sized bar at each opening.
  **NSE regular session is 09:15–15:30 (375 minutes)**: 1m, 5m
  and 15m align exactly. Standard **30m bars cannot certify the
  whole regular session** without inventing a final 15-minute
  segment. 30m partitions can still be researched using
  `DECLARED_WINDOW` for a strictly aligned partial session.
- All CSV values are checked **before** returning a partition.
  Duplicate/missing/late/off-grid records reject the entire
  partition. Any extra interval/candle after the declared
  bounds is rejected; missing first or last records cannot
  be silently excused.
- `Stage59FuturesHistory` includes a `fetch_candles(CandleQuery)`
  implementation of the existing provider-independent
  `MarketDataSource`-style API, returning only aligned and
  complete **in-memory** subsets of the previously audited
  window. A query outside declared coverage or with another
  symbol/timeframe raises instead of quietly returning incomplete
  market history.
- **No folder scanning, internet access, automatic unknown-source
  archive extraction, file writes, broker calls, account mutation
  or live trading.** The original file bytes are not modified.

### Normalized input CSV

The expected header, in this exact order:

```csv
timestamp,symbol,exchange,segment,expiry_date,lot_size,open,high,low,close,volume,open_interest
2026-11-02T09:15:00+05:30,NIFTYFUT,NSE,FUTURES,2026-11-05,25,100.00,101.00,99.00,100.05,1000,2000
```

This is a **fabricated sample**, not an official NSE price/lot
record. A vendor-specific adapter must normalize its actual
licensed format to this schema (the adapter is NOT implemented
here) and attach verifiable historical contract metadata,
calendar source and licence evidence. Row timestamps represent
**candle opens**, with explicit UTC offset, not candle closes.
Volumes/open-interest are not indicative of executable bid/ask
depth and can NEVER be used as a queue-fill substitute.

## Tests and offline smoke

- `tests/test_stage59_futures_history.py`: parameterized
  NIFTY/BANKNIFTY and 1m/5m/15m/30m partial-window QA;
  verified relative to SUPPLIED 1m/5m/15m full-day grids;
  explicit rejection of false 30m full session; all-hash and
  file mutation, missing/extra/duplicate/out-of-order/misaligned
  candles, bad OHLC high/low, NaN/Infinity, non-tick prices,
  huge integers, wrong lot/OI/expiry/segment/underlying, naive
  and wrong timestamp offsets, source path traversal/symlink,
  invalid UTF-8/headers, untrusted "licensed" labels, holiday/
  market session/expiry gaps, resource caps, read-only source
  bytes and strict in-memory query bounds.
- `scripts/run_stage59_futures_history_smoke.py`: constructs
  two ephemeral 3-row synthetic FUTURES datasets (one each
  NIFTY/BANKNIFTY) and proves normal structural acceptance,
  altered-hash veto and missing-middle-minute veto even when
  a replacement digest matches the tampered two-row CSV. It
  does NOT accept real market feeds, approve backtests or
  write any user dataset to the repository.
- Stage52 structural read-only code inventory also recognizes
  the new `Stage59FuturesHistory.fetch_candles` interface.

## What passes and what remains unverified

| Item | Stage59 assessment |
| --- | --- |
| Exact local CSV bytes vs operator SHA-256 | Check implemented |
| Single-contract futures symbol, expiry, lot, tick, valid date window | Check implemented |
| Timezone-aware, ordered, nonmissing per-session expected window | Check implemented |
| Full exchange session relative to supplied local calendar | Check implemented where declared |
| External vendor authentication | **FALSE / not implemented** |
| Licence rights and vendor terms | **FALSE / require external evidence review** |
| Official historical contract master/lot/tick | **FALSE / operator declarations only** |
| Official historical exchange holidays/special trading sessions | **FALSE / supplied calendar only** |
| Multi-year NSE history or every expired series | **NOT PRESENT** |
| Option-chain bid/ask snapshots | Existing Stage26/44; no new dataset |
| Futures tick-by-tick/order book market depth | **NOT PRESENT** |
| NSE contract-note charges, margin, taxes, exercise/settlement | **NOT AUTHENTICATED** |
| Real data backtest / profitability / strategy promotion | **NOT VERIFIED OR ALLOWED** |
| Live order transmission, execution approval or global Risk & Veto | **DISABLED / unimplemented** |

An operator can claim `LICENSED_EXCHANGE_HISTORY` and use
`source_verified=True` in an in-memory contract, but the
returned flags remain false: declared strings/hashes do NOT
authenticate a licence, vendor, source file, official
instrument master, or real exchange price. Real-data vendor
evidence, period coverage and terms must be independently
reviewed before any evidence-based strategy validation.

## Verification

```bash
python scripts/run_stage59_futures_history_smoke.py
python -m pytest -q tests/test_stage59_futures_history.py
python -m pytest -q
```

Only **final PR-head CI** on Python 3.11, 3.12 and 3.13,
including existing Stage25 synthetic integration smoke,
qualifies this as a tested **offline code milestone**.
CI never establishes current NSE data provider licensing,
real monetary readiness, market performance, or cryptographic
proof that operator-declared source metadata is true.

## Stage60 recommended next

Bring the previously built option-chain research preflights
(Stage26/44) and futures historical adapter into **a single
provider-independent, no-write backtest evidence planner**,
while preserving the distinct nature of OHLCV vs independently
observed top-of-book depth. Add per-expiry/roll and
out-of-sample boundaries, transaction costs, explicit held-out
periods and conservative no-depth/no-real-fill assumptions.
Do not infer fills from OHLCV volume or claim genuine F&O
performance until independent real licensed data and
supporting contract/fee evidence have been obtained.

**All stacked PRs remain draft and unmerged. No live trades.**
