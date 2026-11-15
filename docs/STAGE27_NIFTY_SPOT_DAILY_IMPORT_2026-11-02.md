# Stage 27 — Safe NIFTY 50 Spot-Daily Import (NSE-Style CSV)

**Scope:** NIFTY 50 underlying **spot index daily OHLC**, NOT NIFTY/BANKNIFTY
F&O contracts, 1-minute option-chain snapshots, a broker trade, or proof of
licensed NSE vendor origin. Added to the Stage26 branch as a separate draft PR.

## Problem solved
The typical seven-column CSV has whitespace-padded names:
`Date ,Open ,High ,Low ,Close ,Shares Traded ,Turnover (₹ Cr)`.
Dates appear as `02-NOV-2026`, rows may be newest-first, and
`Shares Traded` is **aggregated index activity**, not an exchange
options/futures contract quantity.

The original canonical TITAN `load_canonical_data` strictly expects
`timestamp,open,high,low,close,volume` and increasing ISO timestamps.
Copying the seven-column CSV directly into the regular futures/options
backtest would be misleading and normally fail canonical validation.

## Implementation
- `src/nexus_titan/data/nifty_spot_daily.py`:
  - Strict UTF-8/BOM CSV, exact seven headers with whitespace normalized,
    full SHA-256 for reproducibility, optional separately obtained expected
    checksum, bounded 2 MiB file and 5000 records by default
  - Entire file validated for ISO-unambiguous `DD-MON-YYYY`, unique dates,
    monotone source order, finite positive OHLC, valid candle bounds,
    nonnegative integer aggregate shares and nonnegative turnover
  - Explicit operator declaration required for any weekend trading date;
    neither Sundays nor NSE holidays are independently authenticated
  - Converts descending source to chronological immutable
    `CanonicalCandle` rows, timeframe `1d`, symbol `NIFTY`
  - Canonical time `15:30:00+05:30` is only a daily bar-close **label**,
    not verified quote/event timestamp
  - Weekday absences counted separately (might represent real NSE holidays)
  - Returns unverified source/provenance/option-data/strategy-promotion status.
- `scripts/import_nifty_spot_daily.py`: optional read-only preflight;
  converts to **new** canonical CSV with exclusive file creation
  (`open("x")`) so existing files/original source are never overwritten.
  No automatic trading, signal execution or broker integration.
- `tests/test_stage27_nifty_spot_daily.py`: tests both input orders,
  invalid/corrupt rows, unknown weekdays, explicit weekend session, duplicate
  dates, tamper-detected digest, source immutability, alternate headers,
  invalid resource limits, CLI subprocess result and canonical parser
  compatibility.

## How to use on Android/Replit or PC

Place your file **outside** the Git repository or a `data/private/`
folder covered by a user-managed Git ignore rule. Do not commit a file
until its vendor redistribution rights are confirmed.

```bash
python scripts/import_nifty_spot_daily.py \
  --csv '/path/to/your-NIFTY50-history.csv' \
  --special-session 2026-02-01 \
  --normalized-out '/tmp/nifty-spot-1d-canonical.csv'
```

Use `--sha256 YOUR_INDEPENDENT_SOURCE_HASH` only with an independently
recorded checksum. The special Sunday-session date is an **explicit user
declaration**, not verification that NSE actually held that session.
The converter rejects other weekends unless each is separately declared.

On success it prints JSON with source SHA-256, first/last session, count,
indicated missing weekdays, input/normalized order and spot close-to-close
return. All source authenticity and trading permission fields remain false.

The optional converted CSV is valid for TITAN's canonical **spot daily
research pipeline**. *Do not* simply run it as `EQUITY_DELIVERY` NIFTY
and call the resulting estimated rupee figures exchange-executable P&L:
the NIFTY index cannot be directly purchased at index price and actual
futures/options require separate point-in-time contracts, expiry, lots,
bid/ask, charges and licensed history.

## External data & risk blockers
1. Source/vendor attribution, legal data-use licence and independent NSE
   holiday/calendar audit remain outstanding.
2. Only daily spot candles, not 1-minute historical futures/options prices.
3. The seven-column input's aggregate shares and turnover cannot substitute
   for individual F&O contract volume/open interest/depth.
4. Stage23 risk-gated paper research is still an optional wrapper; Stage19
   direct `reserve_buy` can be called without globally mandatory risk
   authorization. Production needs an unbypassable atomic admission gate.
5. Full order lifecycle execution realism and real-feed multi-day shadow
   validation remain release-blocking; no live trading enabled.

**Tests are synthetic and independent of the user's original file.**
Uploaded source data is intentionally **not checked in to GitHub**.
