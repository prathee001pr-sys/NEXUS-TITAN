# NEXUS TITAN — Stage63 Offline Operator Audit & Evidence Dashboard

**Date:** 2026-11-03  
**Base:** Stage62 draft PR #54  
**Branch:** `feature/stage63-offline-operator-status-view-2026-11-03`  
**Mode:** local, static, non-interactive-with-trading, no network or broker API.

## Purpose

Stage63 provides a separate **read-only operator-facing visual view**
of Stage62's GitHub PR/source/CI audit and Stage61's **synthetic**
NIFTY/BANKNIFTY research evidence.

The original approved Stage51 TITAN dashboard and its locked
black-and-silver design are not modified. Stage63 **reuses the
existing `stage51.css` theme and its key layout classes** and adds
only local, responsive `stage63.css`. It reserves the exact same
digital-human TITAN face placement with **ASSET NOT CONNECTED**:
the original user-approved artwork must be supplied and verified
before the exact image can be used. No substitute digital face is
invented or downloaded.

Stage63 is **NOT live system monitoring**: it receives no updates
unless a user loads new local JSON files. It does NOT start a
background process, subscribe to GitHub/market channels, refresh
an account or query a broker. It reports **NO-GO** even when a local
source file says its internal structural checks passed.

## Assets

- `src/nexus_titan/dashboard/static/stage63.html`
- `src/nexus_titan/dashboard/static/stage63.css`
- `src/nexus_titan/dashboard/static/stage63.js`

Open `stage63.html` locally from the same directory as
`stage51.css`, `stage63.css`, and `stage63.js`. A local HTTP
server is not needed for code unit tests or the JSON generation;
some mobile browsers may restrict `file://` asset loading and
may require a user-controlled local static preview. **Never
deploy this page to a public web origin with sensitive local audit
files or secrets.**

### Supported JSON file 1 — Stage62 audit

The existing Stage62 CLI emits a JSON document with
`mode=STAGE62_FROZEN_SNAPSHOT_NO_MERGE_LOCAL_AST_ONLY`.
Generate a fresh **local** export on an appropriate checked-out
Stage63 branch:

```bash
python scripts/run_stage62_integration_audit.py > stage62_audit.json
```

In the page's first file selector, choose `stage62_audit.json`.
The view shows frozen PR count and roots, claimed main branch
protection, file-diff coverage, selected source/CI/import checks
and some mandatory integration blockers. All source, PR and
GitHub claims remain **untrusted user-selected JSON**. A
SHA256 is local data integrity metadata only, not source
authentication.

The Stage62 dataset initially recorded **52 open PRs** at its
2026-11-03 snapshot moment, prior to PR #54, with **two separate
main-rooted PRs** (#1 and #3) and main reported unprotected
by GitHub branch metadata. Its changed-file inventory is
incomplete; conflicts are still UNKNOWN. No manual merge
was done, and no fully merged-tree CI evidence exists.

### Supported JSON file 2 — Stage61 synthetic evidence

The existing Stage61 smoke program emits a JSON document with
`mode=STAGE61_SYNTHETIC_EVIDENCE_NO_GO_SCORECARD_ONLY`.

```bash
python scripts/run_stage61_fo_evidence_smoke.py > stage61_research.json
```

In the second file selector, choose `stage61_research.json`.
The page shows fabricated NIFTY and BANKNIFTY futures candle
counts, OOS fold and prediction counts, and missing-evidence
blockers. There are **NO genuine exchange-data backtests,
profit factor, live fills, broker-verified charges or strategy
promotion authorizations**. Stage58 simulated costs and Stage60
future-direction signals are distinct, deliberately unlinked
research outputs.

Stage63 **does not** visualize live NIFTY/BANKNIFTY charts,
real-time option chains, crypto prices or executable capital.

## Browser security controls

`stage63.js`:
- Only reads two explicitly selected local UTF-8 JSON files,
  with **256 KiB** per-file size limit checked before and after
  reading; no fetch, WebSocket, XHR, telemetry or browser storage.
- Requires the exact report markers and bounded object schemas.
  Stage62 Git SHA is checked as **40 hex characters** and
  Stage62 local SHA256 fingerprints as **64 hex characters**.
- Rejects inputs claiming authenticated real-market/vendor,
  trading, strategy promotion, security, global risk, protected
  merge or production authority. Missing mandatory Stage61
  release blockers and contradictory local scorecard counts
  are rejected rather than displayed as safe.
- Inserts untrusted labels and warnings only with
  `textContent`, using `document.createElement("li")`.
  Never treats JSON fields as HTML markup or URL destinations.
- Uses per-file asynchronous selection generations: clearing
  a report or choosing a newer one prevents an older
  `File.text()` result from reappearing.
- Has **no** order, approval, fill, cancellation or square-off
  action controls. The CSP is local-only:
  `default-src 'none'; script-src 'self'; style-src 'self';
  img-src 'self'; connect-src 'none'; object-src 'none';
  frame-src 'none'; form-action 'none'; base-uri 'none'`.

Neither CSP nor local JSON parsing proves the underlying
data's authenticity; malicious local code/files, browser
extensions and a compromised runtime are outside this viewer.

### Verification

```bash
python -m pytest -q tests/test_stage63_operator_dashboard.py
python scripts/run_project_validation.py
```

`tests/helpers/stage63_browser_harness.cjs` is a dependency-free
Node browser-like DOM harness run automatically by pytest when
Node is installed. It loads the **actual Stage61/62 Python
scripts' local JSON output**, exercises XSS-text rendering,
spoofed production/merge/live claims, badly formed counters,
oversized files, Clear and async stale response safety.

GitHub Actions currently runs full pytest on Python 3.11,
3.12, 3.13 plus Stage25 and Stage62 synthetic/offline
validations. No synthetic or source-level test is a verified
live strategy. Only mark Stage63 **offline tested** when
the **final exact PR head** has three green matrix jobs.

## Explicit blockers and next work

1. Stage62: two main-rooted PR stacks and incomplete diff
   coverage remain; needs current owner-controlled branch
   review and full candidate merged-tree CI.
2. Stage61: no independently authenticated real, licensed
   NSE F&O futures/options depth/data or genuine broker charges,
   lot/contract history and profitable shadow trial proof.
3. Stage43–57: legacy order/fill APIs and separate capital
   state remain outside an unbypassable risk/settlement service.
4. No independently authenticated human approval/MFA, secure
   isolated broker credential custody, independent global
   risk veto or production signing.
5. Original user-approved TITAN face asset not in this
   repository. No replacement inferred from descriptions.

**Recommended Stage64:** paper/shadow evidence governance
and no-live experimental trial controls with explicit observed
source quality and owner approvals; no pretend synthetic profits.
**Stage65:** comprehensive owner-directed release readiness
review (default NO-GO until all external dependencies pass).

Keep Stage63 PR **DRAFT and UNMERGED**; `main` unchanged,
real-money orders disabled, autonomous strategy promotion blocked.
