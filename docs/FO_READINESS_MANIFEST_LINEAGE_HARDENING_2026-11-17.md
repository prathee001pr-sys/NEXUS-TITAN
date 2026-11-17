# Indian F&O dataset intake lineage hardening — 2026-11-17

**Scope:** Existing Stage205 manual internal structural QA only, no market feeds, no broker integrations and NO live trading. This is an incremental validation improvement, not a new data source.

## Motivation
Stage205 accepted independently-typed Stage201/203/204 receipt objects. The original window-check built dictionaries keyed by dataset ID and therefore silently collapsed duplicate keys if a caller constructed forged dataclass receipts. Dataclass constructors can also set `independent_vendor_authenticated`-like fields or booleans for counts even when no independent evidence exists.

## Change
1. Require unique, bounded, correctly shaped dataset IDs for the catalog, source byte manifest and temporal holdout receipts.
2. Require an exact one-to-one dataset/window key mapping. Unknown IDs and duplicate windows are rejected **before** the downstream datetime dictionary comparison.
3. Reject boolean count masquerading as integer for snapshot/file/holdout counts.
4. Explicitly reject caller-supplied external certification claims in Stage201–204 receipts. Vendor licensing, exchange calendars, official circulars and upstream no-leak evidence are NOT established by a local dataclass field.
5. Preserve existing successful internal manual-review structural receipt and linked evidence SHA behavior. Do not make `real_historical_data_verified`, `real_market_backtest_verified`, `live_trading_authorized`, `autonomous_execution_authorized` or `strategy_promotion_authorized` true.

## Non-goals
No authentic NSE data was received, no fee/margin schedule or market-depth reconciliation has been run, no paper/live orders are transmitted, no model promoted. The structural gate is not an authenticity service and remains fail-closed for production.

## Acceptance
- Existing Stage201–205 63+ tests plus new duplicate-key/self-attested provenance/boolean count negative tests pass under `-W error`.
- Full Indian F&O regression, real-crash tests, Stage147/148 Crypto negative tests and full suite remain green.
- Commit only the Stage205 source file, its existing Stage201–205 test file and this NO-GO document; publish with Git CLI noreply email to a Draft branch rooted at Stage148 commit `c74ff2ecada2788b8a23daec054f620f9c990878`.
- Verify exact-head GitHub 3-version CI and Secret Scan separately; keep Issue #137 OPEN, `main` untouched and live trading off.
