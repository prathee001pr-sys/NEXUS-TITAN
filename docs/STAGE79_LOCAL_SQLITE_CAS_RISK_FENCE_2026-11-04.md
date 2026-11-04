# Stage79 — Same-SQLite Optimistic Snapshot Fence (NO-GO)

2026-11-04. Stacked on audit-only PR #71 (Stage78 + full-chain synthetic F&O test), not merged to main.

## Integration improvement

Stage55's existing SQLite \`BEGIN IMMEDIATE\` transaction previously validated its own atomic cash/reservation journal, but accepted a Stage77 risk-screened order even when another direct writer changed the book after Stage77 inspected it and before its write. Stage79 adds an **optional**, bounded pair \`expected_revision\` and \`expected_journal_tip\` to the Stage55 reserve/fill/cancel public methods. When supplied, the two values are compared to the current replay-verified head **inside the same SQLite write transaction**; mismatch causes rejection before any event is recorded. Calls with only one field, a boolean revision, a negative revision or a malformed digest fail closed.

Stage77 now *always* supplies that exact pair for cooperative local reserve/fill/cancel and tracks the most recent Stage55 receipt. If another writer changes the journal between cooperative calls, Stage77 stops with manual-recovery-required rather than silently adopting a new ledger state. Exact-head changes between inspection and commit are also rejected by Stage55 itself. Stage77 synthetic cancellation remains available with a stale *risk pulse* (to release own local holds), but cannot bypass a changed journal head or damaged ledger.

## Tested behaviors
- Matching revision/hash open → partial fill → cancel succeeds and replay validates.
- Invalid, incomplete or stale snapshot is denied before write.
- A second Stage55 handle writing to the same SQLite file between inspection and operation causes CAS failure; account balances and event head stay consistent.
- Deterministically injected direct-write races immediately before Stage77 reserve, fill or cancel are rejected.
- A legacy direct Stage55 write that doesn't opt into CAS still succeeds, and the active Stage77 sandbox detects that drift at next request.
- Full existing Stage59/44 → Stage71–77 fabricated F&O end-to-end research chain remains required to pass; no raw market feed, broker or option P&L claims.
- Python 3.11/3.12/3.13 automated pytest and conservative no-input smoke.

## Absolutely NOT solved

This is an **optimistic single-database consistency check**, not a global Risk & Veto. Legacy direct Stage55 methods retain optional (bypassable) CAS; existing VirtualAccount, PaperIntentGateway, crypto and Stage53 research books are separate. An untrusted caller can still bypass Stage77, open another SQLite database, change a risk policy during the check, forge a market quote, or rewrite an entire SQLite hash chain. Stage76 telemetry and Stage75 evidence remain operator declarations. Risk-screening itself is NOT authenticated nor stored atomically in the Stage55 transaction. Stage77's active request map remains in RAM, so a nonempty restart still requires supervised manual recovery.

\`main\` is unprotected and the large draft PR stack has not been owner-reviewed or consolidated. Do not merge in bulk. No real trading, broker orders, model promotion, live market fills, genuine NSE F&O backtests, forward paper trial or deployable unified capital authority.

**Stage79 verdict: STAGE79_LOCAL_OPTIMISTIC_SQLITE_CAS_RESEARCH_NO_GO**.

## Priority next

Prepare owner-reviewed merged candidate from the two root PR lineages; add protected \`main\` rules; inventory and close **every** legacy entrypoint in a separate explicit cutover. Consolidate risk, kill-state, current positions and capital holds into a single authenticated transaction authority, with reentrant/multi-process race, crash and recovery tests. Separately verify licensed NSE data and paper shadow evidence. No live trade authorization here.
