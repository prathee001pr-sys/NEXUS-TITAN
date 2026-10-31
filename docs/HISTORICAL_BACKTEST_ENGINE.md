# Historical Backtesting Engine

## Execution model
The initial engine supports one symbol/timeframe and long-only exposure (flat or
long). A strategy receives history ending at the just-closed candle and returns
a target exposure. The engine executes that signal at the *next candle open*,
avoiding same-candle look-ahead. Any open position is closed at the final
candle close. Quantity is fixed; there is no leverage or automatic sizing.

## Costs
`ExecutionCostModel` accepts explicit non-negative rates for brokerage per
order, sell-side STT, exchange turnover fees, GST on brokerage plus exchange
fees, buy-side stamp duty and slippage in basis points. Defaults are zero and
are not an assertion of current Indian exchange charges. Configure rates from
verified broker/exchange schedules before interpreting results.

## Metrics
Reports final capital, net P&L, return, completed trades, win rate, profit
factor, expectancy and maximum drawdown based on closed-trade equity. Cash
accounting reserves the entry notional and deducts entry costs at purchase,
then credits exit proceeds net of exit costs. Profit
factor is null with no trades and infinity when there are wins but no losses.

## Limitations
This is a deterministic research baseline, not a production simulator. It is
long-only, fixed-quantity, single-instrument, bar-based, and assumes next-open
fills with no partial fills, liquidity model, margin, derivatives payoff,
short selling, intrabar stop/target sequencing or market impact. Costs must be
configured; zero-cost defaults are unsuitable for performance claims. No live
broker or order execution exists.
