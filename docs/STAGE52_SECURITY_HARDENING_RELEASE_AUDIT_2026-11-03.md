# NEXUS TITAN — Stage52 Security Hardening & Fail-Closed Integration Audit

**Date:** 2026-11-03  
**Source branch:** `feature/stage52-security-release-readiness-audit-2026-11-03`  
**Base:** Stage51 draft PR #43  
**Milestone:** Offline, read-only developer security review + stricter local visual snapshot handling  
**Release result:** **BLOCKED**, regardless of static test result.

## Why Stage52 exists

The working Stage43–51 code adds local paper-safety protections, signed
HMAC manual approval, a cooperative one-shot SQLite admission fence and a
responsive read-only dashboard. However, none is an independently enforced
operating-system or broker policy boundary. Existing Python order/fill paths
remain callable outside the optional Stage47–49 facades. Stage48 verifies
HMAC key possession, NOT independently authenticated human identity.
Stage49's coordinator does not atomically settle the separate virtual
and research capital books. Stage51's JSON is a caller-selected, untrusted
local file, not signed market/account evidence.

The appropriate next increment is to **make these caveats executable and
reviewable** instead of silently assuming local regression success makes
a trade system safe or complete.

## New/updated implementation

### 1) Structural source/security inventory

`src/nexus_titan/operations/release_security_audit.py` exposes:

- `inspect_stage52_security_sources(repo_root: Path)` — read-only
  deterministic source tree inspection, no external network or credentials.
- `Stage52SecurityReview` — versioned JSON-friendly report carrying
  a bounded content digest, explicit checks/findings, observed legacy
  method surfaces and **12 non-negotiable unresolved release blockers**.
- Critical Stage43/45/47/48/49/50 and `VirtualAccount` Python modules
  are checked for expected class/method signatures and parseable AST.
- Stage51 HTML CSP, approved-face placeholder, offline JS constraints,
  green-status/cash spoof protections, stale-import guard and exact locked
  CSS root-theme variable values are checked for basic presence.
- Source files >512KB, unexpected missing files and symlinked parent/file
  paths are refused; no project code gets executed by the inventory scanner.
- A deterministic SHA256 over the selected local files supports **local
  comparison only**. It is NOT a developer signature, official GitHub
  commit attestation, authenticated account report, build reproducibility
  proof or independent security audit.

`scripts/run_stage52_security_audit.py` prints the review JSON. Exit 0
means the *selected local structural checks passed*, **not** that TITAN is
production-ready. Exit 2 means even local structural checks failed.
The report keeps live, broker, production and autonomous-strategy flags
false for **both** outcomes. This CLI does not write files or edit paper
accounts.

### 2) Stage51 visual JSON spoofing protections

`src/nexus_titan/dashboard/static/stage51.js` now refuses internally
inconsistent *presentation* records:

- False balance-match flags versus exact separate cents, or a declared
  match when the two cash books have diverged.
- Unknown coordinator states, `attempt_count=0` with non-null state,
  missing marker after an attempt or first-entry-ready flag after any
  attempt.
- Negative, fractional, nonfinite or impossible paper order/position
  counts; pending+accepted exceeding recorded orders.
- A local `LOCAL_SYNTHETIC_REVIEW_ONLY` status if the JSON simultaneously
  declares a blocker, prior coordinator attempt, disabled paper session,
  active kill switch, invalid cash alignment, missing strict risk
  config or no local signer callback.
- `LOCAL_REVIEW_REQUIRED` without an explanatory blocker.
- **Stale asynchronous File.text() completion** after the user has
  cleared the screen or selected a newer file: the old import can no
  longer redraw the dashboard unexpectedly.

All of these are *client-side consistency checks on untrusted local
bytes*. Someone with access to rewrite the JSON can still construct
an internally consistent false snapshot. Do not call the file
cryptographically authenticated or use it to authorize a trade.

### 3) Regression testing

- `tests/test_stage52_release_security_audit.py` checks the real
  Stage51 candidate tree and malicious copies of its subset:
  missing critical source, unparseable Python, renamed signed-approval
  or legacy methods, symlink, oversized file, removed HTML CSP,
  dangerous browser APIs, removed dashboard cash guard, tampered locked
  CSS variable, invalid CLI root and immutable release flags.
- The existing `tests/helpers/stage51_browser_harness.cjs` gained
  hostile local JSON, fake green status, noninteger order counts,
  cash mismatch and crash-marker mutation scenarios.
- The same Node harness tests asynchronous file selection/clear races
  and ensures the previously selected file cannot reappear.
- All previous Stage1–51 tests remain part of the GitHub Python
  3.11/3.12/3.13 offline matrix; Stage25 synthetic integration smoke
  stays in CI.

## How to run

```bash
python scripts/run_stage52_security_audit.py
python -m pytest -q tests/test_stage52_release_security_audit.py tests/test_stage51_visual_dashboard.py
python -m pytest -q
```

The output always contains `"production_release_allowed": false`.
It must NOT be promoted to a green release widget merely because the
CLI exits with code 0 or Python tests pass.

## Architecture / branch audit conclusions

The core remains a trading-only research/paper project. Stage46 identified
two independent main-rooted draft PR stacks (#1 and #3) and overlapping
calibration files (PRs #3/#5 vs #6). These require an explicit manual
semantic review and prospective combined-tree validation. In the Stage51
checkpoint, PR #38–#43 were still **draft and unmerged**; do not claim
an integrated `main` release merely because a stacked head is CI green.

GitHub returned `main.protected=false` in the Stage51 review; repository
rulesets may need independent confirmation by an authorized owner. Stage52
source inspection cannot check repository branch protections, pull-request
approvals, signed commits, or provenance of uploaded market data.

### Required secure-architecture work — not implemented here

1. **Global order admission:** isolate order/fill credentials and
   reject all legacy API bypasses at a trusted process/service boundary.
   Unit tests alone cannot prove this.
2. **Independent risk veto:** broker- or gateway-bound enforcement that
   cannot be bypassed by changing in-process Python callbacks.
3. **Verified user identity and signer custody:** separate IDP,
   hardware/isolated signing secret, revocation and approval/fill-time
   checks; HMAC demo credentials are not user verification.
4. **Atomic capital authority:** one rigorously reconciled durable ledger,
   or enforced isolated budgets and reservation/settlement rules,
   including crashes, fees and partial fills. Stage49 isn't this ledger.
5. **Actual authenticated sources:** licensed point-in-time NSE F&O,
   contract metadata, order depth, calendar, fees, slippage and
   extended out-of-sample/shadow validation, deferred at user request.
6. **Official dashboard artwork:** connect exact user-approved TITAN
   face and layout. No replacement is authorized.
7. **GitHub governance:** reconcile independent PR lineages; ensure
   reviewed commits, branch protections, least-privilege checks, and
   final prospective merged-tree CI before any merge.
8. **Owner-governed strategy promotion:** release gates, independent audit
   and explicit approvals. No live trading is approved.

This stage intentionally DOES NOT resolve those requirements or change
the two account databases, authenticate anyone, transmit a broker order,
or promote AI-generated strategies.

## Final evidence requirements

Record the **final PR-head** workflow run, test total, Python
3.11/3.12/3.13 conclusions and all known caveats in the Stage52
draft PR. Any later code/doc change requires the same final-head
verification again. Leave branch and PR **draft/unmerged** for owner
review; do not enable live trading.
