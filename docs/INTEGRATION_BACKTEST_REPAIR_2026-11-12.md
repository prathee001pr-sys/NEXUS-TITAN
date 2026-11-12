# NEXUS TITAN: integration, backtesting and repair report

Date: 12 November 2026 (Asia/Kolkata). Scope: supplied Phase 11 / Stages 149–152 ZIP only.

## Result

**PASS for the automated offline regression and integration checks executed here.** Final run: **3,751 passed, 5 subtests passed; zero failures, errors, skips or warnings**, Python 3.12.14, in 124.34 seconds with branch coverage and warnings treated as errors. This is local evidence; GitHub CI and other Python versions were not verified in this task.

The original snapshot passed 3,729 tests with one optional PDF test skipped and one Python syntax warning. Additional causal checks nevertheless exposed defects. The repaired snapshot adds 21 regression checks; the optional PDF check also ran after its existing optional dependencies were made available. The JUnit total is 3,756 because it includes the five subtests.

**Real-market backtesting and profitability remain NOT VERIFIED.** Neither bundled CSV is licensed or authenticated exchange history. No strategy was promoted, no live trading enabled, and no GitHub branch or repository setting was changed.

## Confirmed defects repaired

| ID | Priority | Defect before repair | Repair and verification |
|---|---|---|---|
| F01 | P1 | Stops and targets were not evaluated on the entry candle. | Protection is now active after the entry at the open. Long and short entry-stop, target and ambiguous-range checks pass. |
| F02 | P1 | The engine inspected the next candle's entire range before processing a scheduled exit at its open. After an intrabar stop it could also re-enter at the same candle's already elapsed open. | Opening gap protection, scheduled open orders, then the intrabar range now execute in chronological order. The fixture with a fictitious +5 result and two trades now correctly returns -5 with one trade. |
| F03 | P1 | An equity intraday position closed at the following session's open and earned an overnight gap. | It now closes at the preceding session's last available close. The controlled fixture changes from +50 to 0 before costs. This is a bar-model close, not proof of a broker's actual square-off price. |
| F04 | P1 | Both rolling and single-split OOS factories received test-window data during fitting. | A fresh OOS strategy is fitted on the training slice only. Fit-window boundary checks pass for both APIs. Trusted callbacks still must not read external future data. |
| F05 | P2 | Rolling warm-up skipped the first OOS execution bar; the single split lacked the preceding known close. | The last warm-up decision can execute at the first OOS open. The single split carries one preceding training candle as context only. |
| F06 | P1 | Fixed-quantity backtests bypassed daily-loss, drawdown and consecutive-loss circuit breakers. | The existing circuit-breaker thresholds now apply to both sizing modes, using equity known at the open. A same-session fixture changes from five trades / -200 to one trade / -50, with later entries rejected. Fixed mode still uses the caller's requested quantity; it is not automatic risk sizing. |
| F07 | P2 | Impossible fold counts, invalid train ratios and a zero minimum-trade gate could be silently accepted. | Parameter and complete-fold checks now reject invalid inputs explicitly. Existing normal walk-forward callers continue to pass. |
| F08 | P2 | The advanced CLI's declared source timezone was applied to the manifest but not passed to the candle loader. | The loader and both backtest CLIs now forward source_timezone. Explicit UTC and invalid-zone tests pass. |
| F09 | P3 | A test regex contained an invalid Python escape sequence and produced a SyntaxWarning. | Converted it to a raw string without changing the assertion. Forced compilation and the full suite pass with warnings treated as errors. |

Before fixing these issues, the first independent causal batch recorded 12 failing checks and one passing check. Two further timezone checks reproduced the missing loader argument. These before-repair logs are retained. No previous behavioral assertion was weakened to obtain a passing result.

## Integration evidence

These are actual Python calls and deterministic fixtures, not assertions that live-market services were exercised.

| Path covered | Selected passing cases | Evidence |
|---|---:|---|
| Core master orchestration and specialist governance | 21 | Consensus → independent risk → red-team → simulated execution; pending human approval when staging is requested. |
| Ingested F&O CSV → as-of alignment → IV/Greeks → experience → scenario → risk → SQLite sandbox | 4 | NIFTY and BANKNIFTY synthetic chain, plus invalid input cases. |
| F&O closed-trade lifecycle | 31 | NIFTY/BANKNIFTY CE/PE, partial fills, costs, close, dashboard, duplicate protection, kill and restart. |
| F&O accounting handoff and separate crypto paper book | 35 | Actual Stage 95 handoff, crypto buy/partial exit/full close, replay, tamper detection, Safe/Risky authority, restart and currency isolation. |
| Stages 141–148 acceptance and review workflow | 66 | Historical integrity, cost arithmetic, fill reconciliation, human-review status, dashboard and security/regression review gates. |
| New execution/validation regression checks | 21 | Entry protection, event ordering, intraday close, OOS train-only fitting, boundaries, circuit breaker and timezone. |

All 23 single-command stage checks listed in `.github/workflows/ci.yml` were run locally and returned exit code 0. Separate Stage 25, Stage 36, Stage 42 and Stage 84 smoke commands also completed. These successful process exits can intentionally report NO-GO for promotion; they are not production approvals. Dashboard coverage uses the existing Python and Node harnesses, not an observed deployed dashboard/browser session.

