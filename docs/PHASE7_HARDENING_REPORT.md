# NEXUS TITAN V2 — Phase 7 Hardening & Backtest Report

**Release status:** hardened research / virtual-paper snapshot; **not production-ready**  
**Live trading:** disabled  
**Last local verification:** 2026-11-01  
**Python used for local verification:** 3.13.5

## Executive summary

The uploaded Phase 7 archive was retained as the starting point and hardened additively. The existing architecture and features were preserved where possible. Critical fixes were added for approval replay, instrument metadata fallback, market-data timezone handling, dataset integrity, options-chain liquidity checks, microstructure input validation, account persistence and backtest input validation.

Final local test evidence at the time of this report:

- `python -m compileall -q src tests scripts`: passed.
- `python -m pytest -o addopts= -q`: **318 passed, 5 subtests passed**.
- `python scripts/run_project_validation.py`: completed successfully.
- `python scripts/run_advanced_backtest_suite.py --json-out reports/phase7_advanced_backtest_report.json`: completed successfully and emitted a test-evidence-backed G0–G9 report.

This is local evidence on Python 3.13.5. The repository CI workflow now has a Python 3.11 / 3.13 matrix, but a remote GitHub Actions run was not triggered by this local archive edit. Python 3.11 is therefore **not claimed as locally verified**.

## Hardening work completed

### Security and approval lifecycle

- Approval token consumption moved from a process-local memory set to a durable SQLite one-time-use registry.
- Token verification now checks canonical HMAC payload, actor/role, target and snapshot binding, expiry, future-issued timestamps and bounded TTL.
- The regression suite verifies that a token consumed by one verifier is rejected by a fresh verifier using the same database.
- Signing secrets must remain outside the database in a deployment secret store. SQLite durability does not itself provide MFA, identity proof or encrypted-at-rest storage.

### Instrument metadata and data integrity

- Unknown instrument symbols no longer silently resolve to lot size 1.
- The bundled point-in-time instrument catalogue is now explicitly labeled **unverified static research reference data**.
- `resolve_verified_lot_size()` fails closed unless a record is explicitly accompanied by a source reference and marked verified. This flag is an operator assertion; the actual official circular / contract-master evidence still must be independently checked and retained.
- Naive CSV timestamps are interpreted in the declared source timezone (default `Asia/Kolkata`) and converted to UTC. A bad timezone causes validation failure.
- Dataset SHA-256 requires exactly 64 hexadecimal characters and full digest equality.
- Hashing streams the file in chunks rather than loading the full data file into memory.
- Dataset promotion eligibility now requires licensed-exchange-history classification, a vendor and licence identifier, survivorship-bias-free evidence, no declared missing/duplicate bars, canonical CSV validity and exact manifest/file agreement.
- A checksum proves byte identity, **not** vendor identity or legal data entitlement.

### Options and microstructure input safety

- Option-chain validation now rejects crossed quotes, malformed prices/expiry/timestamps, excessive spread, zero open interest and invalid size/volume fields.
- Microstructure validation now rejects unknown sides/order types, non-positive or fractional quantity, invalid lot multiples, non-finite values, crossed books, invalid depth and off-tick limit prices.
- Stale-quote rejection and a basic spread-crossing / partial-fill smoke fixture run in the advanced report.
- The simulator remains a simplified model. It is not exchange queue reconstruction and is not calibrated from licensed tick/order-book history.

### Virtual-account persistence

- `ShadowPaperRunner` now uses a durable account-state directory by default; tests confirm open positions and orders restore when a runner is recreated against the same state directory.
- A restored account now rejects a configured starting-capital mismatch instead of silently accepting an inconsistent caller baseline.
- Persistence is local SQLite. Production encryption, access controls, backup/restore drills and multi-process coordination remain external acceptance work.

### Backtest correctness / scope controls

- OHLCV inputs are checked for finite numeric values, positive prices, non-negative volume and plausible high/low bounds.
- Parseable timestamps must be strictly increasing, unique and timezone-consistent; partial/malformed timestamp columns are rejected. DST-ambiguous or nonexistent naive wall times require an explicit UTC offset.
- Each strategy callback receives a read-only prefix ending at the current candle, not the full future dataset; this blocks ordinary look-ahead access and accidental mutation through the callback input.
- Signals are constrained to `-1`, `0`, or `1`; quantity must be whole units; stop/target and sizing inputs are bounded.
- Intraday equity positions are closed at a session boundary instead of being carried overnight.
- Short-option backtesting is explicitly blocked until an exchange-calibrated portfolio SPAN/ELM model is provided.
- `capital_risk` sizing requires a declared protective stop rather than estimating risk from notional alone.

### Costs, gates and reporting

