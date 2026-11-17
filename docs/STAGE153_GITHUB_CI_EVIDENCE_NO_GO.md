# Stage153 — Server-side GitHub PR/CI evidence verifier
Date: 2026-11-17

Disposition: **research-readiness visibility only; NOT deployed owner PWA auth or trading authority**.

## Parent and scope

Source is anchored to the GitHub-verified Stage152 Draft PR #152 commit
`889e9c251cebfc255c4bec9c4408a66a6c314cdd`.
Add only a read-only trusted GitHub API verifier, a backend-only CLI, mocked
negative tests and this review note. No PWA frontend changes or HTTP endpoint.

## Why previous evidence was incomplete

The Stage151/152 PWA export/snapshot protects **local display data**, but
SHA-256 on unsigned JSON and a caller-supplied green CI label do not prove
that a specific GitHub PR actually passed independent CI. The existing
owner-only Android PWA is a separate product whose app/deployment has not
been inspected here.

## Verified-only design

`dashboard.github_ci_evidence.verify_github_draft_pr_ci` requires:
1. A trusted **server-side** GitHub token, an exact lowercase 40-digit head
   Git SHA and a bounded integer PR number.
2. Fixed `https://api.github.com` host; HTTPS certificate checking,
   no redirects, bounded HTTP response, 12-second per-request timeout,
   duplicate JSON key rejection and sanitized failure messages.
3. An **open Draft PR** in the exact `prathee001pr-sys/NEXUS-TITAN`
   repository with matching `head.sha`, head and base repository identity
   and no merge.
4. Exact branch-head content pinning of the previously reviewed workflow
   files, preventing branch-authored empty success workflows:
   - `.github/workflows/ci.yml` Git blob
     `72233c01d390f62238bd723d4eb7a80c6547955e`
   - `.github/workflows/secret-scan.yml` Git blob
     `6257dfd768f1d12c768982350c340568ad51c0d9`
5. GitHub Actions check-run results at that SHA, with **all** returned
   checks completed/success from the `github-actions` provider, no
   incomplete pagination, and the exact four required job names:
   Python 3.11/3.12/3.13 offline-validation and full-history scan.
6. Every green check must link to a GitHub Actions workflow run from an
   allowed GitHub job URL; that run must have the correct repo, head branch,
   exact commit, workflow filename, trusted workflow name, event and
   completed/success status. A renamed or extra fake workflow is rejected.

Only a DISPLAY-ONLY local `GitHubPRCIEvidence` object is returned with
`production_ready=False`, `owner_pwa_session_authenticated=False`,
`global_independent_risk_veto_verified=False` and
`live_trading_authorized=False`. This is a *point-in-time* check; callers
must requery GitHub when the branch/PR changes. Object/dataclass or JSON
serialization is not a cryptographic attestation and must not be accepted
back from untrusted client input.

## Backend-only CLI

`scripts/verify_pwa_github_ci_evidence.py` reads
`TITAN_GITHUB_READ_TOKEN` **from its environment in a trusted backend**,
never from user-submitted PWA payloads, and prints only redacted research
evidence JSON. It returns 2 on incomplete/unverified evidence and cannot
print a token, HTTP response body or private exception message. Use only
a least-privileged GitHub credential from a server-side secret manager;
never store the token in source, static PWA bundles, screenshots or logs.

## Tests and constraints

The focused test suite mocks the Github HTTPS API and checks exact source,
branch/repo identity, bad/redirected hosts, forged workflow jobs, failed or
pending checks, wrong workflow content hashes, check-run pagination,
duplicate check names, credential redaction and safe CLI failure.
Run strict `-W error` targeted tests, Stage151/152 snapshot tests, Stage147/148
crypto risk, Stage142 true crash, Stage201–205 F&O tests, full regression,
new-head Python 3.11/3.12/3.13 CI and full-history Secret Scan.

**NO-GO, still separate tasks:** independently authenticated owner PWA
sessions/route access, trusted server deployment, verified account identity,
encrypted backups, actual bidirectional PWA wiring, licensed F&O data and
prospective shadow trading, global mandatory independent Risk & Veto and
approval for live execution. Do not close Issue #135 or #134 on these tests.
Do not merge `main`, create live exchange routes or grant production flags.
