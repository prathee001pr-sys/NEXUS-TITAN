# Stage 99 – Synthetic F&O Expiry/Margin Review (OFFLINE CANDIDATE)

**Status: LOCAL-CANDIDATE only, not GitHub committed, not integrated or CI verified.**

Base of latest GitHub development: Stage98 `8b132a69e431759709c384c1eb4eb61c4e089bc1`, Draft PR #90. The Replit Agent limit is exhausted. This ZIP does **not** modify that repository.

Files add a read-only operations preflight which reuses existing `settle_option_at_expiry` and `estimate_span_elm_margin`. It handles SYNTHETIC NIFTY/BANKNIFTY CE/PE and futures cases, contract-lot divisibility, IST expiry date/timestamp, synthetic source gate, OTM/ITM settlement, estimated exercise STT and indicative capital/margin. It rejects any claim of official price data, live flags, crypto/USDT or non-index contracts. Futures **net** P&L stays unavailable without actual fees, though indicative gross is shown.

**Permanent NO-GO:** no authentic NSE contract-master validation, no effective-dated lot-size/expiry-authority proof, no official SPAN/ELM/peak/penalty margin, no broker contract notes, no fully verified exercise/physical settlement handling, no order placement, no real-time exchange feed, no authenticated identity or external independent audit. All flags that would assert those capabilities stay `False`. Any prices and costs in tests are illustrations.

Historical settlement helper is floating point and its charges are indicative. Do not use as a legal, tax, fee or broker-reconciliation statement. Unit tests do not substitute actual market evidence.

Use only after verifying a local checkout at the **exact Stage98 commit**; copy the two additive files without overwriting existing project files and run focused + full regression and independent security checks. Then use authenticated Git CLI with noreply author and committer to create a new Stage99 feature branch and Draft PR; do not merge main, change privacy, or enable live trading. Do not use GitHub API publisher for privacy-sensitive commits.

## Optional Replit Shell workflow without Replit Agent

The included `prepare_stage99_no_agent.sh` performs exact SHA, Git-root, origin and
branch/path preflight before creating a **new** Stage99 worktree. It adds only the
candidate module, tests and this documentation. It then runs 5-minute bounded
focused + full regression and leaves all GitHub publication actions to a separate
review. It never commits, pushes, merges or changes repository visibility. On
any failure it stops; do **not** delete worktrees or bypass a safety preflight.

After manually uploading this ZIP to `~/workspace`, extract it to a new empty
package folder using Python zipfile, and from that folder run
`bash prepare_stage99_no_agent.sh`. If the existing exact Stage98 SHA isn't
available locally, stop; do not substitute main or an older checkout.

The previous offline candidate had 44 focused tests. The revised candidate
adds negative boundary tests and offline source safety checks. The test count
in this package is determined by its current validation report, not a claim of
full Stage98 integrated success.


## V3 hardening — 2026-11-10

- Additive, read-only `review_synthetic_batch()` for 1–50 explicit fixture cases. Duplicate contract identifiers are fail-closed; the output is immutable and intentionally **does not** sum realized P&L or imply an executable portfolio.
- A synthetic notional > INR 1,000,000,000 per case, including strike notional, is rejected to reduce uncontrolled floating-point error and excessive unrealistic test exposure. This is a **test size guard**, not a broker margin rule, trading limit, or market fact.
- The three inherited dependencies of this review were independently identified by full Git blob SHA against the exact GitHub Stage98 commit:
  - `src/nexus_titan/derivatives/chain_and_settlement.py`: `6c13eacf480305faed7576cefeb8c9bfc7dfc90a`
  - `src/nexus_titan/cost/charges.py`: `beb355f6786fc278796a15aff943230a75ba9d6c`
  - `src/nexus_titan/derivatives/options_engine.py`: `635da0d5942a9ffdfbf407e1c02d07daa1728d75`
- This exact dependency-hash match does **not** imply the whole Stage98 tree is checked out. Repo-level regression still requires the full exact head `8b132a69e431759709c384c1eb4eb61c4e089bc1`.
- All data is synthetic and merely provides an engineering safety preflight. Source timestamps are fixture declarations, **not** validated NSE settlement calendars or official contract masters.

- Final V3 local check: 100 focused tests passed on Python 3.13.5 with warnings treated as errors. Historical surrogate full suite: 2,511 tests + 5 subtests passed, 2 inherited warnings. Not the exact Stage98 checkout.
