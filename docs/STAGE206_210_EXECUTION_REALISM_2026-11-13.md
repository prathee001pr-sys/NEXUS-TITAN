# NEXUS TITAN Stages 206–210 — Offline Execution Realism (Synthetic Only)

Checkpoint: stacked on Stage 201–205 GitHub feature commit `d4d528942b48816780c0d396b31e06970e639066`.

## Deliverables

- **Stage 206** — bounded ten-level bid/ask snapshots, exact Decimal/tick, depth ordering, future/stale quote veto and canonical digest.
- **Stage 207** — deterministic participation-bounded depth walk; full vs partial fill, VWAP and adverse slippage; no broker or execution interface.
- **Stage 208** — explicit **hypothetical** F&O fee components (brokerage, STT, exchange, SEBI, GST, stamp, extra friction), direction rules, precise Decimal accounting; all rates are supplied assumptions, not authenticated Indian tax/broker/exchange rates.
- **Stage 209** — bounded capacity, depth, assumed latency, fill completeness, maximum expense stress scenarios; scenario list and baseline receipts are linked.
- **Stage 210** — independent re-execution of Stage 206–209 from original synthetic inputs, Stage 205 internal-only structural receipt, all capacity cases passing and baseline case included. This gate cannot authorize live, autonomous, or promoted trading.

## Verification evidence

- New strictly-offline Stage 206–210 unit/attack-boundary tests: **95 passed, 0 failed**.
- Combined Stage 154–210 and selected Stage 26/44/112/141 historical-data/interoperability tests: **665 passed, 0 failed** with `-W error` in local reconstructed repository.
- **Reconstructed local repository full regression:** `4316 passed, 5 subtests passed` in 138 seconds. Full test run used `PYTHONWARNINGS=ignore::DeprecationWarning` to suppress deprecation warnings. This is **local evidence**, not proof of this branch on GitHub CI.
- None of the tests authenticates actual exchange data, a broker fee tariff or genuine fills. GitHub CI for Stage 206–210 requires a pushed feature-branch commit.

## Safety and limitations

1. `accepted` is strictly *eligible for internal manual synthetic execution review*. No broker integration, market orders, credential use, live trading, autonomous execution or promotion exists in these modules.
2. Displayed synthetic order-book size does not prove real order-book capacity, queue priority, fill likelihood, impact, latency or exchange origin.
3. STT/stamp/exchange/SEBI/GST brokerage rates can change; any scenario rates, contract multipliers or fee calculations must not be treated as verified legal or broker tariff rules.
4. Actual historical market data, licensing, exchange provenance, timestamp quality, real settlement, exchange fees and real fills are all **unverified**. Stage 205 and later acceptance flags are not cryptographic third-party evidence.
5. The staged 206–210 branch must remain a Draft PR until tests/CI/security review. Do not merge into main or change repository visibility without separate approval.

## How to review

Inspect the `tests/test_stage206_210_batch.py`, the Stage 210 recomputation logic and GitHub Actions matrix. Use data-provenance checks and official fee schedules before making *any* real-market claims. The Stage 221 Rust optimization roadmap is unchanged: only optimize measured Python bottlenecks.
