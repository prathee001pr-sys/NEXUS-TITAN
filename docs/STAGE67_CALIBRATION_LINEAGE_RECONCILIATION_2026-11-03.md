# Stage67 — Calibration Lineage Reconciliation Candidate (not main)

**2026-11-03** — Offline GitHub branch integration, development-only. No broker, real data, capital actions, PR merges into main, strategy promotion or live trades.

## Source diff review and resolution choice

Independent PR #3 (\`fa8c34eba862108d6cd333c59964c4e3cc6e6405\`) added the probability calibrator and basic tests. Its child PR #5 (\`d97b9abef59c479cd7a7c8dfb0ffb0fd44f95148\`) added Wilson intervals, stable Brier accumulation, research documentation and an independent CI workflow.

Primary Stage66 branch originated at \`d35dad8edaa07462bf0f48a3b28245022bda66dd\`, includes all Stage65 work and now has complete frozen PR filename inventory and tests.

**Manual content decisions based on actual reviewed sources and Git blob equality:**

| PR #5 file | Selected resolution | Git blob SHA |
| --- | --- | --- |
| \`src/nexus_titan/intelligence/calibration.py\` | Stage66 already byte-identical to PR #5 | \`2f0541b85c8ee88139400b7f049b828a72ae49c7\` |
| \`tests/test_probability_calibration.py\` | Stage66 already byte-identical to PR #5 | \`1316c75483c9daba300f581b9998fb2102d71484\` |
| \`docs/PROBABILITY_CALIBRATION.md\` | Stage66 already byte-identical to PR #5 | \`e60da3a9f545b37938489936ad04512da2069e68\` |
| \`.github/workflows/calibration-hardening.yml\` | Preserved exact independent PR #5 workflow file | \`46d1d7c95c89a1bc409fd2c00ab51bbea27ff956\` |

PR #3's \`intelligence/__init__.py\` is an older subset. Keep the expanded primary branch exports (Git blob \`9066f3f9ceecd3e6eeb0b227bf5d97d0b3c59336\`), including the four calibration exports and later intelligence pipeline objects. This is intentional semantic supersession, not a line-by-line identical \`__init__\`.

The candidate branch history may include a **manual two-parent reconciliation commit** with the Stage66 primary parent and the PR #5 hardening parent. It is an **explicit resolved-tree choice**, not an automatic conflict-free Git merge simulation. Verify exact commit parent/tree and all matrix CI jobs externally before accepting it. PR #3 becomes ancestral through PR #5, but both original PRs remain separately OPEN/DRAFT until owner review.

## Checks and restrictions

- \`operations/stage67_calibration_reconcile.py\` independently computes Git blob identifiers from four reviewed PR #5 files, asserts expanded primary exports, and always refuses merge/production/trading authority.
- \`scripts/run_stage67_calibration_reconciliation.py\` supplies a read-only local no-go smoke report.
- \`tests/test_stage67_calibration_reconciliation.py\` adds source drift, missing/symlinked/oversized candidate, deterministic/readonly and fail-closed CLI regressions.
- Existing exact-branch Python 3.11/3.12/3.13 CI and the imported calibration-specific workflow need to be run on the final tree.

## Final gates still pending

No main merge, owner code review, independently verified branch ruleset, real NSE F&O data, real F&O/crypto net performance, globally unbypassable Risk & Veto, atomic account authority, security validation or signed release. Stacked current PR-file snapshot from Stage66 is stale as soon as later PR heads change and cannot establish production readiness.

**Release verdict: ABSOLUTE NO-GO.** This stage is an offline calibration-lineage integration *candidate*, not a production release or completed independent integration.
