# Stage 100 — Read-only selected F&O accounting vs expiry scenario boundary

**Status:** additive candidate; fail-closed; NO LIVE; no broker orders; no merge.

Based on exact Stage 99 Draft PR #91 head `bd8254804ce1c4169367ca5776530ef546b8d7b8`.

- Reads an **exact** Stage96 `FOAccountingReview` (selected replay-checked Indian synthetic account, INR only) and the Stage99 `Stage99BatchReview` (1–50 synthetic expiry/margin scenarios).
- Validates immutable journal identity, bounded integer-cent cash/cost/realized conservation, synthetic mark identity, account statistics eligibility and scenario type/flags/finite values/uniqueness.
- Returns a deterministic SHA-256 fingerprint of the *synthetic scenario input*. Not a verified signature or source attestation.
- Crucial: Stage99 hypothetical expiry payoffs **are not linked to actual selected account fills**, so `expiry_to_journal_linkage_verified` remains `False`. No scenario P&L is added to the actual account.
- Leaves futures fee-adjusted net P&L unverified; indicative SPAN/ELM is not official margin. No actual settlement price, broker contract note, exchange-ledger proof or release approval.

**Non-goals:** Editing Stage55/95 execution or existing derivative arithmetic; a paid vendor feed; real-margin settlement; market profitability claims; live order routing.

**Test gate:** focused Stage100 suite with `-W error`; full exact integrated suite; Python 3.11/3.12/3.13 GitHub CI and Secret Scan. Source path `src/nexus_titan/operations/stage100_fo_reconciliation_gate.py`. GitHub must remain a stacked **Draft** PR.
