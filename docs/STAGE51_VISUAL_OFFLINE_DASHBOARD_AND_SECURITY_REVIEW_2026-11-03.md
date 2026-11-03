# NEXUS TITAN — Stage 51 Offline Visual Dashboard & Security Audit

**Date:** 2026-11-03  
**Parent branch:** `feature/stage50-readonly-paper-dashboard-2026-11-03`  
**PR mode:** stacked draft; do NOT merge `main`  
**Milestone classification:** real static frontend + Stage50 read-only local export; no online service, verified user identity, live market connection, or broker rights.

## Goal / scope

Stage50 added an optional, versioned read-only backend safety snapshot. Stage51
adds **actual responsive HTML, CSS and JavaScript frontend files**, plus an
offline synthetic snapshot-export path that a user can open locally. It is
minimal: **no frontend framework, API server, external dependencies, cloud
dashboard or remote data collection**.

The approved design direction is retained: black/silver panels, subtle
cyan accents, green/red trading cues, clean metric grid, compact mobile
layout and a reserved cybernetic-face placement.

**The exact previously approved TITAN digital face image is NOT in this
repository snapshot.** Stage51 therefore leaves the face frame explicitly
labeled `APPROVED TITAN FACE ASSET NOT CONNECTED`; it does **not** replace
the official face or create a different identity. Exact face and layout
pixel parity require the original approved image/source.

## Components

- `src/nexus_titan/dashboard/static/stage51.html`: actual read-only TITAN
  visual layout with Overview, distinct cash books, paper order counts,
  local Risk & Veto configuration, manual approval warnings, Stage49
  coordinator state, no-feed chart placeholder and blocker register.
- `src/nexus_titan/dashboard/static/stage51.css`: responsive black/silver
  desktop and mobile styling with Stage50's locked primary color tokens,
  text contrast and tabular numeric alignment.
- `src/nexus_titan/dashboard/static/stage51.js`: local user-selected
  Stage50 JSON file renderer. Rejects wrong schema/data source/visual theme,
  unsupported live/broker/identity/production claims, fabricated combined
  cash and any real quote in this version. The UI NEVER raises trade
  permission or invents account valuation. Limited to 256 KiB per JSON.
  Values are rendered via `textContent`, not HTML injection or dynamic
  CSS/URLs, and some output lengths are bounded.
