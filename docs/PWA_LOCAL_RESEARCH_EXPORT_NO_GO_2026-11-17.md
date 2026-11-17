# PWA local research-status export — test-only integration prerequisite
Date: 2026-11-17
Disposition: **PWA/backend production integration still NO-GO**.

## Existing assets
- This GitHub tree has local `DashboardBackendService`, Stage145
  `DashboardResearchStatus`, and Stage148 `ReadinessReport`.
- The separately installed owner-only Android PWA is **not** part of
  this review branch, and there is NO evidence of this module being wired to
  the deployed PWA, authenticated GitHub, or a network endpoint.

## Additive contract
`src/nexus_titan/dashboard/pwa_research_export.py` takes exactly two typed,
validated Stage145 local research statuses (Indian F&O and Crypto). It
rechecks Stage148's prohibition of live authorization and automatic strategy
promotion, then returns a canonical JSON-safe, deterministic, bounded packet
with redacted fixed no-go gaps, two market-specific research labels, explicit
unverified owner/GitHub/global risk/data flags, and a SHA-256 integrity digest.

No source account IDs, user-supplied reason strings, order handles, trading
permits, personal access tokens, raw P&L or arbitrary links are serialized.
The digest is **not** signed; anyone able to edit JSON can recompute it.
A validator checks exact schema, booleans and packet digest, but does not
authenticate a user, source commit, independent reviewer or website session.

## Security non-goals
- No web server, public route, CORS permission, GitHub token storage, cookie,
  PWA file modification, owner login, authentication or deployed backend.
- Never emit privileged actions or treat local research eligibility as
  production/paper order authority.
- Do NOT treat this artifact as evidence that Stage135 is completed.

## Acceptance
- Validate both market rows, bounded JSON serialization, consistent
  human-review semantics, untrusted reason redaction, tampering, forged
  green flags and unsigned/rehashed privilege injection.
- Full Python 3.11/3.12/3.13 CI and full-history Secret Scan on the new
  feature branch; `main` stays unmerged.
- To close Stage135 in future, identify the existing PWA deployment and
  perform real owner-auth, anonymous/deep URL rejection, trusted GitHub
  job-evidence retrieval, backup/restore and end-to-end UI tests, without
  exposing any trading authority.

## Strict SQLite resource-lifecycle recovery — 2026-11-17

The initial PWA contract batch correctly stopped after `31 passed, 1 failed`
in `local_read_models_strict` under Python 3.13. The failing test was
`test_coordinator_preparing_marker_remains_an_unresolved_alert`, with
`pytest.PytestUnraisableExceptionWarning` caused by an unclosed SQLite
connection. This is **not** evidence of a broker/trading-logic failure.

A static source review found three raw `with sqlite3.connect(...)` blocks in
the Stage50 dashboard tests, one `with self._connect()` in approval-verifier
initialization, and one raw SQLite `with` in read-only existing-account
policy inspection. SQLite's connection context manager only handles
transaction completion, not connection closure.

The narrow corrective patch uses `contextlib.closing` while preserving the
original nested transaction context. It does not relax approval verification,
revocation, paper policies or any execution permission. The new connection
lifecycle regression tests instrument connection closure for successful
approval-verifier initialization and both successful/failed read-only policy
checks. Existing Stage50 alert behavior is preserved and **must still pass
under `-W error`**.

Before publication run strict Stage50/PWA/approval/recovery groups and entire
regression; exact-head GitHub Python 3.11/3.12/3.13 CI and Secret Scan remain
independently required. This does **not** verify an owner-only PWA deployment,
trusted GitHub data origin or production trading rights.
