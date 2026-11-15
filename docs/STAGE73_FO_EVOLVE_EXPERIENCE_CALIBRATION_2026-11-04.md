# Stage73 — TITAN EVOLVE F&O Experience Memory and Paired OOS Calibration

2026-11-04. Stacked draft on Stage72 PR #64, not merged to main. India NIFTY/BANKNIFTY F&O remains the primary research scope. Crypto stays isolated.

## Built
- \`src/nexus_titan/evolve/stage73_fo_experience.py\` adds a bounded, **in-memory** journal of immutable F&O forecasts and later binary outcome declarations.
- Each forecast references existing Stage72 IV/Greeks research output and Stage71 aligned-data SHA-256 labels; locks the training cutoff, observation timestamp, prediction, horizon, expiry cutoff, market regime and event definition.
- Admission rejects future or stale input, duplicate forecasts/outcomes, labels arriving before horizon, post-expiry resolution, forged permission claims, invalid probabilities or different evidence/horizons used by competing models for the same episode.
- Local SHA-256-linked journal detects accidental or direct local mutation; it is **not** durable, authenticated, externally timestamped, independently immutable, or resistant to complete malicious rewrite.
- Reuses existing \`ProbabilityCalibrator\` for out-of-sample probability Brier score, expected calibration error, reliability bins and Wilson intervals; adds per-regime descriptive Brier and paired Champion/Challenger comparison on identical resolved episodes.
- Requires sufficient paired OOS observations (100 by default) and lower challenger Brier for even a research-review suggestion. All promotion, execution and live flags stay false.
- Added synthetic/negative tests, deterministic no-input smoke and GitHub CI 3.11/3.12/3.13 integration.

## Strict limits
- **No trained new models, no model-weight learning, no automatic strategy execution or promotion.** This is an experience-memory and measurement foundation, not an already autonomous self-improving AI.
- Outcomes are explicitly **operator supplied** and NOT independently reconciled to exchange market prices; source hashes bind declared strings, not authenticity.
- Event is deliberately only \`UNDERLYING_UP_AT_HORIZON\`, not option CE/PE net P&L. Better directional forecast Brier score can still produce losses after option premium, theta decay, IV, spread, commissions and taxes.
- All forecast timestamps, model training cutoffs, regimes, data labels, and OOS declarations are unauthenticated. No proof of live anti-selection controls or true leak-free training. Real deployment requires signed append-only audit/attestation, immutable actual forecast-before-label event capture, vendor-licensed data, rigorous preregistered splits and prospective independent performance verification.
- Existing Evolve governance prohibits changing protected controls. This module introduces no risky broker paths and requires separate human approval for eventual promotions.
- This work does not address unresolved main-root PR integration, missing main branch protection, unbypassable global risk, atomic position/capital ledger, or real-feed supervised shadow trading.

**Release verdict: NO-GO.** No broker, no paper/live order, no model training, no changes to main, no strategy promotion.

Next suggested work: Stage74 bounded F&O scenario lab with realistic cost/expiry stress and shadow evidence standards, *without inventing historical fills*.
