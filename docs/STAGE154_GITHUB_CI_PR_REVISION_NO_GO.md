# Stage154 — GitHub CI evidence PR-revision stability fence
Date: 2026-11-17
Status: **REVIEW CANDIDATE — tests and GitHub CI not yet executed**.

## Source baseline

Follow Stage153 Draft PR #153 at its fully green Security Scan / Python
3.11–3.13 commit (short SHA `102d25b`).
Continue on a separate feature branch, without merge into `main`.

## Observed defect

The Stage153 backend-only GitHub verifier fetches a Draft PR's head, checks
pinned workflow blobs and GitHub Actions runs, then returns an evidence
receipt. PR heads and base branches are mutable: another author/automation
could push a new head, retarget its base, merge or close the PR *during*
these remote API requests. A green result obtained for a previously checked
head is NOT proof that the PR is still pointing to that head at return time.

## Narrow change

- Require a valid `base.sha` in addition to the existing exact `head.sha`,
  valid branch names and internal repository identity.
- Record the original PR `(head.sha, head.ref, base.sha, base.ref)`.
- Read the same GitHub PR **a second time after all check and workflow-run
  verifications**, and reject if any of those identities or the Draft/open/
  unmerged flags changed.
- Preserve TLS/no redirects, bounded GitHub API responses, workflow file
  SHA pins, per-run path+branch checks, token redaction, exact required
  Python 3.11/3.12/3.13 plus full-history scan, and every NO-GO privilege.
- No new dependencies, credentials, server, PWA frontend or broker hooks.

## Tests

Add parameterized negative cases covering PR head swap, head ref drift,
base SHA/ref retargeting, forked head/base repository, closed/merged/non-Draft
state, changed PR number, incomplete initial base SHA/refs, and a stable
PR check that still produces only a non-production display receipt.

Run strict Stage153/154 verifier and CLI tests, Stage151/152 private PWA,
Stage50/145/148 dashboard, Stage48/49/57 approval, Stage147/148 Crypto,
Stage201–205 Indian F&O, Stage142 actual crash recovery, and full regression.

The eventual new Draft PR must have independently verified exact-head
Python 3.11/3.12/3.13 CI plus full-history Secret Scan and privacy-safe
noreply Git metadata. Do not merge `main` or enable live trading.

## Important limitations

Two GitHub PR reads are a *point-in-time freshness check*, not atomic
locking and not a continuously guaranteed PR state. It does not authenticate
the owner-only Android PWA session; a separately deployed authenticated
backend, signed/managed transport, mandatory independent Risk & Veto,
real data and shadow-market validation are still missing. Keep Issue #135
OPEN and production/live permissions NO-GO.
