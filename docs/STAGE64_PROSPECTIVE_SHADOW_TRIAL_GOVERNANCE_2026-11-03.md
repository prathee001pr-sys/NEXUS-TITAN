# NEXUS TITAN — Stage64 Prospective Shadow-Trial Governance (NO LIVE)

**Date:** 2026-11-03  
**Parent:** Stage63 draft PR #55  
**Branch:** `feature/stage64-prospective-shadow-trial-governance-2026-11-03`  
**Scope:** offline **synthetic or unverified operator-claimed** paper trial assessment, not authenticated market shadow trading or a strategy deployment approval.

## Design decision and dependencies

This stage **reuses rather than rewrites** the existing:

- Stage19/20/21 shadow research ledger, daily recovery and external-evidence-review preparation;
- Stage58 indicative order-book friction stress (independent synthetic quotes);
- Stage59 futures history quality preflight;
- Stage60 embargoed directional OOS experiments, **not executable F&O P&L**;
- Stage61 combined source/OOS/synthetic execution evidence blocker scorecard;
- Stage62 frozen GitHub PR/source/CI read-only architecture audit;
- Stage63 offline black/silver operator dashboard.

Stage64 does **not** connect any of those research-only reports to a live market, finance account, gateway or actual broker fill. It cannot take real orders, activate autonomous trading or promote TITAN EVOLVE challengers.

### New module: `src/nexus_titan/shadow/stage64_trial_governance.py`

`Stage64TrialPlan` defines an intended **single-market** NIFTY or BANKNIFTY trial, with variable starting capital, strategy version, window, declared registration timestamp and **explicit predeclared thresholds**. Defaults are illustrative governance starting points, not statutory/SEBI risk limits:

| Local diagnostic requirement | Default |
| --- | --- |
| Minimum configured sessions | 20 |
| Claimed closed trades | 30 |
| Claimed execution observations / closed trade | 2 |
| Max reported drawdown | 1000 bps = 10% |
| Minimum gross profit factor | 1.20 |
| Minimum declared net expectancy | 1 cent/trade |
| Missing configured-market session days | 0 |
| Data quality flags, order reconciliation and flat inventory | Required |
| Risk policy breaches | 0 |

The plan MUST declare a `registered_at` before the operator-configured start session opens. **This timestamp can be forged/backdated**: it is NOT a remotely timestamped or cryptographically signed strategy registration. A trusted independent registration and a locked parameter version remain external prerequisites.

`Stage64DailyClaim` has explicit:

- Per-date India-timezone-aware end-of-session observation, account, underlying and `FABRICATED_QA` / `OPERATOR_DECLARED_PAPER` **unverified** source.
- Opening and closing virtual cash, gross winners, gross losers, fees, slippage, counts of completed winning/losing/flat trades, execution observations.
- Missing-market-observation count, risk breaches, unresolved orders, unvalued positions, claimed intraday drawdown, submitted data-quality and paper-reconciliation flags.
- Hard-disabled `independently_authenticated_data`, `independently_authenticated_fills`, `real_money_order_sent`.

`inspect_stage64_shadow_trial(plan, days, calendar, as_of, fo_evidence, integration)` is **pure read-only**. It checks:

1. Accounts/market/date/session align, candle-exchange calendar is explicit `Asia/Kolkata`, daily observations are ordered, distinct and **after the configured market close**, no future-dated or out-of-window values.
2. All configured trading dates across the declared window are present. No weekend/holiday is assumed to be a trading day from the supplied calendar. **The calendar is operator-configured, not authenticated as official NSE historical holidays or special sessions**.
3. Exact integral cents and trade counts; winners + losers + flats = total claimed closes. Gross win/loss amounts match their respective positive counts.
4. Cash continuity and simple flat-account conservation: `closing_cash = opening_cash + gross_wins − gross_losses − fees − slippage`. If unvalued open positions exist, reconciliation is not a pass. Financial fields and market volume still remain **unverified caller assertions**.
5. Trial summary computes **claimed gross profit factor**, **claimed net per-trade expectancy**, fees, slippage, day-close peak-to-trough drawdown and maximum **claimed** intraday drawdown. A zero-loss sample has undefined gross PF, never magic infinite profitability.
6. Session quality, zero unresolved orders/inventory, no stated risk breaches, adequate observation count, capital drawdown and thresholds are assessed as separately named local checks.
7. Actual Stage61 scorecard underlying and Stage62 audited interface status are checked. Their structural success is **not** market-source authentication, independent identity, prospective merged-tree CI, or globally mandatory risk enforcement.
8. A deterministic unkeyed SHA256 over the supplied plan/day declarations and referenced Stage61/62 fingerprints helps detect accidental fixture changes. It is **not tamper-proof**: anyone able to modify the data can recompute this hash, so it is not an audit signature.

