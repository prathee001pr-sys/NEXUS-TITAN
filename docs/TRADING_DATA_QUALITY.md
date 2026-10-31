# Trading Data Quality Layer

## Scope
The quality inspector checks a supplied in-memory candle batch. It performs no
network calls, writes, automatic repair, sorting, or trading decisions.

## Checks
- Duplicate candle timestamps.
- Out-of-order adjacent input pairs (reported by original indices).
- Missing fixed-duration intervals between adjacent timestamps.
- Candles outside the requested half-open query range [start, end).
- Symbol or timeframe mismatches against the query.

## Optional market-calendar integration
Pass a configured `MarketCalendar` to `inspect_candle_batch`. The inspector
then reports a gap only when the expected next candle timestamp is inside a
configured session and both candles fall on the same local calendar date.
Cross-date gaps are skipped in this first integration, preventing overnight
closures from being reported as missing candles. This conservative behavior
can miss a gap immediately after the next day's opening; that is a known
limitation pending a session-aware expected-candle iterator.

Without a calendar, the original fixed-duration behavior remains unchanged.
Calendar holidays and special sessions are only as accurate as the caller's
configuration; the NSE helper is a baseline, not an official holiday feed.

## Supported intervals
Positive integer intervals in minutes, hours and days, for example 1m, 5m, 15m,
1h and 1d. Weekly/monthly intervals are intentionally not supported yet.

## Safety
The inspector is deterministic and read-only. It does not connect to a data
provider, exchange, broker, strategy, or order execution system.
