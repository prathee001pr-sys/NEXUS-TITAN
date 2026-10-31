# CSV Historical Import and SQLite Store

## CSV format
The importer requires these columns: `symbol,timeframe,timestamp,open,high,low,close,volume`.
Timestamps must be ISO-8601 with an explicit timezone offset (for example
`2026-01-01T09:15:00+05:30` or UTC `Z`). The caller supplies a source label;
the CSV cannot override provenance. Every row is validated through
`OHLCVCandle`; malformed rows reject the import with a line number. The
`import_csv_to_store` pipeline then runs batch quality checks against a
`CandleQuery` (and optional calendar) before writing anything; a failed batch
is not persisted.

## Local storage
`SQLiteCandleStore` stores decimal values as text to avoid binary floating
point conversion. The unique key is (symbol, timeframe, timestamp). Repeated
keys are ignored and counted as duplicates; first stored values are retained.
Fetches are filtered by symbol/timeframe and the half-open UTC query range,
and returned oldest-first.

## Safe use and limitations
- This is local historical storage only; it has no network or broker access.
- Importer parsing does not itself prove completeness or market-session validity.
  Run imported rows through `MarketDataService`/the quality inspector before
  backtesting.
- The database is plaintext. Do not store credentials, tokens or secrets.
- Duplicate-key policy is idempotent insertion, not data correction. Conflicting
  values for an existing timestamp require a separately reviewed reconciliation.
- Provider licensing and exchange-data rights remain the user's responsibility.
