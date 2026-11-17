# PWA offline snapshot bridge — research-only review candidate

Status: **not integrated into the deployed Android PWA**. Parent is PR #151,
commit `5d21e476cbe1a6d6bca4d22cf8c755a114a728a7` (3-version Python CI
and full-history Secret Scan passed).

## Implementation

`dashboard.private_snapshot_store` stores the existing Stage151 bounded
Indian F&O/Crypto display-only JSON packet to a fixed filename,
`pwa-research-status.json`, **inside a pre-existing private local directory**
that must be owned by the operating-system user and have mode `0700`.

The candidate performs Linux/POSIX no-follow directory/file-descriptor
opening, refuses symlink snapshots and unsafe file permissions, writes
`0600` temporary files, fsyncs them, then uses same-directory atomic
replacement. It refuses an unsafe existing snapshot. Loading is strict:
bounded 4096 bytes, regular inode and ownership/permission checks,
duplicate JSON key rejection, canonical JSON requirement, the Stage151
digest/market shape/NO-GO validator, and before/after descriptor identity
checks. A failed rename leaves the earlier valid file untouched.

The store does NOT create an HTTP endpoint, owner account, cookie/session,
OAuth provider, trusted GitHub evidence, automatic updates, website or PWA
service worker. The packet SHA-256 is **not authenticated**, so an attacker
with the same OS identity or control over the keyless producer may forge
display packets. The `0700` directory mode is a local-file guard, NOT
proof of a private deployed cloud system. The output must never be served
publicly by a web server or placed under a public static-files directory.

## Acceptance required

- Strict unit tests must show 0600/0700 permission enforcement, no-follow
  symlink denial, existing file protection, duplicate-key rejection, forged
  owner/live permissions rejection (even when a digest is recomputed),
  stable JSON round-trip, oversize rejection and atomic rename recovery.
- Run Stage151 PWA/SQLite lifecycle, Stage145/148 readiness, Stage147/148
  Crypto risk, Stage142 actual crash tests and full repo regression without
  skipping or suppressing warnings.
- Publish through noreply Git CLI to a separate Draft PR after tests pass;
  independently verify exact-head Python 3.11/3.12/3.13 GitHub CI and
  full-history Secret Scan.

## Production blocking evidence

Issue #135 stays OPEN. To connect the user-installed private Android PWA,
obtain the actual PWA project/deployment, apply real owner authentication to
a protected backend, prevent anonymous/direct-link access, establish
authenticated source provenance and reliable no-secret status delivery, and
test UI rendering, persistence and backup/restore end to end.

Always preserve `main`, independent Risk & Veto NO-GO, no real-market data
claims, no autonomous order submission and disabled live trading.
