# Stage 125 — NSE-style option-chain snapshot adapter (offline)

Base: Phase 04 PR #103 head `2b085facee536fb5f0b3507c54ee453d858677ec`.

Add-only parser, no broker, no network, no persistence, no trading permission. Source filenames and expiry are caller declarations; they do not authenticate exchange origin or exchange calendar. All returned quotes are **NO-GO** for trading, strategy promotion or historical P&L because snapshot observation timestamps and official contract metadata are absent.

Tested with two user-supplied CSV snapshots:
- NIFTY 2026-11-09: 147 strikes / 294 sides, 103 missing bid or ask, 50 missing OI, 21 LTP outside bid-ask.
- BANKNIFTY 2026-11-23: 169 strikes / 338 sides, 14 missing bid or ask, 51 missing OI, 91 LTP outside bid-ask.

Flag counts are side-wise and can overlap. LTP outside bid-ask is not conclusive corruption; quotes and last trade may have different observation times.

Next: Stage 126 explicit timestamp/provenance gate, Stage 127 contract/quote QA, Stage 128 integration acceptance. Do not synthesize missing timestamps, authenticate providers by filename, or infer strategy returns from snapshots.
