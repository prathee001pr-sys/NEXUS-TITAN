# NEXUS TITAN — Stage 55 Single-Domain Synthetic Capital Lifecycle

**Date:** 2026-11-03  
**Branch:** `feature/stage55-single-db-synthetic-reserve-settle-2026-11-03`  
**Parent:** Stage54 Draft PR #46  
**Classification:** OFFLINE SINGLE-DB ACCOUNTING EXPERIMENT / NO BROKER AUTHORITY

## Goal

Stage54 confirmed that current Stage19 Research Shadow, Stage43 VirtualAccount,
Stage49 one-shot coordinator and Stage53 standalone budget have **four
separate transaction domains**. They must NOT be represented as one
atomic or fully reconciled capital authority.

Stage55 builds a *new, isolated SQLite proof of the desired lifecycle*
rather than modifying those existing databases: SYNTHETIC BUY intent
+ budget reserve, zero or more PARTIAL SYNTHETIC fills with fee accounting,
and cancellation that releases ONLY the still-unfilled reserved portion.
**This proves only intra-file accounting behavior for cooperating clients.**

## Code

### `src/nexus_titan/operations/isolated_atomic_execution_book.py`

`Stage55IsolatedSyntheticExecutionBook(db_path, account_id, starting_cents, policy, excluded_ledger_paths)`

- Requires explicit uppercase synthetic equity-delivery symbol, bounded
  positive integer quantity, integer-cent order limit, bounded fee buffer
  and unique operation IDs. It accepts **variable virtual capital**.
- Default QA reserve caps: 20% of starting capital per order, 50% open
  reserved aggregate. These are **test policy values**, not recommended
  portfolio risk percentages. Their risk semantics are NOT a trading
  stop-loss or SEBI-approved risk control.
- SQLite `BEGIN IMMEDIATE` serializes cooperating writers using the
  SAME file. The append-only-like `execution_events` journal and the
  `execution_head` cash/reserved/revision/hash are committed in **one
  SQLite transaction** and rechecked against complete journal replay.
- `reserve_synthetic_buy`: records PENDING_SYNTHETIC BUY intent, holds
  limit-price notional + fee buffer, does **not spend cash or create a
  real broker order**.
- `record_simulated_fill`: requires explicit
  `evidence_source="LOCAL_SYNTHETIC_TEST_ONLY"`, unique fill ID, limit
  price not exceeded, remaining units not exceeded and fees within
  remaining local fee buffer. Debits simulated spent cash; decreases
  the reserved amount at original limit, releasing any price improvement.
  Full fill also releases unused fee buffer. Partial fills preserve
  reserved cash for remaining units.
- `cancel_unfilled`: requires explicit test source and unique cancel ID;
  releases only remaining limit-price reserve and unspent fee buffer.
  Cash already consumed by simulated fills stays spent.
- `inspect`: replays and validates journal order, hash chain, cash
  conservation, reservations, head consistency, and status. On corruption
  the cash/reserve/available fields are **unknown**, with blockers.
- All activity is limited to a small **500-event demo journal**, deliberately
  inefficient full replay and unsuitable for production throughput.
- A local SHA256 hash chain **is not adversarially tamper-proof**; an
  actor able to edit the whole SQLite database could rewrite the
  events/head and recompute it. Path exclusions and symlink checks
  provide local QA guards only, not an OS-backed protected authority.
- No method transmits an order, modifies Stage43/19/49/53 ledgers,
  accesses a broker, reads true market prices, uses options/F&O
  position accounting or mints a human approval.
- The synthetic fill source label is caller-supplied; it is **NOT
  independently attested execution evidence**.

### Supporting evidence

- `tests/test_stage55_isolated_atomic_execution_book.py`: variable
  capital, reserve-not-spend, partial fill, fee and price improvement,
  full fill/unused fee release, cancel remainder without refunding
  already spent money, duplicate operation replay refusal, malformed
  prices/fees/IDs/symbols, policy caps, same-DB concurrency, restart
  reconstruction, crash injection after journal insert, corrupted event
  and head handling, wrong account/capital/policy/path, no broker APIs.
- `scripts/run_stage55_atomic_book_smoke.py`: disposable synthetic
  ₹50,000 example with ₹1,010 reserve, a simulated partial fill, cancel
  of remaining quantity, and restart comparison. No real market data.
- Stage52 structural code inventory includes the new Stage55 class
  interfaces, but is not an independent security validation.

## Accounting identities (all integer cents)

Before any fills:

```
available = cash - outstanding_reserved
outstanding_reserved = sum(open_order_remaining_qty * order_limit_price
                           + unspent_fee_buffer)
cash = initial_cents
```

After simulated fills/cancels:

```
cash + cumulative_simulated_buy_notional + cumulative_simulated_fees = initial_cents
available = cash - outstanding_reserved
outstanding_reserved >= 0
cash >= outstanding_reserved
```

This is only **cash accounting**: acquired inventory is NOT marked to
market; no realized/unrealized P&L, sell proceeds, futures margin, leverage,
crypto perpetual funding, daily loss, stop execution, partial broker fills,
orders outside this database, or external fee tariff reconciliation.

## Safety boundary and gate status

| Requirement | Stage55 |
| --- | --- |
| Reserve + synthetic fill + cancel in same DB transaction domain | Implemented/tested |
| Exact integer-cent conservation inside Stage55 file | Implemented/tested |
| Restart/replay + duplicate ID/concurrency checks | Implemented/tested |
| Verified broker fills / real market quotes | **NO** |
| Integrated with Stage43 VirtualAccount | **NO** |
| Integrated with Stage19 research reservations | **NO** |
| Integrated with Stage49 coordinator | **NO** |
| Integrated with Stage53 standalone holds | **NO** |
| Cross-database atomicity for existing books | **NO** |
| Independent Risk & Veto / legacy bypass prevention | **NO** |
| External human approval/credential isolation | **NO** |
| Real-money trades / live broker connection | **DISABLED** |
| Production-ready | **NO** |

An in-process caller could fabricate the test fill source or choose a
different DB. Therefore Stage55 must NEVER be wired directly into
live or autonomous trading. Its `record_simulated_fill` and
`cancel_unfilled` release simulated reservations **only within
this new isolated test database**. This does NOT enable unsafe release
of the earlier Stage53 capital holds or the Stage49 crash marker.

## Verification commands

```bash
python scripts/run_stage55_atomic_book_smoke.py
python -m pytest -q tests/test_stage55_isolated_atomic_execution_book.py
python -m pytest -q
```

Only claim Stage55's **offline coding milestone** verified after final
PR-head 3/3 Python 3.11/3.12/3.13 Actions jobs succeed, plus Stage25
offline smoke. Passing CI cannot authorize real-money orders, a
production release, or claim a globally enforced capital authority.

## Next architecture step — Stage56

Define a global non-bypassable risk/admission boundary with separately
controlled order credentials, independent preflight and approval/fill-time
risk recheck. A further owner-reviewed integration design must specify
which single transaction source will eventually REPLACE rather than
coexist with the four independent accounting authorities, while
preserving manual recovery and legitimate protective exits.

Do not merge staged PRs or attach real data/brokers without explicit
owner review and combined-tree CI.
