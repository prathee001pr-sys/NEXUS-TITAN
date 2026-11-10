# NEXUS TITAN — Phase 03, Stages 117–120

**Date:** 2026-11-10. **Status:** offline add-only research implementation candidate; local test evidence only.

## Purpose

Add exactly four lightweight Python capabilities to the **existing trading-only TITAN codebase**. The user also asks TITAN to proactively explain how to use it most effectively: for each detected gap it should say **"I can do X; that could improve Y; the next action is Z"**, without promising returns.

**Hard constraints:** No direct trade order, broker login, live execution, policy/risk changes, AI-generated code execution, privilege elevation, strategy auto-promotion, repository merge or visibility change. Preserve existing `HealthMonitor`, `evaluate_watchdog`, risk, learning and `GovernedEvolveService` classes untouched.

## Base and provenance

- Base archive: `NEXUS_TITAN_PHASE02_STAGES112_116_FULL_OFFLINE_2026-11-10.zip` (offline reconstructed source, not a fully verified GitHub Phase02 release).
- Existing Phase02 documentation says its **ancestor** is Stage108–111 PR #100 commit `41c7a3166bbaad30e65db0a9cf158a081b98082f`.
- Existing Stage112–116 source modules have *exact* SHA256 checks in `scripts/validate_phase03_install.py` so unanticipated versions are rejected before delta installation.
- Only **new** source/tests/docs/scripts are added. No old module rewritten. Phase02 GitHub CI and Stage117–120 CI are **not** claimed as done.
- Phase02 archive uses test fixtures; it is **not** independently authenticated historical NSE F&O market data.

## What was built

| Stage | File | Actual behavior | Non-goal |
|---|---|---|---|
| 117 | `operations/stage117_guardian_jobs.py` | SQLite WAL durable *research-only* jobs, idempotent ID/fingerprint submit, lease-token fencing, monotonically increasing checkpoints, bounded retries, quarantine, corruption check, SQLite backup | Does **not** act as OS process supervisor, auto-run jobs, control risk, or guarantee zero crashes |
| 118 | `operations/stage118_titan_learn.py` | Permission-labeled short excerpts, PDF page/time citation anchors, content SHA256 dedupe, optional local-text-PDF adapter with `pypdf`, user-supplied timestamped transcript segments, research-only confidence labels | No course-app login, downloading videos, DRM bypass, streaming transcription, OCR, untrusted code execution, or evidence-free profitability claims |
| 119 | `operations/stage119_titan_advisor.py` | Evidence-gated deterministic Hindi/Hinglish suggestions based on explicitly supplied verified/unknown status, priority, user action, benefit, and persisted feedback (`INTERESTED`, `DISMISSED`, `COMPLETED`) | No profit promise, unsolicited external transaction, live advice engine, hidden source-truth inference, or autonomous action |
| 120 | `operations/stage120_governed_learning_advisor.py` | Builds proposed source-cited strategy research hypotheses in **existing** governed `EvolveResearch`; composes a read-only advisor report with immutable NO_GO defaults | No ML training, backtests, strategy promotion, order submission, or AI model execution |

### TITAN ADVISOR example

- "**Aap mujhe licensed NIFTY option data dijiye.** Main official contract metadata aur missing bars validate karne mein madad kar sakta hoon. **Isse backtesting evidence quality improve ho sakti hai.**"
- "**Aap mujhe authorized video transcript/course notes dijiye.** Main citations ke sath candidate strategy rules organize kar sakta hoon. **Isse naye research ideas verify karna aasaan hoga.**"
- "**Aap latest code checkpoint dijiye.** Main CI aur crash-recovery test gaps dhoondhne mein madad kar sakta hoon. **Isse upgrade regressions ka risk kam ho sakta hai.**"

Each suggestion states evidence gap, executable *next* human step, and no verified gain claim. Responses do not depend on buying products or enabling trading.

