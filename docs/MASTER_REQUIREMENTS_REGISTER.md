# NEXUS TITAN V2 — Master Requirements Register

This register is the initial baseline for tracking requirements through:
**Designed → Built → Tested → Verified**.

A status is advanced only when the acceptance criteria for that state are met.
Transitions to Tested and Verified must include a concrete evidence reference.
The SQLite-backed implementation lives in
`src/nexus_titan/core/requirements.py`.

| ID | Requirement | Acceptance criteria | Initial status | Evidence / notes |
|---|---|---|---|---|
| CORE-001 | Safe configuration | Validated environment and logging settings; paper trading defaults off | Tested | CI run #6 |
| CORE-002 | Permission guard | Live trading and risk/permission changes require human approval | Tested | CI run #6 |
| CORE-003 | Event system | Subscribe, publish, unsubscribe and handler errors are tested | Tested | CI run #6 |
| CORE-004 | Four-layer memory | Working, episodic, knowledge and procedural layers; confidence/source/time validation | Tested | CI run #6 |
| CORE-005 | Durable memory | SQLite records survive close/reopen and support retrieval by layer | Tested | CI run #6 |
| CORE-006 | Lazy module registry | Modules register once and load only when requested | Tested | CI run #6 |
| CORE-007 | Audit ledger | Hash chain verifies and tampering through returned copies is prevented | Tested | CI run #6; persistence test included |
| EVOLVE-001 | Research notes | Research records retain title, hypothesis and source | Tested | CI run #6 |
| EVOLVE-002 | Human-gated experiments | Proposed experiments require an identified human approver before start | Tested | CI run #6 |
| EVOLVE-003 | Protected controls | EVOLVE cannot target risk controls, permissions or live trading | Tested | CI run #6 |
| EVOLVE-004 | Isolated artifact workspace | Per-experiment folders; path traversal blocked; artifacts are not executable | Designed | Implementation introduced in this change; awaiting CI |
| GOV-001 | Requirements register | SQLite-backed lifecycle; transitions require evidence; records survive restart | Designed | Implementation introduced in this change; awaiting CI |
| CI-001 | Continuous integration | Push to main runs Python tests and reports a successful job | Verified | GitHub Actions run #6, commit `1b3b77f` |

## Scope and safety notes

- "Tested" means automated tests passed; it does not mean production approval.
- "Verified" is reserved for evidence that validates the full requirement, not just that code exists.
- The experiment workspace is **artifact storage only**. It does not run user code, scripts,
  notebooks, strategies, plugins or shell commands. It has no network or broker connection.
- SQLite files are local plaintext databases in this phase. Do not store passwords, API keys,
  broker tokens, or other secrets in them. OS-level access controls, encryption and backup
  procedures remain future work.
- Real-money trading is out of scope. No live broker execution is implemented.
