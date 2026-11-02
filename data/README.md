# Market-data fixtures

The CSV files in this directory are **test fixtures**, not trading data.

- `market_sample.csv`: short synthetic OHLCV fixture for CLI smoke checks.
- `nifty_daily_sample.csv`: deterministic synthetic 120-bar fixture for dashboard/backtest smoke checks.

They are generated for deterministic software tests only. They are not copied from
NSE, are not licensed exchange history, and must not be used to infer strategy
performance, executable P&L, market behaviour or trading decisions.

For actual historical testing, supply a separately licensed and verified OHLCV
dataset with point-in-time instrument metadata and documented provenance.
