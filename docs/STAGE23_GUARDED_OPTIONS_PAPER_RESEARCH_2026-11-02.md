# Stage 23 — Independent Risk + Veto Before Offline Research Execution

## Scope

Adds a small **opt-in BUY-only research admission adapter**:
`nexus_titan.shadow.guarded_options_research.guarded_options_research_buy`.

It composes existing components; does not replace risk rules, permission
policy, option execution simulation or Stage19 SQLite ledger.

### Ordering

1. Explicit `Action.PAPER_TRADE` permission through existing
   `core.permissions.decide`; **default denied**.
2. Existing research ledger must be flat (no open reservations or
   existing unvalued inventory). Avoid falsely assuming that unknown option
   exposure is zero.
3. Source quote, quote identity, exact NSE contract and exposure/risk context.
   Capital comes from the **actual research ledger's available cash**, not
   a user-inflated capital parameter.
4. `AuthoritativeRiskEngine.size_and_validate`, as used by the existing
   `TradingIntelligencePipeline`. The requested quantity must not exceed
   its approved whole-lot quantity. Loss streak, drawdown and daily-loss
   circuit breakers are operator-supplied **research** context.
5. Independent exact-contract `PortfolioRiskManager.evaluate_order`
   using `contract.to_instrument_spec()`. Needed because the authoritative
   facade falls back to generic instrument limits on unknown symbols.
   **Both** calculations must approve the full request.
6. Existing adversarial `challenge_trade` independently vetoes weak
   expected edge or insufficient displayed top-of-book liquidity. The
   **actual selected quote's bid/ask spread** determines spread cost; the
   caller cannot substitute an artificially narrow spread. The expected
   edge, like market-data source metadata, is an unverified assertion.
7. **Only after all checks pass**, Stage17 offline simulator runs and Stage19
   research SQLite ledger reserves premium and a caller-supplied fee buffer.
   Any failed settlement attempts terminal reservation cancellation. Stage19
   independently checks cash and fill accounting; no broker action exists.

The guard is deliberately **not a production-grade atomic, global
risk-to-order admission**. Current risk-check/ledger-write boundaries are
separate transactions, so an independent process could change exposure in
between. The ledger remains a BUY-only research prototype; direct Stage19
methods are not retroactively wrapped by this opt-in adapter. The adapter
rejects accounts carrying open reservations or existing option inventory
until a fuller, independently approved portfolio risk valuation exists.

### Example — synthetic/offline, NOT official NSE quotes or broker prices

```python
from nexus_titan.shadow.guarded_options_research import guarded_options_research_buy

result = guarded_options_research_buy(
    ledger=local_research_ledger, order_id="TEST-001",
    event_id="SYNTHETIC-001", history=synthetic_research_history,
    contract=declared_research_contract, calendar=operator_supplied_calendar,
    observed_at=research_timestamp, strike=100.0, option_type="CE",
    lots=2, depth=synthetic_displayed_depth,
    stop_price=5.0, max_unit_premium=6.0, fee_buffer=25.0,
    expected_edge_bps=2000.0, slippage_bps=1.0,
    paper_trading_enabled=True,  # explicit, paper RESEARCH only
    realized_daily_loss_pct=0.0, consecutive_losses=0,
    current_drawdown_pct=0.0,
)
assert result.live_orders_transmitted == 0
assert not result.approved_for_strategy_promotion
```

The numbers above exist **solely to exercise deterministic test branches**.
The oversized synthetic edge is not a real return forecast.

## Negative paths required by tests

- Permission absent/false/nonboolean: default **DENY**, no ledger mutation.
- Authoritative or exact-contract risk veto, stop-direction failure, daily
  loss, streak, drawdown, insufficient virtual capital: **DENY**.
- Red-Team veto for insufficient visible depth, spread/slippage friction
  exceeding an operator-claimed edge: **DENY**.
- Stale, forged or unsynchronized depth never becomes executable liquidity;
  OHLCV volume is not a substitute for displayed depth.
- Failed settlement releases the new research reservation through terminal
  cancel, with an explicit manual-audit error if cancel fails.
- A successful test does not imply a genuine position or real order.
  Neither the code nor this report enables live-trading or promotion.

## Still missing for genuine paper/shadow operation

- Immutable, operator-approved and **source-authenticated** market-data feed,
  expiry/lot-size metadata and official sessions.
- Actual independent portfolio exposure and margin, daily P&L and stop
  enforcement, multi-order reservations and atomic risk decision binding.
- Order admission sequencing across processes with durable, signed, tamper
  resistant decisions and manual-approval account integration.
- Full SELL-side close/expiry lifecycle, genuine execution receipts and
  externally calibrated costs, then independently reviewed multiday results.
- Existing draft PRs #6–#14 require ordered review before any merge.
  `main` remains unchanged; live trading remains **disabled**.
