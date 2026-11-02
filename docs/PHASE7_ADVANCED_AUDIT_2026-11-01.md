# NEXUS TITAN V2 / Phase 7 - Advanced Audit & Improvement Report

**Date:** 01 November 2026  
**Scope:** Trading-only research / backtest / virtual execution  
**Source archive:** `NEXUS_TITAN_V2_Phase7_Hardened.zip`  
**Source ZIP SHA-256:** `00a01a85da400388098e3ff8cb2c64739d22e2ffb7fbc26cfd26b3a5bbfe7c8a`  
**Original archive:** preserved unchanged; all source edits were made in an isolated working copy.

## 1. Executive decision

The supplied Phase 7 Hardened source archive was checksum-verified against the user's SHA-256 manifest, extracted into a separate working directory, inspected, tested, and backtested. Two code-level improvements were implemented and regression-tested, along with improved backtest-report traceability and explicit scope warnings.

**Result:** compileall passed; project validation passed; **322 tests passed + 5 subtests passed**; advanced research backtest completed successfully. This is a hardened research/virtual-paper snapshot, not a production-ready or profitable trading system. Live trading remains disabled.

## 2. What changed

### Improved

1. **Full dataset SHA-256:** `research/backtest.py::compute_file_sha256()` previously returned only the first 16 hexadecimal characters and read the whole file into memory. It now streams 1 MiB chunks and returns the full 64-character SHA-256 digest. The dashboard now reports a digest consistent with the canonical data-provenance helper.
2. **Monte Carlo adequacy:** `MonteCarloReport` now records sample size, `sample_adequate`, a warning, the effective resampling method, and the drawdown scope. Samples below 30 closed trades are explicitly marked exploratory. The 30-trade threshold is an operational floor, not statistical proof.
3. **Promotion safety:** a strategy cannot pass the promotion check when the Monte Carlo closed-trade sample is below 30, even if other supplied gate fields are set to passing values.
4. **Parameter validation:** Monte Carlo now rejects invalid capital, iteration count, block size, minimum sample size, unsupported method names, and non-finite trade P&L values.
5. **Small-sample method labelling:** when a block bootstrap cannot be formed because the block is larger than the available sample, the actual fallback is reported as `trade_shuffle`.
6. **Report provenance:** the advanced report now records a SHA-256 fingerprint of its Python source inputs and explicitly labels the NIFTY sample as a synthetic signal smoke test. It warns that NIFTY spot is not an equity-delivery instrument; the current equity-delivery cost setting is a placeholder to exercise code paths, not a valid NIFTY execution model.

### Removed / cleaned

- Excluded generated `__pycache__` and `.pytest_cache` directories from the improved ZIP package. These are build/test artifacts, not product capabilities.
- **No application source modules were deleted.** The old V2 `backtest_engine.py` and compatibility exports in `research/strategies.py` and `research/validation.py` were deliberately retained because the source map documents them as legacy API compatibility boundaries. Removing them based only on apparent duplication could break existing consumers/tests.
- Out-of-scope Creator Studio, Finance OS, heavy microservices, and 45 always-on agents were not introduced.

## 3. Reproducibility and tests

| Check | Result |
|---|---|
| Source ZIP SHA-256 | Matches supplied manifest |
| `python -m compileall -q src tests scripts` | Passed |
| `PYTHONPATH=src python -m pytest -o addopts= -q` | 322 passed, 5 subtests passed |
| `PYTHONPATH=src python scripts/run_project_validation.py` | Passed |
| `PYTHONPATH=src python scripts/run_advanced_backtest_suite.py` | Completed |
| Strategy candidates in this exact ZIP | 8 |
| Code-verified G0-G9 gates | 4 / 10 |
| Gates awaiting external evidence | 6 / 10 |
| Failed gates | 0 |
| Live-order transmissions | 0 |

The 4 code-verified gates are G0 build/test reproducibility, G3 arithmetic/accounting fixtures, G4 risk/approval smoke checks, and G5 simplified execution fixtures. The other 6 gates require external or operational evidence; a count of 4 passed does not mean the system is release-ready.

## 4. Backtest evidence and limitations

### Dataset

