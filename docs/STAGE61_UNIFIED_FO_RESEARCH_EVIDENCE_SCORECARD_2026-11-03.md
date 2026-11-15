# NEXUS TITAN — Stage61 F&O Research Evidence & NO-GO Readiness Scorecard

**Date:** 2026-11-03  
**Parent:** Stage60 draft PR #52  
**Branch:** `feature/stage61-unified-fo-evidence-no-go-scorecard-2026-11-03`  
**Scope:** read-only, offline/synthetic. No real exchange data, broker account, order execution, authorized human identity or live trading.

## Objective and implementation choice

NEXUS TITAN already has separate research layers:

- **Stage44:** independently checked *source-declared* historical OPTIONS catalog. Structural integrity does not authenticate vendor, licence, NSE/contract metadata or synchronized executable depth.
- **Stage58:** multi-snapshot **synthetic** futures/options order-book execution and indicative Indian transaction-cost simulation. It does not know Stage60's future symbol/expiry/holdout binding, nor does it create broker confirmations.
- **Stage59:** bounded, per-session **NIFTY/BANKNIFTY FUTURES** CSV byte-hash, OHLCV grid, expiry/lot/tick and supplied-calendar preflight. The source, vendor, calendar and licence are untrusted operator declarations.
- **Stage60:** fixed-MA no-fill **out-of-sample next-close DIRECTION** experiment with train/embargo/holdout splits. Its hit rate is not a monetary P&L or a tradable signal.

**Stage61 unifies the evidence *review*, not their execution engines.** It does not create a broker/ledger bridge, fake portfolio profit, or assert that a Stage58 synthetic fill corresponds to a Stage60 forecast.

### `src/nexus_titan/research/stage61_evidence_scorecard.py`

`inspect_stage61_fo_evidence(history, oos, execution=None, option_catalog=None)` takes the **actual typed reports** from the existing Stage59/Stage60/Stage58/Stage44 modules, with no filesystem, network, broker, capital or order writes.

The immutable `Stage61FOMarketReadinessScorecard` contains:

- Core futures data identity: declared source digest, dataset ID, underlying, symbol, contract expiry, timeframe and inspected candle count.
- Out-of-sample fold/prediction counts and **descriptive** directional hit rate. Recounts held-out candidate labels, neutral signals, correct direction, flat-market misses and fold prediction observations, and rejects any origin/target outside its reported holdout. Does not estimate traded returns.
- Optional Stage58 **indicative** simulated execution fragment count and conservative fee reserve. It checks quantity conservation, ordering, no fake/no-fee fills, spread cost accounting fields, fragment fee sum versus aggregate reserve, finite numbers and no-authority flags.
- Optional Stage44 **declared** historical options window observation. Its mere presence never authenticates CE/PE prices, ensures contemporaneous futures/options quote alignment or authorizes strategy promotion.
- An ordered list of per-check results: `LOCAL_CONSISTENCY`, `CONFLICT` and `MISSING_EVIDENCE`, plus separate structural conflicts and missing evidence.
- A **local unkeyed SHA256** fingerprint over selected report inputs only when there are no local structural conflicts. It is not signature, vendor proof, immutable replay record, file rehash, audited time series or trusted market data attestation.

The Stage61 release blockers are explicit and **never cleared**, even when every available synthetic local report is structurally consistent:

1. No authenticated licensed real NIFTY/BANKNIFTY F&O data.
2. No independently authenticated point-in-time exchange contract master or calendar.
3. No independently observed bid/ask depth joined to actual OOS forecast and fill timestamps.
4. No validated real brokerage/taxes/exchange charges, settlement or margin.
5. No actual F&O monetary P&L, real fills, shadow execution validation or true strategy profitability.
6. No independent human identity or mandatory global Risk & Veto service.
7. No unified authoritative capital/settlement and no globally fenced legacy order/fill APIs.
8. No reconciled full draft-PR stack, prospective integrated-tree CI and explicit owner production approval.

### Important missing *cross-stage* join

The current Stage58 `Stage58ExecutionScenario` has **no authenticated contract ID, expiry or historical dataset pointer** bound to Stage60 fold/signal/label timestamps. Even an apparently complete synthetic fill and positive predictive hit rate must therefore be reported as:

```json
{
  "execution_scenario_bound_to_holdout": false,
  "actual_execution_or_fees_reconciled": false,
  "genuine_futures_options_backtest_verified": false,
  "strategy_promotion_authorized": false,
  "global_risk_veto_unbypassable": false,
  "unified_capital_settlement_verified": false,
  "live_trading_enabled": false,
  "production_ready": false,
  "broker_orders_transmitted": 0
}
```

A Stage58 fee value is **an independent synthetic QA scenario cost estimate**, *not* the actual brokerage for the Stage60 OOS forecast. One must not combine the two into net P&L, profit factor, execution slippage, Sharpe, drawdown or an automatic promotion signal. Nor should historical futures OHLCV volume/open interest be substituted for bid/ask liquidity.

A complete structural review is `local_inputs_structurally_consistent=true`; it is emphatically **NOT** a readiness percentage, green live release, verified backtest or regulatory/compliance approval.

## Tests / smoke

- `tests/test_stage61_fo_evidence_scorecard.py` composes genuine Stage59/Stage60/Stage58 **code outputs** over disposable NIFTY/BANKNIFTY fabricated data; checks exact identity linkage, OOS counts and double-bound holdout timestamps, source digest, optional missing execution, fee/reserve conservation, fabricated fill events/duplicate IDs, NaN/Infinity, spoofed source/strategy/identity/trading flags, bogus OPTIONS catalog authority, and never-true global release flags.
- `scripts/run_stage61_fo_evidence_smoke.py` writes temporary synthetic 46-bar data for both underlyings, invokes the Stage59 preflight, Stage60 embargoed OOS research and a **separately fabricated** Stage58 FUTURES cost/depth scenario, and prints one NO-GO scorecard per underlying. It never changes existing user files or connects market/broker services.
- The read-only Stage52 source inventory now includes the Stage61 schema/check classes, without presenting this AST scan as a functional security or real-source proof.

```bash
python scripts/run_stage61_fo_evidence_smoke.py
python -m pytest -q tests/test_stage61_fo_evidence_scorecard.py
python -m pytest -q
```

Only call Stage61 an **offline coding/testing milestone** after all three final PR-head GitHub Actions Python 3.11/3.12/3.13 checks and the existing Stage25 synthetic smoke pass. This does not establish readiness of the separately stacked draft PR series on a prospective integrated main-line tree.

## Concrete remaining work

- **Stage62 proposed:** prospective stacked-PR integration audit, cross-module contract/CI consistency and explicit environment/runtime controls; no merge without owner approval.
- **Stage63:** secure local user/operator read-only reporting, release blockers and the approved black/silver TITAN visual identity without changing locked layout; original digital-human face asset needs owner-supplied exact source.
- **Stage64:** deterministic paper/shadow trial governance, dataset/cost coverage and externally verified trial evidence required before any strategy promotion claim.
- **Stage65:** owner-controlled end-to-end deployment/recovery audit with real-data and credential isolation prerequisites, production NO-GO until independently verified.

**Owner must explicitly approve any merge or release. No real-money/live trading, no automatic promotion.**
