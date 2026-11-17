# Indian F&O Source Byte Integrity — Race Hardening (2026-11-17)

**State: candidate pending full repository tests and GitHub review.**

## Threat addressed
Existing Stage203 `audit_fo_source_files` checked `path.is_symlink()`,
`path.stat()`, and then opened a file for hashing, before doing `path.stat()`
again. A locally writable dataset directory could be altered between these
operations, including replacing the checked regular file with a symlink or
another regular file that has identical bytes. The hash alone cannot prove
a stable filename-to-inode relationship.

## Narrow correction
- Use `lstat` on the path (no symlink following) and `os.open` with
  `O_NOFOLLOW`, `O_CLOEXEC` and `O_NONBLOCK` where available.
- On platforms without no-follow support, **fail closed** rather than
  trusting a race-prone open.
- Validate that the opened descriptor references the same regular inode as
  the previously checked pathname.
- SHA-256 hash bytes only through that opened descriptor; compare descriptor
  size, mtime, ctime and inode at the end, then `lstat` the final pathname and
  verify its identity and metadata again. Reject a replaced, symlinked,
  altered or unstable file.
- Preserve existing immutable hash receipts, manifest linkage, bounded
  file sizes, duplicate rejection, live trading disabled and original
  Stage201–205 manual intake contract.

## Negative acceptance
- Symlink injected at exact `os.open` boundary must fail without computing
  an accepted source receipt.
- Original inode renamed immediately after descriptor open and filename
  restored using **identical bytes** must still fail by inode mismatch.
- Unchanged ordinary CSV still passes internal manual structural hashing.
- Run focused strict `-W error` Stage201–205, F&O integration, Stage148 Crypto
  and Stage142 real recovery tests, then full regression.
- New-head GitHub 3.11/3.12/3.13 CI, Secret Scan and Draft PR required.

**NO-GO:** This does not establish official NSE or licensed vendor provenance,
proper exchange calendar, market depth, contract margins/fees, real-market
performance, independently authenticated operator identity or any broker
execution permissions. Production and live trading remain disabled.