- Symbol: NIFTY; interval: 1 day; 120 bars.
- Date range in manifest: 01 January 2025 to 30 April 2025.
- Dataset class: `SYNTHETIC_SMOKE_FIXTURE`.
- Vendor: `SYNTHETIC_QA_GENERATOR`; licence: `INTERNAL-QA-ONLY`.
- Manifest verification: false; strategy promotion is disallowed.

This dataset is an engineering smoke fixture, not NSE historical market data. It is not a licensed, survivorship-bias-free, point-in-time market history set and cannot establish strategy edge.

### Eight strategy scorecards

| Strategy | Net P&L output | Return output | Trades | Anchored OOS trades | MC sample adequate? | Stage |
|---|---:|---:|---:|---:|---|---|
| SMA Crossover | -222.49 | -0.445% | 3 | 2 | No (3/30) | DRAFT |
| EMA Crossover | -297.36 | -0.595% | 3 | 2 | No (3/30) | DRAFT |
| RSI Mean Reversion | 119.77 | 0.240% | 2 | 0 | No (2/30) | DRAFT |
| RSI Momentum | -35.36 | -0.071% | 3 | 3 | No (3/30) | DRAFT |
| MACD Trend | -16.05 | -0.032% | 2 | 0 | No (2/30) | DRAFT |
| Bollinger Breakout | -49.59 | -0.099% | 1 | 1 | No (1/30) | DRAFT |
| ATR Volatility Channel | -200.68 | -0.401% | 2 | 2 | No (2/30) | DRAFT |
| Regime Adaptive Composite | -114.99 | -0.230% | 2 | 0 | No (2/30) | DRAFT |


The P&L values above are simulator outputs on synthetic index candles using a placeholder `EQUITY_DELIVERY` charge configuration. NIFTY spot is not an equity-delivery instrument. Therefore these rupee-like figures are not valid tradable NIFTY profit/loss, and should be treated only as a code-path/signal smoke-test output. Use a verified tradable contract and official point-in-time instrument/cost metadata before making economic performance comparisons.

### Walk-forward and Monte Carlo

- Four anchored and four sliding folds were run for each candidate.
- Anchored out-of-sample trades ranged from 0 to 3; all were below the configured minimum of 5 for the walk-forward verdict and far below the promotion requirement of 30.
- All eight strategies remain `DRAFT`; no candidate was promoted.
- Monte Carlo closed-trade samples contain only 1-3 trades. All now report `sample_adequate=false`; their percentiles/ruin figures are exploratory only. Drawdown scope is closed-trade P&L only and excludes intratrade/unrealized exposure.
- A 30-trade threshold is only a minimum operational gate. A robust strategy assessment may require substantially more data/trades and regime coverage.

### Futures, shadow, options and crypto demonstration

- Futures long/short demonstration: 3 trades, 2.258% reported return, 1.183% reported maximum drawdown, and 69.67% average exposure. This uses the same synthetic 120-bar sample, fixed sizing, and unverified static lot reference. It is not a statistically meaningful futures result.
- ₹50,000 shadow demo: 2 orders filled; reported simulated realized P&L ₹151.58; reconciliation discrepancy ₹0.01 within the code's one-paisa tolerance; zero live orders transmitted. This is a single deterministic demonstration, not multi-day shadow evidence.
- Options: one constructed test quote and arithmetic/Greeks/expiry fixtures; not a complete live option chain or calibrated exchange execution history.
- Crypto: isolated local virtual-account reconciliation; no exchange feed or licensed historical crypto dataset was connected.

## 5. Uploaded report vs source ZIP mismatch

A separately uploaded `phase7_advanced_backtest_report.json` reported 10 strategy candidates and a stdlib fallback count of 329 tests. Its SHA-256 is `846069840f18de6d8a4891a1db2393fe5c4491181dc0806c6cd9f2bff86461dc`, which differs from the previously supplied manifest hash `f4925fe76ec4c67c55cd7e56c85f899376506a7146181d09e495c6a75fcbe95c` for `NEXUS_TITAN_V2_Phase7_Backtest_Report.json`.

The source ZIP itself matches its manifest and contains 8 registered strategies. Re-running that exact ZIP reproduced 8 strategies and the original 318-test baseline (before the four new regression tests). The separate 10-strategy/329-test report therefore cannot be assumed to describe the contents of this source ZIP. The improved report is regenerated from the verified ZIP and carries a 76-file source fingerprint.

## 6. What was intentionally not removed