- Indian cost inputs reject invalid quantities, prices, sides and malformed rate configuration.
- Total charges are summed from individually rounded fee components to avoid component/total cent mismatches.
- The advanced report no longer uses a hard-coded test count; it executes pytest and parses the actual test summary. A skipped test execution cannot pass G0.
- G3 includes hand-calculated arithmetic fixtures for futures indicative margin, buy/sell transaction-cost components and index-option expiry P&L.
- Fixture scope is explicitly limited to arithmetic under the configured model. It does not validate the current statutory rate schedule, official exchange SPAN/ELM, broker contract notes, stock-option physical delivery or exercise/assignment obligations.
- The report records actual test counts, safety smoke evidence, strategy metrics and G0–G9 gate status. The instrument catalogue is labeled as unverified reference data.

## Backtest results — interpretation

The shipped sample `data/nifty_daily_sample.csv` is a **synthetic smoke-test fixture** with 120 bars. It is not an official NSE feed, not a 15-year dataset, not licensed exchange history and not usable for strategy-promotion conclusions.

Eight strategy candidates were run against this fixture. None was promoted. The scorecards showed only 1–3 trades per strategy, and walk-forward out-of-sample samples were far below the configured minimum evidence requirement. Several strategies showed negative net P&L after indicative charges. One positive sample return is not evidence of an edge.

The futures demonstration contains only three synthetic trades (including one short trade). Its reported positive return / high profit factor are not statistically meaningful with this sample size. The futures engine still needs independent margin, roll, contract-expiry, partial-fill and side-specific accounting verification with actual historical data.

The ₹50,000 virtual shadow demo ledger reconciled within the implementation's one-paisa tolerance and transmitted zero live orders. This is a deterministic demo, **not a multi-day paper-trading observation**. Crypto silo reconciliation also passed a local simulated round trip; no exchange feed or historical crypto dataset was connected.

Detailed machine-readable results are in `reports/phase7_advanced_backtest_report.json`.

## Latest G0–G9 gate result

At the last advanced-suite run:

| Gate | Status | Meaning |
|---|---|---|
| G0 — Build reproducibility | Passed (code evidence) | 318 tests and 5 subtests passed on local Python 3.13.5 |
| G1 — API / behaviour parity | External evidence required | Adapted source APIs need line-by-line independent parity review |
| G2 — Data integrity | External evidence required | No verified/licensed 15-year point-in-time exchange dataset supplied |
| G3 — Accounting accuracy | Passed (model arithmetic fixtures) | Cash/fee/partial-exit and limited futures/options formula fixtures reconcile; not contract-note certification |
| G4 — Risk / approval safety | Passed (bounded code smoke checks) | Durable replay, stale-feed block, kill switch and daily-loss lockout smoke checks pass; not a penetration test |
| G5 — Execution realism | Passed (bounded fixture) | ₹50k demo ledger and basic microstructure fixture reconcile; not calibrated exchange execution |
| G6 — Independent security | External evidence required | No independent penetration test / threat-review sign-off |
| G7 — Operations / recovery | External evidence required | No independent backup, restore, crash-recovery or disaster-recovery acceptance evidence |
| G8 — Multi-day paper evidence | External evidence required | No multi-day observation on licensed data |
| G9 — Release sign-off | External evidence required | Owner sign-off and preceding release evidence are incomplete |

**Summary: 4 code-evidence gates passed, 0 failed, 6 require external evidence.** A passing gate above is narrowly scoped as described; it is not general production approval.

## Remaining work that cannot be completed from the ZIP alone

1. Obtain licensed 15-year one-minute NIFTY / BANKNIFTY / futures / options data and a verified point-in-time instrument master, expiry calendar, freeze limits, tick sizes and corrections history.
2. Reconcile every cost schedule component against actual broker contract notes and official exchange / regulator rate notices for each instrument, trade side and effective date.
3. Implement exchange-calibrated portfolio SPAN/ELM and stock-option physical settlement, exercise, assignment, delivery, expiry and penalty-margin accounting. Keep short options blocked until then.
4. Independently calculate golden cash / equity / futures / options / crypto fixtures, including gap stops, partial fills, rollover, funding, tax and corporate actions.
5. Complete line-by-line API / behaviour parity audit of adapted Phase 6 / Phase 7 modules.
6. Calibrate slippage, market impact, latency, queue position, participation and partial-fill assumptions from licensed tick / depth data.
7. Conduct independent security review / penetration test, MFA and role-based operator identity, key rotation, encrypted database/secrets, audit retention and permission-boundary tests.
8. Complete backup/restore, crash recovery, dependency lock, clean-install reproducibility, monitoring, resource limits and operator recovery drills.
9. Run an operator-controlled, multi-day ₹50,000 shadow period with immutable daily statements, reconciliation, incident logs and strategy evidence thresholds.
10. Finish the authenticated dashboard / mobile operator workflows and independent owner acceptance.

## Release / safety decision

- The code remains research and virtual/paper only.
- No live broker adapter, real-money order route or automatic deployment is enabled.
- Generated code remains review-only; no dynamic execution or self-deployment.
- EVOLVE cannot change protected risk controls, permissions, capital limits or live-trading state.
- Do not promote a strategy using synthetic or unverified research data.
- Do not treat this ZIP as a production release until the external evidence and acceptance gates above are complete.
