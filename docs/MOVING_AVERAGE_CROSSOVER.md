# Moving Average Crossover Reference Strategy

## Rule
`MovingAverageCrossover` is a deterministic, long-only reference strategy. It
calculates simple moving averages from completed candle closes:

- Return `Signal(1)` when the fast SMA is strictly greater than the slow SMA.
- Return `Signal(0)` otherwise.
- Return flat until at least `slow_period` candles are available.

The default periods are 5 and 20. Both periods must be positive integers, and
the fast period must be smaller than the slow period. The strategy uses
`Decimal` arithmetic for its averages and retains no hidden position state.

## Execution and data safety
The strategy only reads the history passed to `on_candle`. In the historical
engine, that history ends at the currently closed candle; the resulting signal
is filled at the next candle open. This avoids using the same candle close as
both the signal and the fill price.

## Research limitations
This is a simple baseline for validating the strategy interface and backtest
pipeline. It is not evidence of a profitable trading edge and is not
parameter-optimized. It does not model short positions, intrabar execution,
liquidity, partial fills, market impact, options, margin or exchange-specific
constraints. Configure verified transaction costs before interpreting results.

Out-of-sample evaluation and comparisons across distinct market regimes remain
separate validation work. Do not tune parameters against an evaluation period
and then report that same period as an untouched out-of-sample result.
