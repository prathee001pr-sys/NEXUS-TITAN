# NEXUS TITAN — Stage 44 Historical F&O Catalog Preflight

**3 November 2026 | Stacked draft on Stage43 PR #35**

## What this implementation does

- Extends the existing Stage26 *single-contract* option-chain CSV audit to an
  explicit, bounded **multi-contract research catalog** without rewriting the
  Stage26 importer or touching protected `main`.
- `src/nexus_titan/data/historical_fo_catalog.py`: checks unique dataset IDs,
  contract key and expiry, timestamp windows, point-in-time effective dates,
  overlapping partitions, replayed file hashes, per-file and aggregate budgets;
  invokes the existing strict Stage26 hash, session, quote, and 1-minute grid
  checks for every listed partition.
- `scripts/run_stage44_historical_fo_catalog.py`: read-only CLI for offline
  per-contract manifests and bounded local directories. No actual F&O data is
  downloaded, uploaded, copied or committed to GitHub.
- `tests/test_stage44_historical_fo_catalog.py`: synthetic NIFTY and BANKNIFTY
  samples, non-overlapping valid partitions, overlap, metadata, expiry,
  duplicate IDs, changed-file checksum, caps, deterministic nonmutation and
  CLI path traversal tests.

**All vendor references, `source_verified=True` labels, local hashes and
calendar declarations are still untrusted assertions.** None authenticate
license, vendor, NSE metadata or historical calendar. Full-day/full-contract/
15-year coverage is not established merely by valid declared windows.
No live trading, automatic promotion or production readiness is granted.

## Example (synthetic layout; not genuine exchange data)

```text
/tmp/titan-catalog/
  catalog.json
  nifty_nov05.json
  bank_nov05.json
  nifty_nov05/
    snapshot_0915.csv
    snapshot_0916.csv
  bank_nov05/
    snapshot_0915.csv
    snapshot_0916.csv
```

`catalog.json`:

```json
{
  "partitions": [
    {"directory": "nifty_nov05", "manifest": "nifty_nov05.json"},
    {"directory": "bank_nov05", "manifest": "bank_nov05.json"}
  ]
}
```

Each inner JSON file uses the **existing Stage26** manifest format described in
`docs/STAGE26_HISTORICAL_FO_SOURCE_PREFLIGHT_AND_RISK_AUDIT_2026-11-02.md`.
The calendar and instrument metadata must match the actual historical contract
and remain independently reviewed. Partition files must have point-in-time
timestamped CE/PE quote rows in exactly the Stage26 CSV schema. This is NOT an
OHLCV futures 15-year dataset importer.

Run from the repository root after using a legally sourced local dataset:

```bash
python scripts/run_stage44_historical_fo_catalog.py \
  --catalog-root /tmp/titan-catalog \
  --catalog /tmp/titan-catalog/catalog.json
```

Expected success output is structural **only**. It always explicitly has
`external_source_authenticated=false`,
`licence_authenticated=false`,
`point_in_time_exchange_metadata_authenticated=false`,
`exchange_calendar_authenticated=false`,
`full_market_history_coverage_verified=false`,
`realistic_fo_backtest_verified=false`,
`strategy_promotion_allowed=false` and `live_orders_transmitted=0`.

## Validation and remaining blockers

- Run `python -m pytest -q tests/test_stage44_historical_fo_catalog.py`;
  require clean full-suite CI on Python 3.11/3.12/3.13 after opening draft PR.
  Record actual CI evidence; do not count unexecuted tests as passed.
- Source approval requires authentic vendor identity, licensing contract,
  official exchange effective-dated lot/tick/expiry records and independently
  vetted full exchange calendar. Hashes only prove file-byte stability against
  an operator-provided checksum.
- A realistic strategy backtest requires actual historically consistent
  F&O bid/ask and liquidity, contract rollover, spreads, realistic fills and
  validated charges/slippage. The Stage44 catalog does not claim to run these
  backtests, discover missing *unprovided* contracts or prove data coverage
  outside each explicitly declared partition.
- Stage43 global independent Risk & Veto, authenticated approvals, two-ledger
  atomicity, and the locked black-and-silver connected frontend remain separate
  incomplete workstreams. Never enable real-money execution.
- The user plans to provide vendor market data later. Do not upload/commit
  proprietary market data, credentials, licences or sensitive customer files.
- This is **Stage44 pipeline groundwork**, not Stage44 full market-data
  validation or Stage45 production acceptance. Keep the new PR stacked and
  draft; no merge without human review and full integrated CI.
