# NEXUS TITAN Security & Trust Boundaries

## Status
This document is an engineering threat-model baseline, not a penetration-test certificate or production security approval. The current project is research/shadow-only. Live broker order routing is not approved.

## Protected assets
- Virtual account balances, positions, fills and reconciliation records.
- Approval signing secrets and consumed-token database.
- Dataset provenance, instrument metadata and backtest evidence.
- Risk limits, permissions, emergency kill-switch state and audit history.
- TITAN EVOLVE proposals, experiments and generated artifacts.

## Trust boundaries
1. Market data and Telegram content are untrusted input. They must never be treated as instructions or trusted trade recommendations.
2. Strategies, specialist agents and EVOLVE outputs are proposals only.
3. Consensus is not risk approval. Independent risk checks remain authoritative.
4. Approval tokens are cryptographic integrity/replay controls, not proof of human identity, MFA, non-repudiation or secure key custody.
5. SQLite/WAL durability is not encryption-at-rest or protection against a privileged local attacker.
6. The execution simulator is not an exchange matching engine and is not calibrated to live queue position/latency.

## Mandatory deployment controls
- Keep live trading disabled; do not configure broker credentials for this research build.
- Store signing keys in an OS secret store or managed secret service; never commit them or place them in SQLite.
- Restrict filesystem permissions on databases, backups, logs and datasets.
- Use least-privilege OS accounts and isolate research workloads from personal files.
- Verify dataset licence and permitted use before importing or sharing market data.
- Back up state and test restore before unattended operation.
- Review every proposed code change; generated code must not modify risk, permissions, kill-switch or live-order boundaries.

## Incident response
On suspected data corruption, credential exposure, ledger mismatch or unexpected order-like activity: stop research intake, preserve logs and hashes, isolate the affected copy, do not attempt live recovery, and require an authorized human review before resuming.

## Release blockers
Independent penetration test, secret-management review, dependency/SBOM review, backup-restore drill, operational recovery drill, licensed data evidence, multi-day shadow evidence and owner sign-off remain external release requirements.
