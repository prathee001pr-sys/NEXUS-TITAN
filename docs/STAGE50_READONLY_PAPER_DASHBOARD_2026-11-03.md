# NEXUS TITAN — Stage 50 Read-Only Paper Safety Dashboard

**Date:** 2026-11-03  
**Branch:** `feature/stage50-readonly-paper-dashboard-2026-11-03`  
**Parent:** Stage49 draft PR #41  
**Product status:** Local backend data contract only; visual frontend is NOT finished

## Scope

Keep the user's **locked black-and-silver digital-human TITAN** design. Do
not replace, recolor or fabricate the approved face artwork. The previously
approved digital-human image is not committed by this stage; the read model
returns an explicit `EXTERNAL_APPROVED_REFERENCE_REQUIRED` asset marker.

This stage connects *read-only, accurately labeled* local Stage43–49 paper
safety evidence to the existing `DashboardBackendService`. The JSON is
meant to be rendered by the separately approved visual dashboard; no new
interactive trade or approval button, HTTP command route, websocket, login
portal, external quote feed or browser app is added here.

### Files

- `src/nexus_titan/dashboard/paper_read_model.py`
  - `Stage50ReadOnlyPaperDashboard(fence)` only accepts a real Stage49
    coordinator bound to a Stage48 signed-paper session and its underlying
    virtual account. Data is inspected on demand, never mutates a paper
    order or any capital/reservation fields.
  - `snapshot()` returns a JSON-friendly versioned report:
    - identity of the synthetic local research source; UTC observation time
    - explicitly documented black/silver, restrained cyan and red/green
      theme tokens plus **no fabricated digital face asset**
    - initial starting capital and **separate** virtual vs research cash in
      exact cents, NOT a bogus aggregated cash figure
    - local manual/gateway paper safety and kill switch state
    - Stage49 attempt count and PREPARING/PENDING/UNKNOWN marker
    - count of pending/accepted paper orders and simulated fill fragments
    - signed callback configuration **without exposing token or signature**
    - configured risk thresholds, with an explicit
      `NOT_EVALUATED_NO_TRUSTED_QUOTE` new-trade verdict
    - missing live/actual Indian F&O, crypto, news and options data status
    - EVOLVE and production gating warnings
    - prominently false market-source / identity / cross-ledger / broker /
      live trading / strategy promotion / global authority assertions
  - Explicit `LOCAL_REVIEW_REQUIRED` status on missing or broken guard
    evidence, cash mismatch, active kill switch, and prior coordinator
    attempt; do not color an unresolved crash or risk drift "green".
  - No outgoing network calls, broker SDK imports, order IDs, trading
    actor IDs, key material, or hidden approval actions.

- `src/nexus_titan/dashboard/api_service.py`
  - Adds optional `stage50_paper_dashboard=...` to
    `DashboardBackendService`; rejects binding to any other account.
  - Adds `get_stage50_paper_safety()` read-only access.
  - Existing `get_system_telemetry()` exposes `paper_safety`.
  - When not explicitly attached the new panel reports
    `NOT_ATTACHED` and `data_source=NONE`; existing service inputs and
    backtests remain compatible. This has no HTTP order endpoint.

- `tests/test_stage50_paper_dashboard_read_model.py`
  - Synthetic variable-capital checks and no double counting
  - No fabricated quotes or identity assertions
  - Before/after one pending Stage49 synthetic paper entry
  - Signed local accepted order remains **unfilled**
  - Crash PREPARING marker, invalid coordinator scope, capital drift,
    kill switch, default-disabled config, replaced approval callback
  - Repeated read snapshots do not change account revisions or orders
  - No leak of order IDs, HMAC signatures or replay secrets
  - Existing dashboard opt-in account match / legacy fallback / JSON smoke

- `scripts/run_stage50_paper_dashboard_smoke.py`
  - Temporary SQLite synthetic accounts and a single pending paper BUY;
    outputs a JSON "before" and "after" snapshot; no broker, real market
    data, live orders, fills, tokens or actual images.

### Display safety semantics

**No account-level "green" badge grants trading authority.** The
`LOCAL_SYNTHETIC_REVIEW_ONLY` status says only that local paper audit
reads were consistent at the moment of the inspection. It does not
authenticate any exchange feed, external signer, live broker, or global
Risk & Veto service.

The `paper_orders_enabled_in_config` field is descriptive, not an
interactive control. The frontend **must not** treat JSON as a trusted
order/approval instruction, and should keep all action buttons disabled.

The current backend does not implement a full rendered TITAN UI or
authenticate a dashboard viewer. If exposed over HTTP later, add proper
authentication, authorization, cache restrictions, provenance validation
and security headers before displaying any private account data remotely.

### Tests

```bash
python scripts/run_stage50_paper_dashboard_smoke.py
python -m pytest -q tests/test_stage50_paper_dashboard_read_model.py
python -m pytest -q
```

Require Python 3.11, 3.12 and 3.13 CI green for the final commit/PR, and
verify synthetic Stage25 system smoke. A passing dashboard regression
is NOT real shadow/live trading acceptance.

### Remaining blocking tasks

- Build visual frontend bound to these read-only fields using the exact
  approved original TITAN face image and approved layout.
- Independent identity/key custody and truly enforced global risk service.
- Unified capital authority or independently isolated enforced budgets
  with provable cross-book reconciliation, crash/restore reviews.
- Review stacked draft PRs, branch protection, merged-tree CI.
- Legitimate licensed point-in-time NSE F&O feed and extended realistic
  historical/backtest/shadow validation added later per owner preference.
- Explicit owner-reviewed release checklist before even considering live
  broker access (not authorized by this milestone).

**No automatic merges, live trading, real-money transactions, or autonomous
strategy promotion.**
