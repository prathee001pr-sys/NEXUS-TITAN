# Stage 25 — SELL-aware Multi-Day Reconciliation and Offline Research Backtest

**Safety boundary:** Research-only, all bundled histories synthetic; no
broker order, real market feed, licensed option-chain capture or production
approval is activated. Stage25 is stacked on draft PR #16; `main` stays
unchanged unless the owner explicitly approves review/merge.

## What Stage25 actually connects

- `src/nexus_titan/shadow/research_reservation_ledger.py`: new BUY
  `SETTLE_BUY` audit metadata **only for new simulated records**:
  `fill_observed_at_utc`, `buy_premium_cents` and `buy_fees_cents`.
  It conserves the already existing `debit_cents`, quantity, replay-ID,
  reservation, hash chain, and prior risk/permissions behavior.
- `src/nexus_titan/shadow/sell_aware_multiday.py`:
  `reconstruct_sell_aware_daily_journal` reads audited BUY+SELL research
  fills with explicit event timestamps, groups by supplied NSE India market
  sessions, and rebuilds every trading day between first and last event,
  **including days with no fills**. It keeps cents exact:
  `closing_cash = opening_cash - buy_premium - buy_fees + sell_gross - sell_fees`.
  FIFO entry basis and cash accounting are independently replayed and compared
  to Stage19 SQLite and Stage24's long-exit audit before returning.
- `inspect_sell_aware_day_closes` checks one independent operator-supplied
  day-close claim per day, including India post-close time, account ID, cash,
  remaining long-option quantity, FIFO cost basis, and **signed** cumulative
  realized net P&L. Any missing/truncated/duplicate/out-of-order session,
  incorrect cash/P&L, missing evidence references, invalid dates or source
  mismatch blocks structural acceptance.
- Existing BUY-only `inspect_multiday_shadow_evidence` from Stage20 and
  `prepare_unified_shadow_readiness` from Stage21 remain unmodified:
  neither is retroactively promoted into SELL-enabled production approval.

## Important restrictions

- A Stage19 BUY record without a time and separate buy-premium/fees cannot be
  assigned an actual day or reconciled independently. **Legacy records fail
  closed** rather than guessing a fill date or fee schedule. An explicit
  versioned migration and verified original event timestamps are needed for
  older live research datasets.
- When a long option remains open, the report states
  `incomplete_mark_to_market=True`; **cash or realized P&L is not equity**.
  No real market price, implied-volatility mark or expiry exercise is inferred.
- A passing internal paper journal only proves **structural consistency** of
  self-declared synthetic events and a local audit hash chain; it cannot
  establish licensed data, official sessions, broker receipts, actual fills,
  measured latency or market profitability.
- Entire account must have no unresolved open virtual cash reservations to
  reconstruct an unambiguous terminal snapshot.
- Source dates and intraday session limits are derived from the operator's
  `MarketCalendar` and remain unverified until an official holiday calendar
  is provided.
- Stage24's `SETTLE_LONG_EXIT` (a local, long-inventory-only SELL) is not a
  market short order, not a broker trade and does not imply live risk approval.

## Test and backtest commands

From repository root on a complete branch:

```bash
python scripts/run_project_validation.py
python scripts/run_stage25_full_research_audit.py --json-out reports/stage25_full_offline_audit.json
python -m pytest -q tests/test_stage25_sell_aware_multiday.py
```

The second command reruns all available basic strategies on both **bundled
synthetic** sample CSVs, the Phase7 advanced/backtest/Monte Carlo/walk-forward
research/golden-fixture suite, and Stage22 offline options research smoke.
It returns source dataset SHA-256 and exact strategy P&L numbers, **but marks
them unverified and not tradable**. CI uploads this report as an artifact.

## Final release blockers

- Full authoritative Risk & Veto still needs globally atomic and unbypassable
  order admission rather than a separate optional research adapter.
- No verified licensed 15-year NIFTY/BANKNIFTY F&O 1-minute snapshots and
  authenticated historical option chain/level-1 depth are supplied.
- Trade cost calibration, current official contract expiry/lot-size changes,
  risk/margin, assignment, rollover, slippage and real broker reconciliation.
- No independently observed multi-day real-feed shadow series, audited
  profit factor/drawdown/P&L, human owner sign-off or offsite security drill.
- No complete dashboard/API/operator deployment E2E evidence or actual
  instrument-connected live compliance review.

**Do not infer deployability, profit potential or real order authorization
from any passing synthetic tests.**
