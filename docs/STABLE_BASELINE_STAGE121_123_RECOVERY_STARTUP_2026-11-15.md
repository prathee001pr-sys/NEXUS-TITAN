# NEXUS TITAN — Stable research baseline recovery startup hardening

## Scope and provenance

- Patch base: Stage 224 draft feature commit `d0d63e6b0327b7a89df1b757dcaa68342e15af4b`, not `main`.
- Original `src/nexus_titan/operations/stage121_research_supervisor.py` Git blob: `4434a7c8b1448aa0f13e1903c0724c0c345c13b3`; verified equal to archived source.
- Stage 123 source and both legacy tests were also verified by Git blob identity against the Stage 224 branch.
- Research-only synthetic child is unchanged: no new process commands, broker credentials, trading route, dynamic code, or risk override.

## Diagnosed failure mechanism

Stage 121 uses `subprocess.run(..., timeout=timeout_seconds)` for the *entire* fixed child lifecycle. During `hang_once`, the first attempt must time out; the second attempt should finish. The second attempt is susceptible to cold-start delays because CPython normally imports `site` and executes package initialization. On this bounded local test host (four CPU quota) the following was observed:

| Experiment | Observation |
|---|---|
| Original child after intentional timeout, normal CPU | ~0.88–0.93 s execution of second attempt |
| Original child, 10 independent CPU hogs, four trials | 1 completed / 3 quarantined, each unsuccessful trial reached 3/3 timeouts |
| Hardened child after intentional timeout, normal CPU | ~0.07–0.09 s second-attempt execution |
| Hardened child, same stress level, four trials | 4 completed / 0 quarantined |

**This identifies a reproducible startup overhead contributor** but does not independently prove all historic Stage 121/123 failures or performance on every GitHub runner. CPU contention still can cause legal fail-closed quarantine under more extreme load.

## Implementation

Only one change in the authoritative supervisor: add `-S` to the *already hard-coded*, bounded, noninteractive CPython child command. `-S` skips `site` initialization; `PYTHONPATH` already explicitly points to repository `src` and the child depends only on Python's standard library. No timeout values, lease durations, retry counts, checkpoint, risk, live-order, broker, or permissions code has changed.

New regression tests enforce the fixed child path including `-S`, checkpoint/recovery behavior, and timeout-induced quarantine. In particular, `subprocess.TimeoutExpired` must still lead to a bounded `QUARANTINED` state with zero broker orders.

## Current verification and blockers

- 117 Stage 117–124 guardian, safety and recovery tests passed under `pytest -W error` on the locally reconstructed Stage 224 snapshot.
- Selected 58 Stage 117, 121 and 123 startup/recovery tests passed earlier.
- Original full-suite legacy intermittent behavior was demonstrated under synthetic CPU contention and improved locally, **but no authoritative post-fix GitHub matrix CI or complete repository regression has yet passed**.
- One locally reconstructed full-suite batch and one large combined batch exceeded bounded timeouts; neither should be represented as passed.
- Next: privacy-safe authenticated feature-branch push, stacked draft PR, Python 3.11/3.12/3.13 GitHub CI, repeat startup/recovery tests on CI and resource-constrained hosts, review all stacked PRs before proposing any main merge.

## Final governance

This is recovery startup hardening, **not production recovery certification**, not live trading permission, not a risk-control change and not a main-branch merge. Dataset/vendor evidence, independent security testing, multi-day paper/shadow performance, and owner release approval remain blocked outside the research baseline.
