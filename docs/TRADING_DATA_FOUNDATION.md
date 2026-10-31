# Trading Data Foundation — OHLCV Contract

## Purpose
Establish a small provider-independent contract before connecting any exchange,
vendor, broker, or live feed. This phase defines data shape and validation only.

## Candle contract
- One `OHLCVCandle` represents one candle; timestamp means candle open time.
- Timestamps must be timezone-aware and are normalized to UTC.
- Prices and volume are converted to finite `Decimal` values.
- OHLC prices must be positive; volume may be zero but not negative.
- High/low must contain the open, close and opposite extreme.
- Symbol, timeframe and source are required.
- Candle objects are immutable.

## Query and adapter contract
- `CandleQuery` uses timezone-aware UTC-normalized bounds.
- Query interval is half-open: start inclusive, end exclusive.
- `MarketDataSource` is a Protocol. Future adapters can implement it without
  coupling the core to a vendor or exchange SDK.
- Adapter results are expected oldest-to-newest. A future service layer will
  enforce sorting, duplicate detection, gaps and query-bound checks.

## Explicitly not included
No exchange API, broker, network polling, strategy, order placement, live feed,
historical data download, or real-money execution is implemented here.
