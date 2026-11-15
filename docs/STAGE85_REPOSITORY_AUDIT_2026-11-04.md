# Stage 85: verified integration candidate audit

## Source and history

Connector reads on 2026-11-04 verified Stage84 head `034eb43bdf196062e903f943fa172bb0576cbb7f`, tree `9f68c80319a11beb775c660ce3baeb136cdc1d5a`, draft PR #77, and unchanged main `40e93cfb77fa0650e4f57428c6d77f70bb78d564`. The 493-file snapshot was materialized through the authorized GitHub connector and every Git blob and the complete tree hash were reproduced locally. CLI GitHub authentication is absent; publication uses connector Git objects with the actual remote parent, never the temporary local mirror commit.

GitHub compare confirms root PR #1 (`1e9436f6b82baf55eb33d4b98ff0cf47dc6fd69c`), root PR #3 (`fa8c34eba862108d6cd333c59964c4e3cc6e6405`), PR #5 (`d97b9abef59c479cd7a7c8dfb0ffb0fd44f95148`), and main are ancestors of Stage84 (behind=0). Original root trees have no competing different edits against their common main ancestor. Later calibration overlap in PRs #3/#5/#6 was reconciled by Stage67: its four pinned PR5 blobs and expanded primary exports remain unchanged. We retain that reviewed selection; we do not replay or merge old root PRs onto main.

All 76 open draft PRs were inventoried, with complete changed-filename lists from the paginated connector. 41 paths occur in multiple PRs. Repeated edits are mostly stacked dependencies; they do not by themselves prove conflicts. The snapshot includes exact bases/heads and filenames. This is filename coverage and selected semantic review, not an exhaustive review of every historic patch. Main is reported unprotected in the branch listing; protection settings were not modified.

## Actual architecture and boundaries

| Existing path | Connected behavior | Remaining limitation |
|---|---|---|
| Stage59/44 -> Stage71 -> Stage72 | Validates futures/options CSV and contracts, performs as-of alignment and expiry/IV/Greeks research | Fabricated fixtures; no authenticated exchange feed/licence |
| Stage72 -> Stage73 -> Stage74 -> Stage75/76 | Calibration memory, scenario losses, readiness and portfolio risk screen | Research packets and telemetry are caller supplied; no order authority |
| Stage77 -> Stage55 | Rechecks Stage76 then reserves/fills/cancels in one SQLite book with exact-head CAS | Direct Stage55 API can skip Stage76; gateway state is volatile and rejects nonempty restart |
| Stage82 inside Stage55 `_record` | Same-transaction local kill switch stops direct OPEN and FILL; CANCEL remains possible | Local stop can be cleared without authenticated operator credentials |
| Stage83 | Coherent replay, cash/hold/cost arithmetic and comparison to research plan | Read-only comparison; not enforcement of portfolio commitments |
| VirtualAccount / PaperIntentGateway / Stage19 / Stage49 / Stage53 | Existing separate paper, research, approval and hold implementations | Separate ledgers and optional strict modes; not a single global F&O account |
| CryptoVirtualAccount | Separate virtual crypto accounting and costs | Must stay isolated from Indian F&O capital and permissions |
| EVOLVE / governed proposals | Existing review and human approval interfaces | No new automatic promotion or permission mutation is introduced |

Stage81 is a frozen ancestry/source contract check, not a live Git verifier. Stage84 tests execute real Python module calls on synthetic CSVs; they do not establish global risk enforcement. Existing end-to-end tests cover two F&O underlyings sharing one Stage55 book.

Identified duplicate responsibilities are the several capital ledgers, overlapping paper-entry facades, two EVOLVE research/governance generations, and three CI workflows. Functioning implementations are retained. No broker is configured or connected. Hash chains detect ordinary corruption, not an attacker rewriting an entire SQLite database. Existing local approval/telemetry objects do not authenticate a human. These are release blockers, not reasons to discard the existing architecture.

## Candidate hardening

Extended the existing integration audit with a whole-package dependency inventory (150 Python source modules at this stage), duplicate top-level definition detection, identical-file reporting and missing internal import target detection. Tests actually import every module and exercise the retained Stage67 calibration resolution. A standalone read-only audit is added to the existing three-version CI. Static import-target checks do not prove dynamic call dominance; full regression provides behavioral evidence only for tested paths.

## Validation

Unmodified Stage84 baseline: **2,316 passed, 0 failed** locally on Python 3.12.14; 5 pytest subtests are reported separately. GitHub run `41824039895` succeeded for 3.11/3.12/3.13, and its 3.12 job log explicitly reports 2,316 passed. Editable installation and `pip check` passed. Stage85 final local regression: **2,319 passed, 0 failed**, including 3 new tests (5 subtests counted separately), in 34.54s. Compilation, 150-module/253-edge static dependency review and actual imports passed. Exact-commit remote CI is checked after publication; this document does not pre-claim its outcome.

Stage86 must enforce a persistent default-deny boundary inside the selected Stage55 transaction domain. Stage87 must make its F&O gateway restart-safe and enforce account-wide committed exposure, reservations and costs against the same book. Legacy cross-ledger paths remain outside that selected environment. Real F&O shadow trading also requires licensed genuine data, verified contract calendars/costs/margins, independent risk/operator authentication, forward validation and approved deployment. Live trading and main merge are not authorized.
