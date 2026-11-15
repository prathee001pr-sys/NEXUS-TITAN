# NEXUS TITAN — Stage 25 End-to-End Code Audit & Synthetic Backtest Final Report

**Report date:** 2026-11-02 · **Candidate branch:** `feature/stage25-sell-aware-multiday-e2e-audit-2026-11-02` · **Target:** Stage24 draft PR #16. **This is not a production release.**

## Executive result

**Outcome: PASS for tested offline code paths; BLOCKED for genuine market
readiness.** Full repository unit/regression tests pass on Python 3.11, 3.12
and 3.13; synthetic historical strategies, Phase7 research/accounting fixtures,
Stage22 option-chain/ledger/restart smoke, and Stage25 SELL-aware daily
accounting were exercised. This is **not** a complete real NIFTY/BANKNIFTY
options backtest or proof that the complete connected TITAN product is ready.

Latest fully successful push workflow:
[GitHub Actions run 41456191413](https://github.com/prathee001pr-sys/NEXUS-TITAN/actions/runs/41456191413).
**812 passed + 5 subtests** in each Python matrix job.

### Stage25 design evidence

| Integration path | Tested outcome | Scope |
|---|---|---|
| Stage19 → Stage24 BUY then multi-day SELL | PASS | Synthetic long-only options |
| Per-day BUY premium/entry fees | PASS | SQLite audit event reconstruction; new events only |
| Per-day SELL proceeds/exit fees | PASS | Synthetic SELL observations |
| FIFO realized **net** P&L & remaining basis | PASS | Exact cents, partial and final exits |
| Trading days with no event | PASS | Calendar-derived carry-forward; calendar is unverified |
| Day-close claims | PASS / rejection tests | Missing/duplicate/wrong account/cash/P&L/time blocked |
| Restart and local SQLite restore | PASS | Same-host backup only |
| Legacy BUY without trade timestamp/fee split | FAIL-CLOSED | Cannot reconstruct historically without original records |
| Options price/liquidity/fee realism | UNVERIFIED | Synthetic displayed depth and indicative charges |
| Global unbypassable Risk & Veto | NOT COMPLETE | Stage23 optional research adapter, old direct paths separate |
| Real 15-year F&O backtest and supervised NSE shadow | NOT RUN | No verified/licensed market series supplied |

### Bundled synthetic historical backtest (NOT a market performance claim)

`scripts/run_stage25_full_research_audit.py` ran every available
`run_backtest.py` V6 strategy on both bundled sample CSVs. The model assumes
placeholder instrument costs and synthetic NIFTY price paths; rupee-like
numbers have **no live trading interpretation**.

| Synthetic source | Bars | Strategies | Completed simulated trades |
|---|---:|---:|---:|
| `data/market_sample.csv` | 20 | 8 | 0 |
| `data/nifty_daily_sample.csv` | 120 | 8 | 18 |

The eight 120-bar *illustrative* strategy-level estimated net P&Ls were:
`atr_channel -144.99`, `bollinger -21.82`, `ema -214.51`,
`macd +39.35`, `regime_adaptive -60.41`, `rsi +174.67`,
`rsi_momentum +47.33`, `sma -139.67`.
**These must not be interpreted as a ranking, investment advice, expected
returns, valid NSE tradable-contract results, or broker-executable P&L.**

The advanced Phase7 runner also executed strategy research/Monte Carlo,
walk-forward, derivatives/arithmetic fixtures, crypto virtual silo,
microstructure/shadow accounting, and G0–G9 release gate evaluation.
Golden partial-fill and options/futures arithmetic fixtures passed.
The *normal* CI advanced run executes pytest and reports **4 code-tested
gates** and **6 external-input-required gates**; the nested Stage25 runner
deliberately uses `--skip-tests` to avoid re-running pytest a third time,
so within that *nested* subreport G0 is unverified (3 code-tested / 7
external-required). Neither permits release.

### Actual bugs / issues identified and corrected

1. **Incomplete Stage19 BUY historical evidence:** Old BUY audit payload
   lacked fill time and split of premium/fees; new audit payload now stores
   `fill_observed_at_utc`, `buy_premium_cents`, `buy_fees_cents`. Existing
   rows are untouched. Old records fail closed in Stage25 until independently
   reconstructed from original evidence.
2. **BUY-only day-close assumption:** Earlier Stage20 validator rightly
   rejected legitimate SELL cash increases/inventory reductions. Added an
   independent, **versioned SELL-aware** daily reconciler instead of
   weakening BUY-only validation.
3. **Signed P&L comparison:** Ensured claim matching uses exact two-decimal
   signed currency, so genuine losses aren't rejected as invalid money and
   fake fractional-cent values don't pass.
4. **Empty or contradictory daily evidence:** Added fail-closed handling,
   missing-session/date/account, unsupported source dates and unresolved
   reservations.
5. **GitHub workflow YAML formatting:** Corrected literal newline escaping
   in an artifact upload `path` field that prevented CI jobs from starting.
6. **Incorrect synthetic manifest assumption in first audit runner:** Initial
   runner treated the synthetic source's correct **NOT VERIFIED** provenance
   as a fatal internal error. Fixed to preserve the external-data blocker in
   the report rather than claim the bundled sample is licensed exchange data.
7. **Audit report formatting:** Fixed a source-generation newline syntax
   error before final successful GitHub verification.

Multiple intermediary branch builds failed during active development; final
validated head CI is green. A green CI **does not mean all project bugs are
known or fixed**. Security penetration testing, live market simulation and
uncertified modules remain outside this verified scope.

## Release blockers requiring independent inputs

**P0:** Licensed timestamped NIFTY/BANKNIFTY futures/options, 1-minute bars
and point-in-time options/depth history; verified NSE contract master, actual
expiry calendars, correct taxes/fees, and consistent source provenance.

**P0:** End-to-end *globally enforced*, atomic permission + authoritative
Risk & Veto + account control, including concurrency and default-deny live
orders. Optional Stage23 research wrapper alone is insufficient.

**P0:** Controlled multi-day actual-feed shadow trading: true buys/sells,
liquidity and spread, partial executions and returns, expiry/exercise,
independent realized/unrealized net P&L and drawdown with broker-like
reconciliation. Existing synthetic diary is *not* this evidence.

**P1:** Dashboard API integration, service recovery/monitoring, encrypted
offsite backups, independent security audit, owner signoff, rollout/rollback.

## Commands to reproduce (full feature branch required)

```bash
python scripts/run_project_validation.py
python scripts/run_stage25_full_research_audit.py --json-out reports/stage25_full_offline_audit.json
python -m pytest -q tests/test_stage25_sell_aware_multiday.py
```

CI archives `reports/ci_backtest_report.json` and
`reports/stage25_full_offline_audit.json` as downloadable build artifacts.
The latter is intentionally written by the CI runner, **not** committed as
a performance claim in the source tree.

**Final decision:** Retain as stacked **DRAFT PR**; do not merge to protected
`main` without review. **Live trading remains disabled.**