## Safe execution model

- All work in local SQLite databases, using operator-specified paths; no new always-on daemon.
- Small research chunks; idempotent job IDs, lease expiry and *manual* resume/claim. If a worker fails, checkpoints persist and a stale lease cannot write further. Exhausted jobs quarantine.
- `GuardianJobLedger` is a **recovery foundation**, not yet a true external watchdog/process supervisor. Force-kill simulation validates persisted job state only. Full service crash failover, memory pressure isolation and power-loss recovery need independent deployment testing.
- `LearningEvidenceLibrary` stores **only bounded excerpts** (max 2,048 chars each). PDF max 5 MB / 30 pages default; optional dependency `pypdf` is not added to the project's required dependencies. No course material is scraped.
- Source text is data only and never interpreted as executable instructions. Source permission flags are provided by the operator and must be independently checked; this is not automated legal verification.
- Human-marked confidence (`SUPPORTED`, `CONFLICTED`, etc.) indicates **knowledge/source assessment**, never validated trading alpha or authorization.
- No new job type can request `live_execution`, `broker_order`, `risk_override`, `code_exec`, or similar. `GUARDIAN` is not the independent Risk & Veto.
- Advice feedback changes only suggestion order/visibility, not trading behavior or strategies.

## Tests and acceptance

- New files: `tests/test_stage117_guardian_jobs.py`, `tests/test_stage118_titan_learn.py`, `tests/test_stage119_titan_advisor.py`, `tests/test_stage120_governed_learning_advisor.py`.
- Expected coverage includes idempotency, lease fencing, hard-kill replay from checkpoint, corrupted database fail-closed, rights rejection, time/page citations, untrusted prompt text as data, no-trade flags, proactive suggestions and human-governed proposal.
- Run `PYTHONPATH=src python -m pytest -q -o addopts='' -W error tests/test_stage117* tests/test_stage118* tests/test_stage119* tests/test_stage120*`.
- Run `PYTHONPATH=src python -m pytest -q -o addopts='' --disable-warnings tests/`.
- Run tests on GitHub Python 3.11, 3.12, 3.13 and secret scan after authenticated privacy-safe feature-branch push, **not** from the GitHub API publisher.
- Neither CI verification nor production deployment has been performed by this candidate.

## Replit phone-first installation — do not overwrite existing repo

1. **First** clone/verify exact Stage112–116 candidate into a separate working copy. Do not replace an active Replit project using the FULL zip.
2. Extract `PHASE03...DELTA.zip` into a separate temporary directory, never over the repo directly.
3. Run `python <delta>/scripts/validate_phase03_install.py --root <target_repo> --ancestor-only`. If hashes differ, STOP and reconcile.
4. Verify every delta path does not already exist in target. Copy **new paths only**; never replace an existing module, tests, Git metadata or config.
5. `python scripts/validate_phase03_install.py --focused` then `--full` in the target.
6. Check commit author + committer are GitHub noreply, create separate feature branch, draft PR, run CI and secret scan. No main merge without explicit direction.
7. Run advisor read-only CLI: `PYTHONPATH=src python scripts/run_titan_advisor_demo.py`.

## Not yet implemented (separate gates)

- Automatic daily discovery of courses/videos and app-integrations through authenticated/authorized providers; full video transcription/OCR.
- Multi-provider semantic retrieval, contradiction matching, automatic strategy generation and complete human-reviewed evidence classification.
- Strategy candidate execution and champion/challenger with externally licensed historical data and purged OOS.
- Actual OS-level process supervisor and resource limits, durable incident alerting, full service failover, and production backup restore drills.
- Official current F&O data, complete exchange-specific margin/expiry and L2 order-book replay.
- GUI integration of TITAN ADVISOR, phone notifications or automatic periodic recommendations.

**Verdict: additive offline research foundation. NO_GO for trading, real market claims, production self-modification and strategy promotion.**
