# Phase 6 ZIP Compatibility Test Report

Date: 2026-11-01
Reference archive: `NEXUS_TITAN_V6_Phase6_Agent_Runtime_And_Backtest.zip`
Integration repository: `prathee001pr-sys/NEXUS-TITAN-V2`
Integration branch: `integration/phase6-zip-baseline`

## Verdict

The V2 integration branch is the stronger overall project foundation because it retains V2 Core/data/security/backtest work while integrating the Phase 6 capabilities. It is not a byte-for-byte copy of the uploaded ZIP: 40 of the 48 ZIP Python source modules were adapted to V2 interfaces and compatibility requirements.

## Test runs

| Test run | Source under test | Result |
|---|---|---:|
| Uploaded ZIP standalone | Original ZIP source and tests | **246 passed** |
| ZIP compatibility run | Original ZIP's unchanged tests, but `PYTHONPATH` pointed to the integrated V2 `src/` directory | **246 passed** |
| V2 integrated CI | Full V2 integration-branch test suite | **280 passed, 5 subtests passed** |

V2 GitHub Actions evidence:
https://github.com/prathee001pr-sys/NEXUS-TITAN-V2/actions/runs/41256696389

The compatibility run was performed in the working test environment against the branch snapshot. The original ZIP's 30 test modules have not yet been copied into the V2 repository's CI test tree, so that exact 246-test compatibility run is not yet automatically repeated on every V2 push.

## Source inventory

- Original ZIP: **48 Python source modules**, **30 Python test modules**.
- V2 integrated snapshot: **69 Python source modules**, **37 Python test modules**.
- ZIP paths represented in the integrated source: **48 / 48**.
- Byte-identical ZIP modules: **8**.
- Adapted/reimplemented ZIP modules at the same path: **40**.
- Additional V2 source modules retained: **21**.

The original V2 `research/backtest_engine.py`, `MovingAverageCrossover`, and chronological OOS functions remain. The V6 strategy and validation APIs are exposed as compatibility imports while also remaining available in collision-safe modules `v6_strategies.py` and `v6_validation.py`.

## Compatibility corrections made after initial comparison

The first direct ZIP-test run against the adapted integration code exposed compatibility gaps. These were corrected and regression coverage added:

1. Derivative partial fills now enforce whole-lot multiples.
2. Changing an approved order after manual approval invalidates the approval snapshot.
3. Daily-loss and other pre-trade risk checks are applied before accepting another entry.
4. Dashboard telemetry includes the self-improvement capability list and the original 15-module breakdown.
5. The dashboard's `run_live_backtest_suite` API name remains available as a compatibility alias.
6. The original V2 strategies/validation modules retain their interfaces and re-export the V6 strategy/validation APIs.

After these corrections, the original ZIP tests passed unchanged against the integrated V2 source.

## Important cautions

- A passing unit suite is not proof that every adapted public API is byte-for-byte or semantically identical in every untested condition.
- A full line-by-line parity review of all 40 adapted modules remains open.
- `data/market_sample.csv` and `data/nifty_daily_sample.csv` are deterministic synthetic smoke-test fixtures. They are not real or licensed NSE historical data.
- The included NIFTY spot sample is not executable futures/options P&L and does not validate exchange-grade costs or liquidity.
- Futures/options margins, SPAN/ELM, exercise/assignment, historical option-chain data, crypto history, partial-fill market microstructure and provider licensing still require independent validation.
- The PR remains draft and is not merged into `main`.
