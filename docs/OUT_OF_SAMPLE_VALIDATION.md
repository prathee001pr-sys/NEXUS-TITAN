# Chronological Out-of-Sample Validation

## Split policy
`split_chronologically` keeps the oldest candles in the in-sample partition
and the newest candles in a separate out-of-sample holdout. The default
in-sample fraction is 70%. Each partition must contain at least two candles;
the input must be strictly increasing and belong to one symbol/timeframe.

## Holdout execution
`evaluate_out_of_sample` passes the complete chronological series to the
backtest engine, but starts signal generation on the final in-sample candle.
That candle is used only to calculate indicator history. Its signal can fill
at the first out-of-sample candle open. No trades or P&L from the in-sample
period are included in the returned result. Any open holdout position is
closed at the final out-of-sample candle close.

This approach allows rolling indicators to warm up on earlier observations
without trading during the training partition. The strategy interface must
remain history-driven: it should use only the candles supplied to each call.

## Research discipline and limitations
Choose the split before comparing strategies or tuning parameters. Do not
change parameters after inspecting holdout results and continue to describe
the same holdout as untouched. For repeated strategy selection, reserve a
new later holdout or use a documented walk-forward design.

This utility does not perform parameter optimization, cross-validation,
walk-forward retraining, regime labeling or statistical significance testing.
It does not repair bad/missing market data or prove that a strategy has a
predictive edge. Results are only as reliable as the underlying data and
execution-cost assumptions.
