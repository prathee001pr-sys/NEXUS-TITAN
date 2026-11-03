# NEXUS TITAN — Stage 47 Local Offline Risk & Veto Boundary

**Date:** 3 November 2026  
**Branch:** `feature/stage47-offline-risk-veto-boundary-2026-11-03`  
**Base:** Stage46 draft PR #38  
**Safety verdict:** RESEARCH-ONLY ADDITIVE CODE; NOT GLOBAL/PRODUCTION RISK ENFORCEMENT.

## Engineering rationale

Existing `VirtualAccount.submit_order()` already has an authoritative
pre-trade risk calculation. Separately, options-research adapters run exact
contract risk and an adversarial Red-Team check. But Stage43/45's supported
paper startup and extra flat-entry facade do not make this complete
Risk & Veto chain globally mandatory, and direct legacy Python APIs remain.

This stage introduces an *additional restrictive* synthetic new-BUY path.
It is not an independent OS service, external identity proof, signed
single-use risk permit, atomic two-book admission or a broker-side firewall.

## New components

- `src/nexus_titan/operations/offline_risk_veto.py`: Stage47-only,
  immutable preflight decisions and a `Stage47OfflineRiskVetoEntry`
  wrapper over Stage45 and Stage43. Checks:
  1. Stage45 virgin-flat accounts, policy, manual opt-in and audit.
  2. Strict *synthetic-only* source reference, timezone-aware quote timestamp,
     max-age / future quote rejection and realistic spread derived from the
     quote, never caller-supplied spread compression.
  3. Bounded bid/ask, requested quantity, displayed ask depth, protective
     stop, estimated slippage and expected edge over friction.
  4. Existing active `AuthoritativeRiskEngine` and a separate exact
     `PortfolioRiskManager` with additional synthetic instrument quantity
     limits; refuses active/effective policy drift.
  5. Higher of supplied loss/drawdown/consecutive-loss metrics and local
     account metrics; rejects daily loss, drawdown and consecutive-loss
     breaches rather than lowering the account's observed risk.
  6. Existing `challenge_trade()` Red-Team veto and Stage43/45 recheck
     before submitting *only* an unfilled, manually approved virtual BUY intent.
- `tests/test_stage47_offline_risk_veto.py`: synthetic positive/negative
  regressions for stale/future and naïve timestamps, spoofed external source,
  quote invalidity, red-team friction, spread/depth/slippage, loss and
  drawdown, quantity limits, malicious policy types, kill switch and
  altered risk config, restart and no-order side effects.
- `scripts/run_stage47_offline_risk_veto_smoke.py`: temporary synthetic
  ₹50,000 virtual and research ledgers, valid gated pending order, duplicate
  entry rejection, stale quote refusal and zero simulated fills. Never
  downloads market data, contacts a broker, executes a live order or imports
  vendor proprietary sources.

## Deliberately blocked scenarios

This **does not enable NIFTY/BANKNIFTY options or futures**. Stage47's
small regression interface permits only `EQUITY_DELIVERY` synthetic
paper intent and does not infer exchange lot/tick, expiry or real depth.
For actual F&O data, verified licensed historical contract specifications,
exchange calendars and quote/depth metadata are needed; keep those for
the owner's later planned data upload.

All quotes and the optional test clock are **caller-supplied**, not signed
by a verified independent feed. External identity callbacks in Stage43
are application-local, not independently authenticated human actors.
Both `AuthoritativeRiskEngine` and `PortfolioRiskManager` run *in the
same mutable Python process*, so the Red-Team component is another
in-process veto layer, NOT a true external regulator/risk service.

Existing Stage43/Stage45 methods remain directly accessible. This
additional Stage47 facade is not unbypassable: a developer can call
legacy APIs without this extra check, or mutate runtime state.
The veto check also occurs before and outside the subsequent SQLite
order transaction, so concurrent state changes, source spoofing and
approval/fill-time market conditions are NOT solved here.
Independent Global Risk & Veto enforcement remains a separate P0 task.

## Verification

```bash
python -m pytest -q tests/test_stage47_offline_risk_veto.py
python scripts/run_stage47_offline_risk_veto_smoke.py
python -m pytest -q
```

Require 3/3 Python 3.11, 3.12 and 3.13 CI green on the final PR head.
If a test fails, fix and rerun; previous green commits do not substitute
for final-head evidence. No real data, broker access, merge or production
release is authorized by test success alone.

## Required subsequent milestones

- A separate OS/service-enforced central policy gateway with no bypass
  through legacy entrypoints; independently authenticated identity and
  signed, order-bound expiring approvals; approval/fill-time rechecks.
- One atomic capital/positions truth or independently and mechanically
  enforced isolated risk budgets for virtual and research ledgers.
- Genuine source licences, dated NSE metadata, realistic order-book
  backtests, extended market shadow evidence and owner-reviewed CI on
  the prospective merged Git tree.
- Connected premium dark dashboard as previously approved.

**Keep this PR draft and unmerged. No real-money trading, autonomous
strategy promotion or external broker activity.**