## Backtests actually executed

The basic runner evaluated all eight strategies on each included sample: 20 bars and 120 bars. The advanced suite evaluated eight strategies, four-fold anchored and sliding walk-forward validation, 500-iteration block-bootstrap Monte Carlo per strategy, a futures long/short example, derivative accounting fixtures, a 50,000-unit shadow account and a separate crypto virtual account.

**The following numbers are synthetic software-fixture outputs only.** The advanced suite uses a placeholder EQUITY_DELIVERY charge setting on a synthetic index series; it is not an executable NIFTY or F&O performance model. Columns are model currency units, not achieved profit. Quantity is one; starting capital is 50,000.

| Strategy | Closed trades | Model net P&L | Profit factor | Expectancy/trade | Close-equity max DD | Anchored OOS trades |
|---|---:|---:|---|---:|---:|---:|
| sma | 3 | -222.49 | 0.00 | -74.16 | 0.496% | 2 |
| ema | 3 | -297.36 | 0.00 | -99.12 | 0.612% | 2 |
| rsi | 2 | 119.77 | undefined (no losing trades) | 59.88 | 0.109% | 0 |
| rsi_momentum | 3 | -35.36 | 0.00 | -11.79 | 0.321% | 3 |
| macd | 2 | -16.05 | 0.00 | -8.03 | 0.272% | 0 |
| bollinger | 1 | -49.59 | 0.00 | -49.59 | 0.242% | 1 |
| atr_channel | 2 | -200.68 | 0.00 | -100.34 | 0.401% | 2 |
| regime_adaptive | 2 | -114.99 | 0.00 | -57.50 | 0.230% | 0 |

All eight anchored walk-forward verdicts are **INSUFFICIENT_EVIDENCE**. All eight Monte Carlo samples are inadequate for reliable tail-risk estimates. All eight promotion decisions remain false. A positive synthetic result is not evidence of a profitable tradable strategy.

The synthetic shadow ledger reconciles within its existing 0.01 rounding tolerance; the crypto virtual ledger discrepancy is 0.00. Replay protection, stale-feed rejection, kill switch, daily-loss lockout, partial-fill arithmetic and futures/options arithmetic checks all return true. These arithmetic fixtures do not validate official rates, real liquidity, SPAN/ELM, historical contracts or current broker charges.

## Coverage and readiness

- Statement coverage: **88.08%** (18,087/20,535).
- Branch coverage: **76.00%** (5,399/7,104).
- Combined line/branch coverage: **84.97%**. Untested paths remain; coverage is not complete.

The final advanced report contains current full-regression evidence rather than skipped-test evidence. Four quality gates are code-verified; six still require external evidence:

| Gate | Scope | Recorded status |
|---|---|---|
| G0 | Build reproducibility | PASSED_CODE_VERIFIED |
| G1 | API/behavior correctness | EXTERNAL_INPUT_REQUIRED |
| G2 | Data integrity | EXTERNAL_INPUT_REQUIRED |
| G3 | Accounting accuracy | PASSED_CODE_VERIFIED |
| G4 | Risk and approval safety | PASSED_CODE_VERIFIED |
| G5 | Execution realism | PASSED_CODE_VERIFIED |
| G6 | Independent security | EXTERNAL_INPUT_REQUIRED |
| G7 | Operations and recovery | EXTERNAL_INPUT_REQUIRED |
| G8 | Paper evidence | EXTERNAL_INPUT_REQUIRED |
| G9 | Release sign-off | EXTERNAL_INPUT_REQUIRED |

Still required for genuine market validation: licensed and provenance-verified historical F&O/crypto data, point-in-time contracts and calendar, verified fees/margin/settlement assumptions, adequately sampled chronological OOS results and observed multi-day paper evidence. Independent security and operational acceptance remain open. Automated regression does not establish that every future input or all production paths are correct.

## Reproduce locally

From the extracted project root, using Python 3.11 or newer:

```bash
python -m pip install -e '.[dev]'
python -m pip install pytest-cov pytest-timeout reportlab pypdf
PYTHONPATH=src python -W error -m compileall -q -f src scripts tests
PYTHONPATH=src python -m pytest -q -o addopts='' -W error --timeout=30
PYTHONPATH=src python scripts/run_advanced_backtest_suite.py --json-out reports/backtest_current.json
PYTHONPATH=src python scripts/run_stage25_full_research_audit.py --json-out reports/offline_audit_current.json
```

The last two commands are separate reports; the advanced command runs the full regression internally. Stage 25 intentionally skips nested pytest. In this task, unrelated global pytest plugins were disabled and only coverage/timeout plugins explicitly loaded; this avoids a pre-existing environment plugin warning. The optional PDF packages are only needed for their existing optional ingestion test.

## Package evidence

`reports/integration_backtest_2026-11-12/` contains the final advanced JSON, final JUnit XML, coverage JSON/XML, before-repair test logs, CLI results and a reviewable repair patch. `INTEGRATION_BACKTEST_REPAIR_MANIFEST_2026-11-12.json` records the exact input hash, changed original files and final source fingerprint. Older manifests/reports describe their original checkpoints and are retained as history. Generated test databases and Python caches are excluded from this delivery.
