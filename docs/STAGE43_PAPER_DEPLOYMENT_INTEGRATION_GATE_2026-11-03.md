# NEXUS TITAN — Stage 43 Paper-Only Deployment & Integration Gate

**Date:** 3 November 2026  
**Branch:** `feature/stage43-paper-deployment-startup-gate-2026-11-03`  
**Base:** Stage 42 draft PR #34  
**Release decision:** OFFLINE RESEARCH ONLY; not approved for production or live trading.

## Stage 43 deliverables

1. `src/nexus_titan/operations/paper_deployment.py`:
   - `PaperDeploymentConfig`: explicit account ID, adjustable starting virtual capital, distinct virtual and research SQLite paths, exact `RESEARCH_PAPER_ONLY` mode, and a **session-local** `paper_orders_enabled=False` default.
   - `open_paper_only_deployment(..., approval_authorizer=...)`: refuses missing operator callback, invalid paths or configuration, partial storage-pair recovery, legacy or mismatched existing account policy, and corrupt/unprotected guarded research database.
   - New isolated accounts bootstrap with durable `strict_paper_mode=True`, `MANUAL_APPROVAL`, authoritative pretrade risk, Stage28 guarded research ledger, and Stage40 irreversible `gateway_only_mode`.
   - Existing accounts **must already** have both persisted strict and gateway-only flags; this startup does not silently convert legacy accounts or discard state. Starting virtual capital must match.
   - Every `request_buy` / `request_sell_to_close` uses the Stage33 gateway; Stage41 BUY risk-policy drift, Stage38 snapshot-CAS, Stage30 kill, Stage37 approval and Stage40 direct-submit denial remain inherited.
   - `status()` rechecks persisted manual/risk/gateway policy, virtual reconciliation, research hash audit, open reservations, inventory, kill state and explicit per-session paper permission. A stale, stopped or suspect account becomes read-only for new paper intents.
   - Status **always** reports false for externally authenticated identity, global legacy-API disablement, cross-ledger atomicity, broker/live execution and production readiness.

2. `tests/test_stage43_paper_deployment_startup.py`:
   - Fresh/read-only startup, explicit enablement, manual pending BUY and owned SELL, restart without implicit permission, no autofills, stale-writer admission rejection, kill-switch restart, unsupported mode/path/invalid capital, explicit legacy nonmigration, strict-but-not-gateway account rejection, one-sided recovery, mismatched capital, corrupted research hash audit, guarded synthetic option reservation and CLI smoke.
   - All tests use temporary paths and synthetic data only.
3. `scripts/run_stage43_paper_deployment_smoke.py`: sample temporary-account smoke producing bounded JSON evidence, zero live orders, never loading market CSV/ZIP or contacting a broker.

## Verified repository integration dependencies

GitHub inspection before this stage found **33 open draft PRs (#1, #3–#34)**, **31 of them targeting another draft feature branch**. Two draft roots target `main` (PR #1, PR #3); the staged branch stack includes a sequential options/research lineage and a separate calibration lineage. The exact current review graph matters: PR #34 targets Stage41 branch, not `main`, and Stage43 should target PR #34's Stage42 branch.

Suggested *human-reviewed* integration order:

- Preserve both original baseline and the calibration side-branch. Compare overlapping data/backtest/risk files to avoid losing fixes while choosing a canonical baseline.
- Review PR dependencies from the baseline and the options/research stack **in topological order**, one PR at a time; do not merge all stacked PRs or force-push them to main automatically.
- Require combined CI on the **actual prospective merged commit**, not just passing CI on an isolated Stage43 branch. Run migrations and old-state restore fixtures on copies.
- Review separate research-ledger and VirtualAccount state transitions and all legacy exposure routes before claiming central enforcement.
- Obtain explicit owner approval and branch policy checks before any merge; this Stage43 work does not merge or change `main`.

## Critical blockers that Stage 43 does NOT solve

**Identity & code integrity.** A configured `approval_authorizer` callable is not an independently verified human identity. Python runtime and SQLite are mutable by application-level code. The local gateway-only adapter remains private-by-convention, not protected by a separate OS process or external policy service. Historic legacy modules still exist and could be used by other entrypoints.

**Risk/account atomicity.** The options research ledger and VirtualAccount are distinct SQLite stores. Matching account IDs and individual hash-chain audits do not provide a common atomic cash or position book, and an account with local positions may not match the research portfolio.

**Data/execution evidence.** No independently licensed, point-in-time NIFTY/BANKNIFTY futures/options history (including strike, expiry, bid/ask, depth, lot sizes and fees) has passed complete coverage validation. No real feed, broker order, broker-side protective order, live position reconciliation or extended shadow track record has been verified.

**Dashboard.** The approved black-and-silver home display remains a design reference, not a connected running frontend. The existing Python DashboardBackendService is read-only and not a finished React/HTML UI.

**TITAN EVOLVE.** Governed research exists, but autonomous promotion and production self-editing remain blocked intentionally.

## Stage gate

This stage is complete only after the latest final commit's GitHub CI matrix is green on Python 3.11, 3.12 and 3.13, with no failed unit tests or CLI smoke checks. Report the run ID and test count in the PR review. Do not mark Stage44–45 complete without data and real shadow evidence.

**Next safe steps:** independent PR-stack integration/merge review, externally enforced risk/identity design, authenticated real F&O historical-source approval and data-quality gates. Keep live trading disabled.
