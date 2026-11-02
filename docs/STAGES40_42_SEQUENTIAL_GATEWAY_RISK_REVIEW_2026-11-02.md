# NEXUS TITAN — Stages 40–42 Sequential Engineering Review
**Date: 2026-11-02. Synthetic research-only, stacked draft PRs.**

## Executive summary

Stages40–42 improve **optional, strict, paper-only** order admission,
pending BUY risk policy integrity and a combined recovery audit. Their
CI coverage is regression evidence for Python software logic—not
exchange data validation, broker readiness or expected profits.

| Stage | PR | Delivered capability | CI |
| --- | --- | --- | --- |
| 40 | [#32](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/32) | One-way SQLite gateway-only account policy; explicit flat/guarded migration, direct normal BUY/SELL submission blocked; manual gateway and emergency close kept | 1,046 tests + 5 subtests; three Python versions green |
| 41 | [#33](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/33) | Durable BUY policy SHA256; approve/fill rejects changed risk/capital/margin/underlying effective PortfolioRiskManager configuration; safe partial fills and SELL | 1,056 tests + 5 subtests; three Python versions green |
| 42 | Stacked draft PR after #33 | Isolated synthetic Stage40/41 E2E safety lifecycle, signed-authority negative assertions, restart, CAS conflict and kill switch | Python matrix and 5 integration regressions |

## Stage40 security scope

`enable_gateway_only_mode(research)` requires explicit strict
mode, validated guarded research ledger, matching account IDs, a flat
research and virtual account, configured identity callback and
manual trading mode. Normal direct `submit_order()` refuses on these
opted-in accounts. SQLite never lets normal snapshots downgrade the
gateway-only flag; Stage38 revision CAS stays enabled.

**Known gap:** This is an in-process Python convention; anyone who can
mutate Python runtime state or private functions can bypass it, and
legacy accounts remain supported for research. It is NOT a global
mandatory security service.

## Stage41 anti-drift scope

Pending gateway-only BUY intent records include an unsigned,
versioned-in-code risk-policy fingerprint. Approval and fills reject
changed policy, capital, margin or risk engine effective settings.
Historical legacy order snapshot hashes remain unchanged. Partial
BUYs and owned SELL-to-close remain available.

**Known gap:** Fingerprint is recomputable with access to source/runtime;
market input and independent risk identity not authenticated. Real-time
execution realism and order-book liquidity are not proven by this hash.

## Stage42 acceptance

`scripts/run_stage42_gateway_risk_e2e.py` uses only temporary
SQLite/virtual account paths and synthetic instrument ABC, with
configurable ₹50k initial simulation capital. It verifies strict,
gateway-only restart, manual approval, default-deny paper permission,
inability to directly submit orders, old policy rejection before
approval and fill, stable BUY, stale-process compare-and-swap failure,
no naked SELL, owned SELL settlement, kill switch, emergency exit,
restart lock persistence, and no AUTO_PAPER escalation.

Every output includes explicit false statements for:
`cross_ledger_atomicity_verified`, `externally_authenticated_identity`,
`real_market_data_approved`, `production_ready`,
`automatic_strategy_promotion`; and zero live orders transmitted.

## Remaining P0 blockers

1. Opt-in mode is still not mandated for all existing legacy research
   execution entrypoints.
2. Separate VirtualAccount and Stage19 research ledger share **no
   atomic capital reservation or aggregate exposure ledger**.
3. Authentication callbacks and unsigned SHA evidence do not prove
   independently authenticated identity or signed one-shot approvals.
4. Broker access is absent by design. Emergency exits are simulated,
   not connected to actual exchange positions.
5. Historical real NIFTY/BANKNIFTY F&O quote provenance, full contract
   chain metadata, bid/ask depth, 1-minute historical gaps, exchange
   charges and licensed vendor rights have not been established.
6. A passing synthetic test cannot support estimates of trading
   profitability, execution latency, real slippage, or an approval
   to trade with real capital.
7. There has been **no merge into protected main**. Stacked PRs need
   independent review, ordered merge, and independent combined CI.

## Later stages (proposed, not completed here)

- Stage43: independent deploy-time safety boundary review, integration
  merge plan and secrets/identity isolation design.
- Stage44: actual approved market-data import/coverage/provenance
  verification, then realistic backtests *only once data are supplied*.
- Stage45: extended shadow-trading acceptance and operational safety
  evidence (not a promise of real-money trading approval).

**Release verdict: RESEARCH-ONLY / NOT PRODUCTION-READY.**
