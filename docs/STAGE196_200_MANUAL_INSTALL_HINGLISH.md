# NEXUS TITAN — Stages 196–200 Manual ZIP Patch

## Scope and status

**Additive patch only**, not a complete repository ZIP. Built for the latest verified Stage 195 feature-branch API (`feature/stages191-195-2026-11-12`, commit `c7e636567f6caaaaa7aa2de3d310753faf737acd`). The original source code and existing tests stay untouched.

- Stage 196: real Stage 191→195 synthetic ledger, drawdown, cost, holdout, review-gate orchestration.
- Stage 197: multiple bounded incremental cost stress scenarios.
- Stage 198: UTC-normalized deterministic closed-ledger replay comparison.
- Stage 199: recompute and reconcile every Stage 196–198 evidence receipt.
- Stage 200: explicit synthetic-only review NO-GO gate for broker execution, autonomy and strategy promotion.

**Important:** Passing these checks never demonstrates real-market profitability or grants permission to trade. `*_attested=True` inputs are *caller claims*, not proof of independent verification. This patch includes one positive and one duplicate-fill negative actual Stage 190→200 integration regression, but that full integration is pending execution against the complete repository.

## Android/Replit manual install

1. In Replit, open the existing NEXUS-TITAN project. Do not use Replit AI Agent.
2. Make sure the current project contains `src/nexus_titan/data/stage195_offline_portfolio_gate.py`. If absent, the Stage 195 base must be installed first.
3. Upload the ZIP file **without extracting it in the Replit file browser** to the project root (beside `pyproject.toml`).
4. Open Replit **Shell** (not Agent) and run the commands below.

```bash
cd ~/workspace/nexus-titan
pwd
ls -l pyproject.toml src/nexus_titan/data/stage195_offline_portfolio_gate.py
ls -lh NEXUS_TITAN_STAGE196_200_MANUAL_PATCH.zip
unzip -l NEXUS_TITAN_STAGE196_200_MANUAL_PATCH.zip
```

**Do not install over existing Stage 196–200 files.** Check collisions first:

```bash
for n in 196 197 198 199 200; do
  find src/nexus_titan/data -maxdepth 1 -type f -name "stage${n}_*.py"
done
ls tests/test_stage196_200_batch.py 2>/dev/null || true
```

If any existing Stage 196–200 files are listed, **STOP**: send the list back for safe reconciliation. Do not overwrite them. If none are listed, install the patch non-destructively:

```bash
unzip -n NEXUS_TITAN_STAGE196_200_MANUAL_PATCH.zip -d .
```

Run focused tests:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -o addopts='' -W error tests/test_stage196_200_batch.py
```

If `.venv/bin/python` does not exist, use your existing project Python interpreter instead. If focused tests are green, run complete regression:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q -o addopts='' -W error tests/
```

Do not commit/push on `main`. Git author/committer must use GitHub noreply email if you choose to commit. No live trading.

## Verification claims

- Local tool environment: 29 offline focused unit/negative cases passed against a **reconstructed compatibility fixture**, with 1 actual Stage 190 integration case intentionally excluded; a second actual Stage 190 integration negative test is provided but was not run locally.
- These are **not** evidence of successful full repository regression.
- Official Replit test count, and GitHub Actions/Secret Scan for this patch: **not verified**.

If a test fails, capture the complete traceback and stop. Avoid blind repairs or upgrading packages unnecessarily.
