# Historical Market Data Service

## Purpose
Provide one provider-independent retrieval boundary between a data adapter and
NEXUS TITAN's research/backtesting components.

## Flow
1. Caller supplies a validated `CandleQuery`.
2. Injected `MarketDataSource` fetches candles.
3. Service checks that the adapter returns a sequence containing only `OHLCVCandle` objects, then freezes it as a tuple. Contract violations raise `MarketDataSourceContractError`.
4. Data Quality Inspector checks query bounds, symbol/timeframe identity,
   ordering, duplicates and missing intervals.
5. Invalid batches raise `MarketDataValidationError` with the full report;
   valid batches return `ValidatedCandleBatch`.

## Safety and limitations
- No provider SDK, network client, broker, order, strategy or credentials are
  included in this package.
- Provider exceptions are allowed to propagate to the caller; retry policy and
  rate limiting belong in a later adapter/orchestration layer.
- Empty batches are valid transport results, not proof that historical data
  exists. The caller must decide whether an empty response is acceptable.
- Calendar-aware gap checks require a caller-supplied configured calendar.
  The NSE baseline is not an official holiday feed.
- The service does not sort or repair provider data: malformed ordering is
  rejected so source defects remain visible.
