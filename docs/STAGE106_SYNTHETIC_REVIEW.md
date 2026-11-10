# NEXUS TITAN Stage106 — Synthetic out-of-sample chronology / leakage guard (NO LIVE)

**Parent:** Green Stage105 feature branch. Exact typed Stage103 assurance, Stage104 training and holdout catalogs, and Stage105 synthetic execution preview.

- Rejects training/holdout overlap by date and source hash; requires strictly earlier training sessions and a separate catalog matching the Stage105 execution lineage and Stage103 chain/window hashes.
- Requires 2–100 explicit synthetic forecasts with IST minute timestamps; forecast before known-outcome time, no overlapping labels, all observations within the checked holdout source-bar interval.
- Returns only **illustrative direction match count** on synthetic labels. It is explicitly **not** authenticated predictive accuracy, tradable alpha, profitability, calibrated probabilities, actual out-of-sample validation or a strategy promotion permit.
- Immutable report and deterministic local research fingerprint. No model weight updates, performance scores eligible for live, broker routes, human-approval minting, audit-log rewriting or automatic risk setting changes.

**Acceptance gate:** -W error focused and full exact-checkout regression, Draft PR, GitHub 3.11/3.12/3.13 and Secret Scan. OOS on actual licensed historical data and prospective paper/shadow evidence remain open.
