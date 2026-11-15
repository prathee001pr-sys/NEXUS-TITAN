# Option-chain history continuity (research-only) — 2026-11-02

## Purpose

This is an *additive* historical-series validator layered over PR #7's strict
per-snapshot SHA-256 CSV importer and point-in-time option-chain checker. The
objective is to reject missing/duplicated/unsorted snapshot timestamps before
offline research. It is not an exchange feed, options backtester, or trading
engine and has **no** order placement capability.

## APIs

`nexus_titan.data.option_chain_history.inspect_option_chain_history` returns
an immutable `OptionChainHistoryReport` (including missing count, a bounded
sample of missing UTC timestamps, and per-snapshot issues).

`assemble_research_option_chain_history` raises
`OptionChainHistoryError` and releases **no partial history** if any check fails.
Success returns `ResearchOptionChainHistory` with
`approved_for_strategy_promotion=False`.

```python
from nexus_titan.data.option_chain_history import (
    assemble_research_option_chain_history,
)
from nexus_titan.data.sessions import nse_equity_derivatives_baseline

# A and B must already have passed load_research_option_chain_csv(),
# including independently recorded SHA-256, structural option-chain checks
# and the same explicit, reviewed contract/provider evidence references.
calendar = nse_equity_derivatives_baseline(holidays=reviewed_exchange_holidays)
history = assemble_research_option_chain_history(
    [A, B],
    contract=point_in_time_option_contract,
    calendar=calendar,
    interval_minutes=1,
)
assert history.approved_for_strategy_promotion is False
```

## Checks

1. Each snapshot is rechecked against `inspect_verified_option_chain()` and
   the supplied exchange session calendar. Metadata must be NSE, explicitly
   source-declared and valid for each timestamp and expiry.
2. Observation times are timezone-aware, strictly increasing, unique,
   and aligned to an **exchange-session-open anchored** minute grid.
3. Every snapshot carries unique, syntactically valid SHA-256 source digest
   and consistent provider, licence, calendar and contract references.
   Digests/declared references alone do *not* authenticate the sources.
4. Replay of the same digest, missing/blank evidence references, and
   claimed promotion authorization fail closed.
5. Strike-side universe retention versus prior snapshot must exceed the
   configured threshold (default 80%); this is a research continuity
   heuristic, not an exchange listing rule.
6. Expected intervals are enumerated within configured session segments.
   Weekends, explicitly declared exchange holidays, and configured
   trading-session breaks are excluded.
7. Only the span **between the first and last provided timestamps** is
   evaluated. Full start/end-of-day completeness is **not proven**.
8. Bounded processing defaults: at most 2,000 snapshots, 20,000 expected
   intervals, 366 calendar days and 20 stored missing timestamp examples.
   Larger datasets require verified batches; no silent truncation can pass.
9. Current implementation handles one contract + expiry + evidence lineage
   per history batch. Contract rolls/expiry transitions require separate
   batches with independently verified contract metadata.

## Limitations / release gates

- The source timestamps and SHA-256 fields are caller-supplied; this module
  does not reread vendor bytes or cryptographically authenticate their origin.
- The NSE calendar constructor is a **configurable baseline**, not an
  authoritative holiday/special-session feed. Operators must supply
  independently verified calendar evidence before using outputs in research.
- The CSV importer validates individual snapshots, but **this history module
  consumes imported snapshots**; it does not accept arbitrary raw vendor CSV
  paths, ingest streaming data or reconcile exchange packets.
- Missing-volume, liquidity, stale quote fill model, official margin,
  execution fees, corporate actions and provenance licensing need external
  evidence and additional integration.
- The PR is stacked on draft PR #7, which itself depends on draft Stage 1–15
  PR #6. No changes to `main`, risk/veto, live trading, or promotion gates.
