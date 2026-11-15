# NEXUS TITAN — Stage 216–220 Offline Progress Reliability (14 November 2026)

## Scope and evidence boundary

A bounded offline progress tracking/recovery feature batch, built as five **additive** Python modules with an adversarial test suite. Source is synthetic/caller-submitted. A Git branch/commit ID, a hash, a claimed green CI label or a local JSON backup **does not** constitute independent GitHub provenance, an owner identity check, tamper-proof attestations or production readiness.

Stage progress must **never** be silently labelled independently verified. All dashboard projection rows are `UNVERIFIED`, `SUBMITTED_UNVERIFIED`, `LOCAL_TEST_REPORTED_UNVERIFIED`, or `CI_REPORTED_UNVERIFIED`. Even after a real GitHub CI check the backend caller must not claim independently verified solely from these offline modules.

### Implemented stages

| Stage | Source | Responsibility | External verification |
|---|---|---|---|
| 216 | `stage216_progress_evidence.py` | Accept bounded caller-submitted evidence; preserve feature-branch Git SHA-1/256 object labels, digest and reported CI/scan status | None |
| 217 | `stage217_progress_journal.py` | Deterministic hash-chain journal with sequence and replay rechecking | No signatures / no immutable remote log |
| 218 | `stage218_dashboard_projection.py` | Read-only data projection of stages 1–220, all explicitly unverified | Not a web server, no authentication |
| 219 | `stage219_progress_backup.py` | Exclusive-create, 0600 local JSON snapshot, in-file SHA-256 integrity, safe restore, path and JSON hardening | No authenticated/off-site backup or disaster recovery certification |
| 220 | `stage220_offline_progress_no_go.py` | End-to-end replay and backup cross-check, linked to Stage 215 synthetic research receipt; reject prohibited requests | Always NO-GO for live trading, deployment, promotion and risk changes |

### Critical security properties

- No broker network calls, orders, risk-policy mutation, live/autonomous trading, strategy promotion, or dashboard deployment.
- No public or anonymous access endpoints: **there is no deployed endpoint in this batch.** Owner-only authentication, direct URL/data endpoint access checks, and site deployment are **out of scope** and **not verified**.
- The repository visibility, main branch, existing PRs and existing stages remain unchanged.
- Fail closed on wrong record type, malformed stage/branch/commit/digests, double-spends of journal sequence, event tampering, forged `VERIFIED` status, forged access flags, altered backup, duplicate JSON keys, symlinked paths, world-readable snapshots, hardlinks, mismatched replay and prohibited permission requests.
- Local SHA hashes are integrity checks, not external authenticity. The progress event hash-chain must be compared against an independently retained trusted head to detect malicious replacement of the entire chain.
- Stage 220 validates the *reported* CI and scan fields as labels and still marks independent verification as false; GitHub Actions verification requires separate connector proof.

### Testing

- New isolated Stage 216–220 adversarial suite: **139 passed, 0 failed**, Python 3.13, `pytest -q -o addopts='' -W error`.
- Combined Stage 154–220 + historical F&O targeted tests: **917 passed, 0 failed** in strict warnings mode.
- Stage 216–220 reconstructed local full suite across four bounded batches (199 test modules): **4,564 passed, 2 failed, 2 skipped + 5 subtests passed**. Warnings filtered for only `DeprecationWarning` and `ResourceWarning` on this full-suite run. **Full regression is NOT green.**
- Both failures are in **pre-existing research-process watchdog/recovery tests** (not Stage 216–220):
  - `tests/test_stage121_research_supervisor.py::test_hanging_worker_killed_and_recovered` — the 1.2-second worker timeout caused excess attempts and timeouts versus the expected recovery. Isolated re-run also failed.
  - `tests/test_stage123_recovery_fault_lab.py::test_full_real_process_fault_matrix` — failed an aggregate synthetic fault-lab acceptance in the full batch; isolated re-run passed. Timing-sensitive and needs bounded reproducibility audit.
- **Finding P1 (reliability validation):** the legacy watchdog timeout and process recovery must be audited/repaired and full GitHub regression rerun before declaring a clean release baseline. No production code changes were made to Stage 121/123 as part of this new offline progress batch.
- GitHub 3.11/3.12/3.13 CI and Secret Scan for Stage 216–220: **not run yet** until feature commit is pushed and Draft PR opened.

### Known limitations / future scope

1. An owner-only privately deployed dashboard with persistent database and authenticated API endpoints is not implemented by these data classes. Must implement and independently test authorization on every URL and API endpoint before any private deployment.
2. Backup is on-disk local JSON, not automatic off-site backup. Does not implement multi-device sync, remote storage or server-grade durability.
3. Real-time GitHub CI evidence must be fetched and verified via authenticated GitHub, not claimed by a caller.
4. No licensed real historical NSE F&O feed, reproducible live execution or broker simulator can be inferred from this batch.
5. `main` must remain unmerged; risk, broker and live-trading controls remain disabled absent explicit owner approval.
