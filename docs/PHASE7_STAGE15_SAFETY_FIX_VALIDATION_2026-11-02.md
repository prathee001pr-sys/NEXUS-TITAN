# NEXUS TITAN — Stage 15 Safety Fix Validation

Date: 2026-11-02

## Fixes applied

1. **Durable kill-switch recovery:** a valid filesystem lock marker now overrides an older SQLite snapshot. Missing, malformed, unreadable, or contradictory marker content is treated as locked and requires operator recovery. The system does not auto-unlock.
2. **Fill idempotency binding:** a key is bound to the original order ID, fill price, and quantity. An exact retry returns the original order without applying cash, position, or fee changes. Reusing the key for a different order or request raises a conflict. A persisted key without its fill record fails closed.
3. **Approval integrity:** order approval snapshot fingerprints now use the complete 64-character SHA-256 digest rather than a 16-character prefix.
4. **Evidence refresh:** the advanced backtest evidence report and release preflight report were regenerated from the corrected Stage 15 source snapshot.

## Offline verification of the Stage 15 source snapshot

- Before fixes: **406 passed, 5 subtests passed**.
- Six new safety regression tests added.
- After fixes: **412 passed, 5 subtests passed**.
- Python compile check: passed.
- Advanced backtest report: generated successfully; its test evidence records 412/412 passed.
- Release preflight: test validation passed and secret scan reported zero findings.
- Release status remains **BLOCKED_EXTERNAL_EVIDENCE**; licensed historical market data, independent security assessment, operations recovery drill, multi-day shadow evidence, and owner sign-off are still unverified.

## Scope note

The 412-test result above is from the complete Stage 15 ZIP source snapshot run in an isolated local workspace. The GitHub safety branch receives the targeted code fix and regression tests; the branch's own GitHub Actions run is a separate verification result and must pass before this branch is considered validated.

No main-branch updates, merges, broker connections, or live trades were performed.
