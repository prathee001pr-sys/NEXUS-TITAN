# NEXUS TITAN Stage104 — Synthetic historical minute catalog integrity (NO LIVE)

**Parent:** Stage103 exact commit `ff56cdd0bd1e539cd86e6233eb35c42664555dfd` / `feature/stage103-synthetic-assurance-gate-2026-11-10`. Additive 3-path change only. This reads Stage101 immutable synthetic single-session windows. No existing trading policy, risk authority, data ingestion, or execution logic is modified.

- Requires 1–20 explicit Stage101 source windows, one underlying (NIFTY or BANKNIFTY), INR, 1-minute granularity, strictly increasing dates, no duplicated sessions, consistent timezone and bar duration/count, bounded positive paise and valid SHA-256 strings.
- Returns immutable one-catalog fingerprint and observed **synthetic session count only**; any unknown official holiday gaps remain unknown, even when supplied sessions are ordered.
- No 15-year NIFTY/BANKNIFTY coverage claim, authenticated provider claim, strategy promotion, account ledger write, external API access, real-market feed, or live order permission.
- Stage104 gates cannot turn Stage101 synthetic fixtures into authentic exchange evidence. Malicious actors can forge local test fixtures; cryptographic local hashes are not exchange signatures.

**Acceptance gate:** `-W error` focused Stage104 tests, entire exact checked-out parent-tree regression, Git CLI noreply commit, Draft PR, Python 3.11/3.12/3.13 CI and independent Secret Scan. All must pass before Stage105 proceeds. No main merge without owner instruction.