The apparent older research engine and wrappers are documented compatibility components. Their deletion was not justified by static appearance alone. The SQLite learning/runtime data file was also preserved because it may contain user project state. No secrets, live broker route, or credentials were added.

## 7. Remaining P0 work before strategy claims

1. Obtain licensed, provenance-verified NIFTY/BANKNIFTY historical data at the chosen interval, with missing bars, corrections, corporate/contract events, and point-in-time metadata accounted for.
2. Use actual tradable instrument datasets for futures/options and independently verify expiry, lot/tick sizes, exchange charges, broker contract notes, margin, and settlement assumptions.
3. Re-run chronological walk-forward and unseen tests with adequate trade counts; include regime and time-of-day stability, realistic spread/slippage/partial-fill assumptions, and benchmark comparisons.
4. Calibrate execution against licensed tick/order-book data before treating microstructure fill estimates as realistic.
5. Complete independent API parity, external security testing, recovery/restore drills, and multi-day ₹50,000 virtual shadow observation.
6. Keep TITAN EVOLVE candidate promotion human-approved; it must not modify risk limits, permissions, capital controls, kill switch, or live-order permissions.

## 8. Final status

**Improved research code snapshot, not production-ready.** No strategy has passed promotion. Existing code modules and runtime state were preserved; only the identified provenance/Monte Carlo/reporting improvements were applied. Live trading remained disabled throughout.

## 9. Stage 2 — Data integrity hardening (01 November 2026)

A follow-on code review found two data-quality weaknesses: (a) calendar-aware checks detected gaps but did not reject individual candles timestamped outside configured market sessions, and (b) a manifest could silently default `missing_bars_count` to zero even though no calendar-based completeness audit had been performed.

### Changes implemented

1. `data/quality.py` now records `outside_session` timestamps whenever a market calendar is supplied. These are included in `DataQualityReport.is_valid`, so weekend/holiday/out-of-session candles invalidate the batch.
2. `data/provenance.py` now leaves `missing_bars_count=None` and `coverage_verified=false` unless a caller supplies a market calendar and the batch passes the calendar-aware check. Unknown coverage is no longer converted into a false zero.
3. Strategy-promotion manifests now require explicit vendor-identity, licence, coverage, and point-in-time instrument-metadata evidence references, plus a named reviewer and timezone-aware review timestamp. They also require verified calendar coverage, zero missing/duplicate bars, licensed exchange history, and survivorship-bias-free attestation.
4. `verify_dataset_manifest()` requires the market calendar again when coverage was marked verified and rechecks the data before returning success.
5. `build_manifest_from_csv()` now rejects invalid canonical CSV rather than creating a partially valid-looking manifest.
6. Manifest validation rejects booleans masquerading as integer bar counts and requires timezone-aware manifest/review timestamps.
7. Added `tests/test_data_provenance_gates.py` with focused tests for out-of-session candles, unknown coverage, missing intraday bars, promotion evidence, calendar re-verification, and strict manifest values.

### Validation

| Check | Result |
|---|---|
| Pytest collection | 329 tests collected |
| Pytest run | 329 passed |
| Advanced runner | 329 passed + 5 subtests passed |
| `compileall` | Passed |
| `scripts/run_project_validation.py` | Passed |
| `scripts/run_advanced_backtest_suite.py` | Completed; report regenerated |

### Gate status and limitations

G2 (Data integrity) remains **EXTERNAL_INPUT_REQUIRED**, not passed. The bundled dataset is still a synthetic 120-bar sample. No genuine licensed NSE data, official point-in-time contract master, independently reviewed vendor licence, or complete official NSE holiday/special-session calendar was supplied. Evidence-reference fields are operator-supplied pointers; the software checks their presence but does not authenticate external documents or prove legal data rights. All strategies remain research-only; no strategy was promoted; live-order transmission remains disabled.

### Files changed

- Modified: `src/nexus_titan/data/quality.py`
- Modified: `src/nexus_titan/data/provenance.py`
- Modified: `docs/TRADING_DATA_QUALITY.md`
- Modified: `docs/MASTER_REQUIREMENTS_REGISTER.md`
- Added: `docs/DATASET_PROVENANCE_PROMOTION_GATE.md`
- Added: `tests/test_data_provenance_gates.py`

No existing strategy, risk, permission, broker, or live-order module was removed or altered in this stage.
