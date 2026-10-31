# NEXUS TITAN V2 — V6 Phase 6 ZIP Integration Status

Last updated: 2026-10-31 UTC
Integration branch: `integration/phase6-zip-baseline`
Draft pull request: https://github.com/prathee001pr-sys/NEXUS-TITAN-V2/pull/1

## Executive status

The ZIP-derived Phase 6 capabilities have been integrated additively into the V2 integration branch. The original V2 core, CSV/SQLite storage, baseline backtest engine, moving-average strategy, and chronological OOS validator remain in place.

**Latest confirmed combined CI evidence:** GitHub Actions run #41252347987 completed successfully with **266 tests passed** at commit `b1b624be0700673bda50b9e329e81e5d9da63a66`. A later storage package-export-only commit (`9fd7a9e7503fd7ca66e1408ed9f0f2248b41b20b`) triggered another CI run; that run must complete before the latest branch head can be called verified.

The uploaded ZIP's independent baseline suite previously reported **246 passed**. That result belongs to the ZIP by itself and must not be confused with V2 combined CI.

## Integrated in this branch

| Area | Files/capabilities added |
|---|---|
| Agent creation and runtime | Declarative ACE prototypes, allowlisted capabilities/tools, named human approval, SQLite task queue, idempotency, retry-safe adapters, workflow dependencies, inbox, metrics, and fail-closed interrupted-task recovery |
| EVOLVE | Learning store, improvement proposals, experiment records, skill metadata and human-gated promotion, 12 supervised specialist agents, regime detection/evidence, code proposals restricted to research files, source ingestion, optional LLM synthesis, and scheduled research |
| Research/backtesting | Advanced event-driven backtest, technical indicators (SMA/EMA/RSI/MACD/ATR/Bollinger), six V6 strategy candidates, rolling walk-forward validation, Monte Carlo stress testing, strategy promotion gates, and trade post-mortem |
| Data | Canonical OHLCV validator, CSV market-data loader and strict CSV validation helpers |
| Risk and costs | Legacy-compatible risk facade, authoritative risk engine, portfolio exposure/lot/tick sizing, daily-loss/consecutive-loss/drawdown lockouts, and configurable Indian statutory charge estimates |
| Derivatives and crypto | Theoretical Black-Scholes Greeks and IV solver; isolated crypto virtual account with generic symbol metadata, fee model, and optional VDA TDS calculation |
| Paper/virtual execution | SQLite durable account snapshots, paper order lifecycle, manual-approval callback, partial fills, idempotent fills, limit/stop orders, price-triggered exits, kill switch, emergency square-off, and reconciliation |
| Storage/trading/dashboard | SQLite and JSON trade ledgers, CSV signal-to-risk decision flow, virtual decision ledger adapter, and a read-only dashboard backend |

The V2 originals `research/backtest_engine.py`, `research/strategies.py`, and `research/validation.py` were not overwritten. V6 versions use separate names (`backtest.py`, `v6_strategies.py`, `v6_validation.py`) to preserve the existing baseline while integration continues.

## Test evidence

New focused integration tests cover ACE/runtime, advanced backtest, canonical data, portfolio risk, indicators, walk-forward/Monte Carlo/promotion gates, virtual paper account, durable recovery, options Greeks, crypto virtual-account behavior, AI risk veto, EVOLVE service boundaries, dashboard backend, risk compatibility, and trade ledgers.

- ZIP-alone suite: 246 passed (separate source tree).
- V2 integration branch: 266 passed at commit `b1b624be0700673bda50b9e329e81e5d9da63a66`.
- Latest branch head `9fd7a9e7503fd7ca66e1408ed9f0f2248b41b20b`: CI rerun pending at the time of this document update.

Tests are necessary but do not prove trading profitability, exchange-data accuracy, correct statutory taxation in every broker contract note, or production readiness.

## Not complete / remaining work

1. **Source parity audit:** ZIP files were integrated selectively and additively, with some modules adapted/reimplemented. A file-by-file API/behavior parity audit against the original ZIP and tests is still required. This is not a byte-for-byte ZIP extraction.
2. **Remaining V6 integration:** compare and, where useful, integrate any remaining archive modules and scripts; review storage and dashboard API contracts; bring ZIP test coverage across with explicit adaptations instead of assuming the original suite is compatible with V2.
3. **Advanced backtest verification:** test futures margin/cash accounting, costs by instrument and side, stop/target gap behavior, risk sizing, drawdown/equity metrics, and benchmark/annualization against independently calculated fixtures. No claim of exchange-grade simulation is made.
4. **Indian derivatives:** dynamic official contract master, verified expiry/lot/freeze/tick metadata, options-chain history, bid/ask liquidity, exchange SPAN/ELM margins, physical settlement/exercise/assignment, spreads, partial fills and intrabar option pricing remain unimplemented or incomplete.
5. **Crypto history/integration:** licensed exchange historical data, exchange-specific precision/min-notional/fees, funding, borrow/withdrawal costs and independent historical backtesting remain.
6. **Market data:** no production live-feed provider or licensed 15-year one-minute NIFTY/BANKNIFTY/options/crypto dataset is connected. Provenance, licensing, corrections, gaps, contract-roll and point-in-time universe metadata need external evidence.
7. **Paper execution fidelity:** market depth, bid/ask spread, realistic queue position, liquidity/partial-fill model, latency/slippage calibration, corporate actions and exchange halts need validation and expansion.
8. **Authentication/security:** manual approval is represented by a configured callback/named reviewer; production identity, MFA, per-user ACLs, secret management, encrypted-at-rest databases, backups, key rotation and independent threat modelling remain.
9. **Agent Runtime operations:** current implementation is local SQLite/in-process and does not provide distributed workers, sandbox isolation, durable cross-host coordination, or production observability. Tool adapters require deliberate review and registration.
10. **EVOLVE operations:** scheduled research is a callable one-shot worker, not yet wired to a scheduler/deployment; external fetches require explicit host allowlists; LLM provider requires operator-managed secrets and source verification. Generated code remains review-only and is not executed/applied.
11. **Dashboard/UI:** the backend returns read-only telemetry; the finished premium front end, authentication, responsive/mobile UI, charts and operator workflows remain.
12. **Data and deployment QA:** packaging/dependency lock, clean-install reproducibility, load/performance testing, backup/restore drill, disaster recovery, security review and complete end-to-end acceptance testing remain.
13. **Live trading:** deliberately disabled and out of scope for this merge. No broker adapter or live-order pathway may be enabled without a separate design, compliance review and explicit human approval.

## Safety invariants retained

- No generated Python execution, dynamic import, auto-deployment or automatic source replacement.
- ACE permanent registration and EVOLVE skill promotion require explicit human approval.
- Protected risk/permission controls cannot be modified by self-improvement agents.
- Agent tools are allowlisted; no default broker, shell, credential or arbitrary network tool is registered.
- Paper/virtual trading only; live mode is disabled.
- Strategy results cannot be promoted from unverified/small samples; historical backtests are not evidence of guaranteed returns.

## Merge state

This work is in an **open draft pull request** against `main`. The pull request is not merged. Keep it draft until the latest CI succeeds, the ZIP parity audit and remaining critical tests are complete, and the project owner has reviewed the diff.
