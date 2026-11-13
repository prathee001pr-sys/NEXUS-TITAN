# NEXUS TITAN — Stages 196–200 Github-first QA checkpoint (2026-11-13)

## Exact scope

Additive synthetic-only Stage 196–200 candidate based on GitHub Stage 195 head
`c7e636567f6caaaaa7aa2de3d310753faf737acd`, branch
`feature/stages191-195-2026-11-12` (draft PR #121, stacked on Stage 186–190).

The new GitHub branch `feature/stages196-200-github-first-2026-11-13` was
created at the above head, **without changing its files**. Do not claim Stage
196–200 is GitHub-committed until the feature branch push succeeds.

## Verification performed in an isolated container

- Manifest SHA-256: 8/8 entries verified.
- Reconstructed code: Stage 153 full archive + additive Stage 154–195 overlays
  + supplied Stage 196–200 patch; no older files overwritten.
- Stage 185–195 source: 11 of 11 file Git blob SHA-1 hashes matched the
  corresponding GitHub Stage 195 branch files.
- Existing SQLite operations source involved in strict-warning failure also
  matched the GitHub Stage 195 branch.
- Stage 196–200 focused: **31 passed, 0 failed**.
- Stage 181–200 focused: **240 passed, 0 failed**.
- Stage 154–200 focused: **397 passed, 0 failed** using
  `PYTHONPATH=src python -m pytest -q -o addopts='' -W error ...`.
- GitHub Stage 195 head workflows: CI and Secret Scan completed successfully.

## Full suite limitation (not a pass)

The full reconstructed-repository test run under Python 3.13 and strict
`-W error` was interrupted by a long timeout. Before interruption, multiple
failures/errors were indicated. A bounded `-x` re-run showed a pre-existing
`sqlite3.Connection` ResourceWarning / PytestUnraisableExceptionWarning
arising from `src/nexus_titan/operations/isolated_atomic_execution_book.py`
in `tests/test_full_chain_fo_data_to_sandbox_e2e.py`. That operations source
matches Stage 195 on GitHub and is **not modified by this patch**. Do not
claim 4,126 tests pass for Stage 200. A fresh GitHub Actions CI run after
push is needed to assess the exact GitHub checkout and matrix.

## Safety

All new features are synthetic/offline review only. Caller-provided
attestation flags are not independent proof. No live broker execution,
autonomous trading permission, strategy promotion, or merge to main.

## GitHub commit policy

Use the accompanying manual Replit Shell script, which sets GitHub
noreply author/committer, verifies them before push, stops on collisions,
runs Stage 154–200 strict focused tests, and pushes only the feature branch.
No GitHub API commit publishing is used due to past email-privacy concerns.
