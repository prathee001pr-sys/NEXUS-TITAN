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

## Important market-calendar limitation
Gap detection uses fixed durations (minutes, hours, days). It can flag expected
overnight, weekend, holiday, or exchange-break closures as gaps. Do not interpret
those findings as missing market data until a market-session calendar is added.
The inspector deliberately does not guess exchange hours or auto-fill candles.

## Supported intervals
Positive integer intervals in minutes, hours and days, for example 1m, 5m, 15m,
1h and 1d. Weekly/monthly intervals are intentionally not supported yet.

## Safety
The inspector is deterministic and read-only. It does not connect to a data
provider, exchange, broker, strategy, or order execution system.
