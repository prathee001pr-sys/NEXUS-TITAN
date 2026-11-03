# NEXUS TITAN — Stage 46 PR Stack Integration Audit

**Evidence snapshot:** 2026-11-03 04:46:08 UTC (10:16:08 Asia/Kolkata)  
**Repository:** `prathee001pr-sys/NEXUS-TITAN` (private)  
**Starting point:** Stage45 PR #37, HEAD `62a83cc0d4ff64366f1f83f10be74c6e3297476c`  
**Status:** OFFLINE GRAPH AUDIT / NO MERGE / NO LIVE TRADING.

## Source-backed findings

- At capture, GitHub REST returned **36 open draft pull requests** on the first
  complete `per_page=100` result; all were marked draft and unmerged.
- The **main** head was `40e93cfb77fa0650e4f57428c6d77f70bb78d564`.
  Its GitHub branch response had `protected=false`. This is a reported
  configuration flag, **not** a guarantee that all organization-level
  branch/ruleset enforcement has been independently investigated. An owner
  must review/enforce appropriate rules BEFORE considering integration.
- There are exactly **two main-rooted stacks**: #1 (`integration/phase6-zip-baseline`)
  and #3 (`feature/oos-probability-calibration`). The Stage 45 lineage runs
  through #1 -> #6 -> #7 ... -> #37. A register side-branch #4 also originates
  from #1; calibration hardening #5 originates from #3.
- Every recorded base SHA matched its parent branch HEAD (or the observed
  main SHA for roots) at capture; no missing parent refs or graph cycles.
  **This does not imply merge conflicts are absent** or that the current
  GitHub state remains unchanged in the future.
- Selected compare results expose an explicit independent-lineage edit
  overlap between calibration root #3 and canonical integration #6, with
  further overlap between calibration hardening #5 and #6:
  `src/nexus_titan/intelligence/__init__.py`,
  `src/nexus_titan/intelligence/calibration.py`,
  `tests/test_probability_calibration.py`.
  These files need human semantic reconciliation; overlap is not proof of a
  Git three-way merge conflict. Snapshot contains full changed paths for
  #3/#5/#6 **only**; other PR file-list coverage remains incomplete.

## Implementation delivered

- `src/nexus_titan/operations/pr_stack_audit.py`: local deterministic PR
  graph validator. Enforces unique PR IDs/heads, bounded file paths,
  explicit state flags, SHA matches, topological dependency order, cycle
  detection, missing-parent rejection, independent-lineage file overlaps,
  and reports review blockers. **Always** leaves merge readiness and
  production readiness false, because offline snapshots cannot prove either.
- `docs/STAGE46_PR_STACK_SNAPSHOT_2026-11-03.json`: minimized GitHub metadata
  and selected complete diff-path evidence captured at one instant. It
  includes no tokens, credentials, customer market data or private market
  history. Read-only fixture, not a machine authorization for merging.
- `scripts/run_stage46_pr_stack_audit.py`: strict bounded JSON parser,
  default snapshot audit, no GitHub network calls and no writes. An exit
  code of 0 means **snapshot structurally analyzed**, not safe-to-merge.
- `tests/test_stage46_pr_stack_audit.py`: synthetic graph regressions,
  stale parent SHA, cycle, duplicate branches/IDs, bad paths, incomplete
  evidence, malicious JSON keys/symlinks and a frozen-source CLI test.

Run offline from repository root:

```bash
python scripts/run_stage46_pr_stack_audit.py
python -m pytest -q tests/test_stage46_pr_stack_audit.py
python -m pytest -q
```

## Merge/integration plan — REVIEW ONLY, no automatic merge

1. **Lock down and independently inspect branch policy.** Owner should
   consider branch protection / repository rulesets with required reviews
   and CI for `main`; current `protected=false` needs resolution.
   Confirm the latest full PR list/head SHAs before every decision.
2. **Choose canonical lineage.** PR #1 has the Phase6 baseline; PR #6 carries
   the Stage1–15 canonical integration snapshot. Review the original and
   preservation of calibration fixes before resolving #3/#5 against #6.
   PR #4 register has a separate ancestor path and should be reconciled
   independently, not blindly mixed with core code.
3. **Inspect independent calibration branches (#3/#5) versus #6** for the
   three overlapping code/test paths. Include semantic/deterministic
   probability-calibration regression tests. GitHub's changed-file overlap
   is only an early-warning indicator, not a substitute for a 3-way merge.
4. **Review stacked dependencies topologically** (under the canonical
   chosen branch graph) and require the actual prospective merged tree
   to pass Python 3.11/3.12/3.13 tests plus Stage25 synthetic smoke.
   Check schema migrations/old SQLite states and tests on isolated copies.
5. **Only explicit owner-reviewed merges.** Do not force-push, mass-merge,
   rewrite `main`, edit risk policy, move broker credentials or enable
   live trading as part of integration. Independent production authorization
   remains out of scope.

## Residual blockers after Stage46

- Main branch reported unprotected; complete independent repository policy
  / organization ruleset review has not been performed.
- Combined post-merge CI and semantic cross-branch resolutions are unverified.
- No globally mandatory unbypassable Risk & Veto service, independently
  authenticated approval, or cross-ledger atomic cash/positions authority.
- No genuine licensed point-in-time NIFTY/BANKNIFTY F&O history, realistic
  real-market fills, extended shadow-validation record, or connected final
  approved dashboard.
- All PRs remain drafts and unmerged until owner action. Stage46 code is
  **audit groundwork**, not completion of NEXUS TITAN, Stage47, live
  operation, or strategy promotion.

**Next after Stage46 CI:** design **Stage47 independent policy/veto boundary**
in isolated paper-only mode, with explicit fail-closed behavior and no
broker credentials. Preserve existing permissions, source and protected
risk settings; do not broaden product scope or touch real datasets.
