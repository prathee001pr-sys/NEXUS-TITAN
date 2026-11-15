# NEXUS TITAN — Stage 15 Safety Fix & Combined Stage 1–15 Validation

Date: 2026-11-02

## Safety fixes

1. **Durable emergency lock recovery:** a valid filesystem lock marker takes precedence over an older SQLite snapshot. Missing, malformed, unreadable, or contradictory marker content leaves the account locked and requires recovery; no automatic unlock was added.
2. **Fill idempotency:** a key is bound to the original order, fill price and quantity. An exact retry returns the original order without applying cash, position or fee changes. Reuse for a different order/request is rejected.
3. **Approval integrity:** order approval snapshots use the full 64-character SHA-256 digest instead of a truncated 16-character digest.
4. **Partial-fill fee reconciliation:** entry fees are tracked and amortized across partial exits, eliminating the one-paise final reconciliation discrepancy found during cross-stage integration.
5. Six additional focused regression tests exercise stale SQLite recovery, failed SQLite persistence, corrupt lock markers, idempotency conflicts, restart replay and full-length approval hashes.

## Combined Stage 1–15 integration evidence

- Candidate base: GitHub Phase 6 integration snapshot at `1e9436f6b82baf55eb33d4b98ff0cf47dc6fd69c` plus the Stage 15 Evidence Provenance ZIP.
- 80 Stage 15 paths were not present in the Phase 6 branch snapshot. They include 26 source modules, 17 additional tests, 2 scripts, and supporting documentation/reports/configuration.
- The cross-branch comparison identified 20 overlapping Python files that differed. The Stage 15 versions were selected for the complete candidate where required by the Stage 7–15 APIs; identical shared files were preserved.
- A first mixed-source trial exposed API mismatches and then a partial-exit accounting discrepancy. Those were resolved by reconciling the conflicting Stage 15 source modules and the Stage 15 virtual order manager.
- **Final combined regression:** 412 passed, 5 subtests passed.
- `python scripts/run_project_validation.py`: passed (compile + project test runner).
- Advanced backtest/verification suite: 412/412 passed; code smoke checks for replay protection, stale-feed blocking, kill switch, daily-loss lockout and microstructure fixtures passed; partial-fill accounting and futures/options arithmetic fixtures passed.
- Static secret-pattern scan: 0 findings.
- Release preflight test validation: passed.

## Remaining release blockers

Release decision remains `BLOCKED_EXTERNAL_EVIDENCE`. Licensed historical market data, independent security assessment, operations recovery drill, multi-day shadow evidence and owner sign-off are unverified. The included 120-bar NIFTY dataset is synthetic and promotion-ineligible; the backtest outputs are smoke/research evidence, not evidence of tradable profitability.

The static instrument catalogue is an unverified research reference, and futures/options arithmetic fixtures do not validate current exchange/broker charges or live SPAN/ELM requirements. Full API/behavior review and external data/provider verification are still required.

## GitHub state and release boundary

- Existing Phase 6 integration PR remains draft; its GitHub Actions run #41388360519 reported 286 passed and 5 subtests for the Phase 6 branch snapshot.
- The 412-test combined Stage 1–15 candidate has been validated in the local clean integration workspace and packaged separately; it is **not yet the committed source tree of that GitHub PR**.
- `main` has not been modified or merged.
- No broker connection, real-money order route or live trading was enabled.
