# NEXUS TITAN — Phase 04 / Stages 121–124 (Guardian Reliability)

Date: 10 November 2026. Offline additive research candidate; **no live trading, no deployment approval**.

## Verified starting point

* GitHub Phase 03 PR #102, `feature/phase03-stages117-120-2026-11-10`, commit `77ba2eec628eb5353a46c8d2f8b5eb97191a7a29`.
* Stage117/118/119/120 source hashes match exact GitHub PR #102; known PDF validation fix included. Existing files untouched.
* GitHub Phase 03 CI and Secret Scan had succeeded; these do **not** attest to Phase 04.

## Add-only features

* **121**: `stage121_research_supervisor` — opt-in single-purpose, sealed research checkpoint subprocess harness. Uses existing Stage117 `GuardianJobLedger` for fencing, retries, immutable checkpoints and quarantine. OS-enforced address-space cap on Linux, timeout kills the known child, limited process retries. This is a **fixed synthetic worker**, **not** a production worker supervisor, general command runner, OS/container sandbox or trading failover.
* **122**: `stage122_verified_recovery` — snapshot research ledger with SQLite online backup, checksums, quick check, fsync, atomic no-clobber publication, staged restore to NEW path requiring explicit operator review. Does not auto-restore or operate on broker/trading ledgers.
* **123**: `stage123_recovery_fault_lab` — explicit local synthetic drills: normal exit, abrupt process death after committed checkpoint, hung subprocess timeout/kill, retry quarantine, backup restore and corrupted DB fail-closed. Temporary directories; no market/broker data.
* **124**: `stage124_guardian_release_gate` — structural + typed evidence gates, distinct local research vs PR-review readiness, hardcoded false trade permission and false automatic strategy promotion. Does not claim risk-veto runtime certification.

## Security and reliability boundary

* Existing runtime and source of truth, Risk & Veto, market data, order gateways, CI workflows and existing modules remain unchanged.
* No indefinite daemon, auto-launched server, automatic trading resume, real broker or authenticated exchange feed. Synthetic child launches no untrusted scripts and gets minimal environment (no tokens). No network isolation is claimed at OS level; this is NOT a production sandbox.
* Crash recovery is for one isolated research *demonstration* worker. Real service restarts and durable deployment backups require separate platform engineering, plus persistent storage outside ephemeral Replit runtimes.
* A strategy never becomes approved because of content, AI analysis, test count or a successful crash drill. Existing independent Risk & Veto controls remain authoritative.
* A specific script must pass GitHub 3.11/3.12/3.13 CI and Secret Scan on the new branch before even research PR review; independent human review required.

## Testing

See `docs/PHASE04_VALIDATION_RECEIPT_2026-11-10.md` for actual local results. CI / deployment status is **PENDING** for this phase. No GitHub write is performed by this package.

## Replit setup — ONLY from clean Phase 03 PR #102 working copy

1. Inspect Git root and SHA. Never install into a parent workspace with unrelated untracked files.
2. Extract delta ZIP separately. Run `scripts/validate_phase04_install.py --root <target> --ancestor-only` from the delta area (base hashes).
3. Run `scripts/install_phase04_add_only.py --source <delta> --target <target>` for dry run, then add `--apply` only when safe.
4. In target, run `PYTHONPATH=src <python-with-pytest> scripts/validate_phase04_install.py --focused`, then `--full`.
5. Confirm no existing code modified. Only after new PR and separate 3-version CI + Secret Scan should a review be considered. Do not merge main, change visibility, or enable live trading.

## Future gaps

Existing TITAN runtime uses advisory watchdog only; Phase04 does **not** replace it. Need independently measured CPU/RSS budgets and configurable process supervisor deployed outside ephemeral Replit process, coupled with independently verified trading-core fail-closed recovery. Authentic F&O data, exchange/broker reconciliation and real-market shadow validation are still separate future work.
