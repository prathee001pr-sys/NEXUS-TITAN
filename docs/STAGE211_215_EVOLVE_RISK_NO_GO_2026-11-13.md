# Stages 211–215 — Governed TITAN EVOLVE / Independent Risk Veto (offline research only)

## Scope

This is an **additive, read-only, synthetic research** checkpoint on top of Stage 210, not a new execution path. Existing `evolve/governance.py`, `risk/authoritative_risk.py` and risk-control modules are **untouched**. All new receipts default to `False` for live trading, code execution, risk modifications, autonomous execution and strategy promotion.

| Stage | Added module | Acceptance semantics |
| --- | --- | --- |
| 211 | `stage211_evolve_candidate.py` | Immutable, fingerprinted, allowlisted research hypothesis; reject protected targets and permission requests |
| 212 | `stage212_evolve_review.py` | Caller-supplied distinct reviewer identity and fixed risk-policy fingerprint; approval is **offline-review only** |
| 213 | `stage213_evolve_holdout.py` | Bounded strictly chronological train/holdout samples, embargo and synthetic loss cap |
| 214 | `stage214_independent_risk_veto.py` | Read-only synthetic metric limits: drawdown, daily loss, open exposure, data staleness and emergency stop |
| 215 | `stage215_evolve_no_go_gate.py` | Recompute Stage 211–214 receipts from raw inputs and tie them to Stage 210 synthetic NO-GO evidence; reject risk-policy substitution |

## Explicit proof boundaries

- A typed SHA-256 input is a **caller-provided fingerprint**, not authenticated data or source-code integrity proof. No source files, model code or executables are loaded or run by these modules.
- Distinct `proposer_id` / `reviewer_id` strings are **not identity verification**, signature verification or human approval authentication. Real authorization needs an external owner-only IAM workflow.
- Stage 213 timestamps and holdout performance are caller supplied. This does **not** audit upstream feature-leakage, NSE market-data vendor licences, out-of-sample validity or profitable live performance.
- Stage 214 is an **additional paper-review veto**, *not* a replacement for `AuthoritativeRiskEngine`, risk limit enforcement at the broker gateway, an emergency stop or live risk certification. Its `risk_engine_allows_offline_review` input is an attestation, not a verified runtime risk-engine invocation.
- Stage 215 checks a typed Stage 210 NO-GO receipt and its fingerprint but **does not recompute all Stage 210 input artifacts**. It categorically prohibits live trading regardless of receipt acceptance.
- These modules never place orders, use network access, load broker credentials, mutate permissions/risk settings, execute candidate code or promote strategies.

## Tests

- 113 new pytest cases validate stage acceptance and adversarial tampering: NaN/Infinity/booleans, stale market observations, unauthorized requests, unapproved risk-policy changes, forged receipt hashes and candidate–baseline mismatches.
- Combined focused regression (Stage 154–215 and the historical F&O importer compatibility tests): **778 passed, 0 failed**, strict `-W error` mode, in locally reconstructed project snapshot.
- Full GitHub Actions Python 3.11/3.12/3.13 matrix and Secret Scan are **not verified** for this stage until its feature branch has been pushed and CI has finished.

## Integration instructions

- Parent GitHub commit: `defe9fa2cc651062cc9d8e7ee4e56c37989cbcb8` on Stage 206–210 branch.
- Target branch: `feature/stages211-215-evolve-risk-no-go-2026-11-13`.
- Create **draft stacked PR** targeting `feature/stages206-210-execution-realism-2026-11-13` only after safe authenticated push.
- **Never merge to main, enable live trading, change visibility or publish a public dashboard** as part of this patch.