- `scripts/run_stage51_visual_dashboard_demo.py`: produces a temporary,
  **synthetic new paper account** (not the user's account), reads its
  Stage50 snapshot and writes a distinct demo JSON file with no overwrite,
  using owner-only POSIX file permissions. Never mints an order, approval
  token, fill, remote request or production credential.
- `tests/test_stage51_visual_dashboard.py`: visual/CSP/theme and safe
  offline exporter tests plus Node harness invocation when Node exists.
- `tests/helpers/stage51_browser_harness.cjs`: tests actual JS with
  in-memory browser-like DOM. Exercises valid file load, reset, oversized
  data rejection, malicious HTML string rendering as literal text, fake
  live/broker/identity claims, fake combined capital and schema/source
  spoofing.

## How to open the real Stage51 frontend

From this development branch (Replit or PC), run:

```bash
python scripts/run_stage51_visual_dashboard_demo.py
```

It creates **one new file** at `reports/stage51_paper_snapshot.json`
unless that file already exists. Existing files are **NEVER** overwritten.
To refresh a demo, supply a separate new path using `--output`.

Keep these files in the same folder:

- `stage51.html`
- `stage51.css`
- `stage51.js`

Open `src/nexus_titan/dashboard/static/stage51.html` locally in a
supported browser, choose the generated JSON through **Choose JSON file**.
If a mobile browser prevents local sibling JavaScript/CSS files for
`file://` pages, open the files from a development **localhost-only**
static server, or copy the three files intact to a browser-accessible
directory. **Do not expose a static server over the public internet or
Replit's public preview** without separate authentication and privacy
review. This milestone does NOT deploy a server.

The example shows a *demo account with paper_orders_enabled=False*.
If no JSON has been imported, the screen explicitly displays
`NO SNAPSHOT ATTACHED`, not made-up demo money or market prices.

## Security review — verified design limits, not a production pen test

| Control | Stage51 implementation | Explicit limitation |
| --- | --- | --- |
| UI command surface | no trade/approve/fill controls or POST requests | other underlying Python APIs still exist |
| External networking | HTML CSP `default-src 'none'`, `connect-src 'none'`; JS no `fetch` / `WebSocket` | local files and browser environment remain untrusted |
| XSS | only `textContent`; no `innerHTML`; strict input schema | a malicious browser extension or tampered local assets is out of scope |
| Imported JSON | 256KiB max, signed-source status **not claimed**, explicit denial of production/live flags | the file is NOT cryptographically verified as originating from the account |
| Account privacy | no raw order IDs, signing tokens or credentials; local file picker | local exported account data still requires controlled sharing/storage |
| Capital | never sums independent cash books; mismatch alert | two SQLite ledgers are still not globally atomic |
| Risk & approval | displays configuration/limits and missing auth flags | independent signer/IDP, mandatory risk service and global legacy path controls unfinished |
| Market data | explicit not-connected indicators; no fake price | genuine point-in-time Indian F&O feed deferred |
| Digital human identity | official face asset remains unmodified and not substituted | original approved face needs user-supplied exact asset |
| PR integration | staged PR and CI evidence, no merge | main branch reported `protected=false`; owner must review branch rulesets |

## PR stack checkpoint (actual GitHub records at Stage51 review)

| Stage | Draft PR | Expected parent |
| --- | --- | --- |
| 46 integration audit | #38 | Stage45 |
| 47 paper Risk & Veto facade | #39 | Stage46 |
| 48 signed paper approval | #40 | Stage47 |
| 49 cooperative crash fence | #41 | Stage48 |
| 50 read-only backend snapshot | #42 | Stage49 |
| 51 static UI + demo export | this PR | Stage50 |

Each of #38–#42 was open, unmerged and draft at review; Stage51 is also
intended to stay draft/unmerged. GitHub reported **main protected=false**
and main HEAD
`40e93cfb77fa0650e4f57428c6d77f70bb78d564`.

## Critical outstanding work — do not treat Stage51 CI as release

1. Reconcile the **independent main-rooted stacks** (#1 vs #3)
   and semantic calibration file overlaps first (Stage46 findings).
   Verify the prospective **combined merged tree**, not just stacked
   development CI; require owner reviews, branch rulesets and CI gates.
2. Build a real mandatory **separate secure entry process/service** so
   no legacy API bypass is possible; independent risk & veto with a
   trusted authenticated identity and verifiable audit boundary.
3. Build a **unified durable capital ledger** or mechanically enforced
   isolation/real reconciliation of budgets. The Stage49 coordinator is
   an additional **one-shot cooperative fence**, not double-entry
   cross-DB settlement or capital conservation.
4. Integrate proper **external human identity + key custody**
   (Stage48 HMAC possession alone is not identity), with revocation
   and approval/fill-time checks.
5. Wire exact **approved cybernetic face asset** and final art direction
   to the visual frontend, and decide whether an authenticated
   localhost/remote dashboard service is warranted. Currently file import
   is manual by design.
6. At the *owner-approved later data stage*, ingest licensed
   point-in-time NIFTY/BANKNIFTY F&O and crypto market feeds, verify
   quality, instruments, fees, slippage, market liquidity, calendar,
   margin, costs and real shadow evidence. No source is connected now.
7. Re-run negative/crash/concurrency tests on combined reviewed tree.
   No live broker access or autonomous strategy promotion permitted.

## Final CI acceptance criteria

```bash
python -m pytest -q tests/test_stage51_visual_dashboard.py
python -m pytest -q
```

The project GitHub Actions matrix must pass **Python 3.11, 3.12 and
3.13 on the final PR-head commit**, including the Node JS-renderer
security harness where Node is available and existing Stage25 synthetic
integration smoke. Test passes demonstrate **offline local UI behavior
only**; they do not prove profitability, real feed accuracy, identity,
production security, or project completion.