### Interpretation and safety invariants

Even if every local synthetic KPI passes, the returned `Stage64ShadowTrialGovernanceReport` **always** sets:

```json
{
  "data_source_independently_authenticated": false,
  "real_fill_or_fee_calibration_verified": false,
  "genuine_net_pnl_verified": false,
  "prospectively_signed_trial_plan_verified": false,
  "audited_full_portfolio_pnl_verified": false,
  "independently_verified_human_approval": false,
  "one_authoritative_capital_authority_verified": false,
  "global_risk_veto_enforced": false,
  "merge_authorized": false,
  "strategy_promotion_authorized": false,
  "live_trading_enabled": false,
  "production_ready": false,
  "broker_orders_transmitted": 0,
  "release_decision": "BLOCKED_INDEPENDENT_EXTERNAL_EVIDENCE_REQUIRED"
}
```

Local trial success is **not** a real-data validation percentage or permission to use real money. Even `OPERATOR_DECLARED_PAPER` claims are not trusted as genuine exchange observations, actual fills or brokerage reconciliations.

All eight external blockers are permanent in this version:

- Genuine licensed market history and rights independently verified.
- Authenticated market quotes **bound to actual order/fill timestamps**.
- Date-specific, broker-specific fees, margin and settlement verification.
- Independently timestamped/signature-verified trial and detailed trade log.
- Independent human strategy promotion approval.
- One unbypassable mandatory Risk & Veto/execution boundary.
- One authoritative atomic capital account and crash-safe reconciliation.
- Owner-approved integrated draft-PR merge and complete release/security CI.

No attempt is made to infer profitability from Stage60 directional-hit percentages or merge Stage58 indicative fees into non-executed futures P&L. **A report cannot prove active positions' unrealized P&L or tick-level intraday drawdown; those require separately verified market and account state.**

## Smoke and tests

`scripts/run_stage64_shadow_trial_smoke.py` runs actual Stage61 and Stage62 code reports plus two **fabricated** NIFTY/BANKNIFTY paper-trial claims using 20 configured weekdays in September 2026 and 40 nominal closed trades per underlying. Starting capital is deliberately variable (example ₹35,000); it is **not pinned to ₹50,000**. The example generates internally consistent positive net-after-declared-fee arithmetic to demonstrate a local KPI pass, **not real NIFTY/BANKNIFTY performance**.

`tests/test_stage64_shadow_trial_governance.py` checks:

- Both underlyings, variable starting capital, 20-day configured calendar coverage, exact cents/fees/slippage, trial-gross PF/expectancy and drawdown arithmetic.
- Missing middle session, duplicate/out-of-order dates, cash drift, omitted transaction costs, wrong market calendar, early market-close observation, future dates, forged timestamps/unauthenticated market or brokerage assertions.
- Trade count/win-loss conservation, bad numeric/Boolean values, gross PF nondefinition if no loss data, gross profitability that collapses to negative after costs, risk breaches, low execution observations, unresolved/unknown positions, data quality gaps.
- Stage61/62 schema/market/authority mismatches and mandatory no-promotion invariants, no external API or user-data mutation.

Run:

```bash
python scripts/run_stage64_shadow_trial_smoke.py
python -m pytest -q tests/test_stage64_shadow_trial_governance.py
python scripts/run_project_validation.py
```

Stage64 synthetic smoke is also included explicitly in the **Python 3.11/3.12/3.13 GitHub Actions matrix**, alongside existing Stage25 and Stage62 checks. Call the stage **tested** only if CI succeeds on the FINAL PR HEAD, not an earlier partial commit. CI does not authenticate any sample market history.

## Stage65 next

**Final consolidated acceptance/security/merge readiness review (NO-GO by default)**. Reconcile both main-rooted draft PR stacks and all affected file diffs; do prospective merged-tree CI, owner-controlled branch protection review and independent security check. Integrate and verify licensed NSE contract/option history, fees, true executable quotes, global risk/capital authority, authenticated human identity and actual supervised paper performance in later owner-controlled work. A Stage65 code milestone is not an implied production launch.

Keep Stage64 PR DRAFT / UNMERGED. No real trading, no owner-independent strategy promotion, no actual market-data upload until owner supplies approved evidence.
