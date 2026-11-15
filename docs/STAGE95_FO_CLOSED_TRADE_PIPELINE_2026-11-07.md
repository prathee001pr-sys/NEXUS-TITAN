# Stage95 — selected Indian long-option closed-trade pipeline

Base: Stage94 plus draft security PR85, commit
`cb81a196824459826446977544b58ae20b6b4c24`.

## Scope and implementation

`FOClosedTradePipeline` composes the existing validated futures/option-history
import, as-of analytics, strategy signal, independent risk, selected signed
F&O gateway, Stage55 atomic SQLite journal and Stage89 closing accounting.
It creates no signing authority, broker adapter or new capital pool.

The actual SMA strategy uses only completed underlying bars at the options
observation time. Rising underlying proposes long CE; falling proposes long
PE. A distinct explicit second research-confirmation lane is required by the
existing consensus path. Confirmation is untrusted input, not calibrated alpha.

Paper access defaults OFF. SAFE requires a literal local approval instruction;
autonomous requests require RISKY, ON and an explicit autonomous allowance.
Neither mode changes the independent signed risk requirements. These flags
are local instructions and **not verified human identity**. The underlying
book still verifies exact-operation HMAC evidence and current risk/capital
under its own SQLite transaction. The adapter is not an OS/process boundary.

Entry/exit prices include explicit bid/ask spread and configurable tick
slippage. Declared available liquidity bounds partial fills. The existing
Indian cost engine calculates brokerage, STT, exchange/IPFT assumptions,
SEBI fee, stamp duty and GST; integer paise enter the durable ledger.
Charges are conservatively calculated per fill fragment, including a separate
brokerage cap per fragment; they are not an authenticated broker contract note.
Fee-buffer exhaustion, bad ticks, missing fees or mismatched signed economics
are rejected. Reducing a position still requires signed exact-contract close
authorization. Cancel and protective signed close remain available after stop.

The dashboard data contract derives accounting and performance from **one**
checked journal snapshot. It exposes no signing key and grants no trading
authority. The locked visual theme is unchanged; this adds backend report data.

## Verification and review

31 new focused tests exercise all four NIFTY/BANKNIFTY CE/PE combinations,
partial opening and closing, fee-aware net P&L, cash conservation, durable
restart, duplicate protection, permission/autonomy denial, stale/conflicting
signals, source mismatch, missing/expired permits, fee bypass attempts,
quote/spread/tick errors, liquidity bounds, emergency stop/protective close,
ledger corruption and unsupported/expired contract rejection.

The closed-trade assertions independently calculate
`gross = quantity * (exit_price - entry_price)` and subtract the ledger's
actual entry/exit fees. They check cash equals starting capital plus realized
P&L when flat, along with matching dashboard journal revision/tip.

A separate source/invariant review identified missing liquidity bounds before
checkpointing; four rejection cases were added. Existing risk/close/concurrency
regressions are included in the full-suite run. This is an automated engineering
review and a separate author review, **not third-party human security sign-off**.
Executed test counts, commit and publishing status are recorded in the stage
checkpoint; a local pass alone is not GitHub CI verification.

## Charge references and limitations

The inherited configurable schedule was checked against these primary sources
on 7 November 2026; no rate defaults were changed in this stage:

- [NSE STT schedule](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax)
- [NSE transaction-charge/IPFT circular FA73061](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf)

The selected account supports long CE/PE only. Futures history participates in
research, but **futures execution/margin and settlement are unsupported** and
rejected. Expired quotes/orders are rejected; expired-position exercise/cash
settlement is not implemented. No fabricated automatic expiry proceeds are paid.

Remaining release blockers: authenticated human approval/key custody, global
enforcement across legacy direct Python APIs, cross-market safety integration,
futures/expiry settlement, licensed real market data, calibrated liquidity and
broker charges, prospective real-feed shadow evidence, external review and
owner release approval. These local synthetic tests do not clear them.

## Local verification

From a clean checkout with Python 3.11–3.13 and the development dependencies:

```sh
python -m pip install -e '.[dev]'
python -m pytest -q -o addopts='' tests/test_stage95_fo_closed_trade_pipeline.py
python -m pytest -q -o addopts='' tests/
```

No live trading, real credentials, repository visibility change, main merge or
force push is part of this stage.
