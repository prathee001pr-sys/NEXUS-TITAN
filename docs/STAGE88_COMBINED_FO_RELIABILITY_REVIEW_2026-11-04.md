# Stage 88: connected synthetic F&O integration and reliability review

## Actual connected code path

The expanded CSV fixture uses real Stage59 futures and Stage44 options importers, Stage71 completed-candle alignment, Stage72 expiry/IV/Greeks, Stage73 calibration experience and Stage74 scenarios, then Stage75/76 research risk. Forty fabricated futures candles and two option snapshots provide enough warm-up for actual market-regime calculations. The market assessment admits only the 35 candles completed at the first options observation; later/incomplete candles are excluded.

`assess_synthetic_fo_research` connects that actual ingested history to the existing OHLCV validator, regime classifier, MarketStateBuilder, ConsensusEngine and AuthoritativeRiskEngine through TradingIntelligencePipeline. It binds the alignment/options source digests and carries the EVOLVE review as diagnostic context. Unknown regime/volatility does not manufacture a signal. Supplied BUY proposals are explicitly fabricated engineering-drill inputs, with UNCALIBRATED confidence; no alpha, independent-source authentication or strategy efficacy is established.

The Stage73 fixture resolves a synthetic future label for diagnostic post-mortem calibration. Its single paired sample remains insufficient and never grants promotion or order authority. It is **not evidence of a prospective leak-free training/inference pipeline**. Direction in this engineering drill comes from explicit synthetic proposals, not that label or Brier score. Genuine forward/OOS evaluation remains required.

`SyntheticFOExecutionGateway.apply_assessed_open` requires a valid BUY shadow candidate, adequate pretrade risk quantity and source hashes matching the selected account's pinned Stage71/72/73 contract. It then calls the actual Stage86/87 boundary: signed risk review -> same-file atomic reservation -> synthetic partial/full fills -> deny-only cancellation. Stage83 reconciles the exact same journal/cash/holds. The gateway's report reads that verified snapshot rather than a second ledger.

This assessment facade is cooperative Python composition, not a global process-security boundary. Callers can use the lower-level selected-account lifecycle, which still enforces mandatory signed Risk & Veto in the ledger. No production broker or live-trading path is introduced.

## Supported report and tested reliability

The final combined test reserves both NIFTY and BANKNIFTY, fills 10 and 25 units at 545 cents, charges 5 cents each, cancels only the unfilled NIFTY quantity and reconciles all five events. Paid premium is **19,075 cents**, fees **10 cents**, pending reserve **0**, with **35 filled units**. These are fabricated engineering-test amounts, not genuine NSE prices, costs or investment returns.

The report supplies verified cash, holds, paid premium, costs and gross committed debit. Net P&L, profit factor, expectancy and drawdown are `None` with an explicit unavailable reason: the selected adapter has no exits or independently marked equity curve. Premium cash outflow is never presented as realized trading loss.

New tests include both markets' stale/conflicting/wrong-source/kill/daily-loss failures; unknown-regime denial; futures checksum failure and duplicate timestamps even after the supplied hash is updated; options checksum corruption; real POSIX process death before commit and after commit with a lost reply; recovery and replay without duplicate allocation; corruption of event and head hashes while the old signed risk proof remains; EVOLVE's protected risk/permission/live targets; and unchanged global release NO-GO. Existing Stage86/87 concurrency, duplicate, partial-fill, fee, crash and accounting tests run in the full regression.

The process-death drill uses POSIX fork only in tests and is skipped on platforms without it. Runtime code is standard-library Python 3.11+; the prior injected-exception rollback tests remain portable.

## Security and release readiness

The supported selected-account engineering flow is testable; **real F&O shadow deployment is NO-GO**. Remaining blockers include:

- Genuine licensed point-in-time NIFTY/BANKNIFTY futures/options data, verified contract master, exchange calendars, depth, fees, margins and expiry handling.
- Real prospective out-of-sample and forward shadow evidence, calibrated independent signals and trustworthy execution-quality measurement.
- Independent risk/operator identity, secure signer custody and revocation, trusted clock and process/host isolation. Local HMAC possession is not human approval.
- Global migration or explicit disabling of relevant legacy ledgers/entrypoints; cross-database capital remains separate. Crypto has its own accounting and risk silo.
- Full selected-account SELL/close, realized P&L, MTM equity, options settlement, actual futures/short-option margin and refreshed research-allocation lifecycle.
- External journal checkpoints/anchors to detect wholesale rollback or replacement of an otherwise valid database. Local replay/HMAC checks do not establish that external guarantee.
- Main protection, owner-reviewed integration/merge and deployment readiness. No main merge or protection setting change is performed.

## Batch evidence

Stage85: 2,319 passed (+3), commit `b9117a684b8089db367acd65be84e3c0016d3344`, PR #78, three-version CI run `41840950048` success.

Stage86: 2,349 passed (+30), commit `465226196aae7336fc2f873fbd42f930f778ef21`, PR #79, three-version CI run `41842244043` success.

Stage87: 2,368 passed (+19), commit `1c463f5cd36780603692965f4a03e9599e61863a`, PR #80, three-version CI run `41843335876` success.

Stage88 adds 22 reliability/integration tests. Final full-regression counts, exact published head and 3.11/3.12/3.13 job results are verified after publication and included in the consolidated handoff. Unique counts are never multiplied by Python environments; five pre-existing pytest subtests are separate.

Final local Stage88 result: **2,390 passed, 0 failed**, 22 new tests in this stage and 74 new tests across the batch, on Python 3.12.14. Compilation, editable-package dependency validation, whitespace review and a 153-module/268-internal-edge import audit passed. Both abrupt process-death cases executed locally. Runtime imports add no third-party dependencies. Exact published-head CI is checked separately before reporting the batch complete.
