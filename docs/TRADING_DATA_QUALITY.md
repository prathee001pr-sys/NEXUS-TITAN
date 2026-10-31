# Trading Data Quality Layer

## Scope
The quality inspector checks a supplied in-memory candle batch. It performs no
network calls, writes, automatic repair, sorting, or trading decisions.

## Checks
- Duplicate candle timestamps.
- Out-of-order adjacent input pairs (reported by original indices).
- Missing expected candle intervals between adjacent timestamps.
- Candles outside the requested half-open query range [start, end).
- Symbol or timeframe mismatches against the query.

## Optional market-calendar integration
Pass a configured `MarketCalendar` to `inspect_candle_batch`. When the next
fixed-duration timestamp falls outside a configured session, the inspector
advances the expected timestamp to the next configured session open. This
supports gaps within a session and immediately after a later session opens,
including across overnight closures, weekends and explicitly configured
holidays. Multiple sessions and special-session overrides are supported by
the calendar.

The report represents a missing span as (first expected timestamp, timestamp
of the later candle); it does not enumerate every missing candle in that span.
Without a calendar, the original continuous fixed-duration behavior remains.

Calendar holidays and special sessions are only as accurate as the caller's
configuration; the NSE helper is a regular-hours baseline, not an official
holiday feed or a contract-specific calendar. Validate schedules against the
applicable exchange circulars before using results for trading decisions.

## Supported intervals
Positive integer intervals in minutes, hours and days, for example 1m, 5m, 15m,
1h and 1d. Weekly/monthly intervals are intentionally not supported yet.

## Safety
The inspector is deterministic and read-only. It does not connect to a data
provider, exchange, broker, strategy, or order execution system.
