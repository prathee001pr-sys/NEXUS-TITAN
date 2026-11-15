# Pre-public security remediation — 7 November 2026

Base: `4a52b5213b6781ba62aaf43725887becabe2e0b0` (Stage94 development).
This patch adds CI security controls. It does not authorize release, merging,
strategy promotion, broker connectivity or live trading.

## Diagnosis and changes

| Audit issue | Remediation in this change |
| --- | --- |
| Mutable Actions tags | All Actions in the four current workflow files use full commit SHAs, resolved from the official upstream version refs on 7 November 2026. |
| Persisted checkout token | Every checkout sets `persist-credentials: false`; workflow permissions remain `contents: read`. |
| No repository secret-scan workflow | A push/PR/manual Gitleaks 8.30.1 job fetches complete branch history and scans all fetched refs, including merge diffs. Its release archive has a fixed, verified SHA-256. Output is redacted; detection exits unsuccessfully. |
| Generic detector false positives | The generic rule remains enabled. Exceptions require both an exact relative path and a complete anchored line for eight reviewed synthetic IDs/HMAC expressions. No test directory, commit or provider rule is excluded. |
| Accidental local state commits | Ignore environment variants, SQLite databases/sidecars and private-key files; retain `.env.example`. Ignore rules do not erase already committed files. |
| Frozen historical workflow comparison | Retain all four original PR5 blob IDs. Report three unchanged calibration files and the exact reviewed CI successor separately. Arbitrary drift still raises an error. |

The reviewed calibration workflow changes only checkout/setup-python references
and checkout credential persistence. Its Git blob is
`c376a11142c1b5f00b6cbeb489e9a577beb77f00`; the original remains recorded as
`46d1d7c95c89a1bc409fd2c00ab51bbea27ff956`. A regression independently reverses
only these edits and verifies the original blob. Other regressions reject
write permissions, persisted credentials and removal of the pytest command.

## Validation

- Full offline validation: 2,482 tests, plus 5 passing subtests, using Python 3.12.
- All 25 existing CI report/smoke commands pass locally.
- Actionlint 1.7.12 validates all four workflows; YAML/TOML and bash syntax pass.
- Gitleaks history scan over the audit mirror: 721 patch-bearing commits,
  including merge diffs, approximately 12.03 MB; no remaining findings with
  the reviewed configuration. The mirror has 723 reachable commits.
- Five temporary detector checks pass: reviewed synthetic code is accepted;
  a provider token and generic replacement in the same file are rejected;
  appending a generic secret to an allowed line is rejected; the same
  reviewed expression in another path still requires review. No canary
  credential is committed.

For a local scan, install the official checksum-verified Gitleaks 8.30.1 binary
and run from the repository root:

```sh
gitleaks git . --config .gitleaks.toml \
  --log-opts='--all --full-history -m' \
  --ignore-gitleaks-allow --redact=100 --timeout=300
```

The workflow scans fetched history; deleted/unadvertised refs, external forks,
hosted Actions logs and external datasets are outside that coverage.

## Account and publication decisions still required

The pre-change GitHub Actions failure is an account-level runner admission
failure. Check-run annotations for jobs `127086344895` and `127086345061` state
that recent payments failed or the spending limit must be increased. These
jobs did not run tests. Code changes cannot clear an account billing hold;
the account owner must review **Settings → Billing & plans**. No payment or
spending-limit change is included here. A fresh run must be inspected after
the patch is published; historical failed checks are not current execution
proof.

Personal name/Gmail metadata exists in old commits. This patch does not
rewrite or remove it. The owner can enable private GitHub commit email and
use the account's GitHub noreply address for future local commits. Removing
old metadata requires a separately approved history rewrite, coordinated
branch/PR updates and review of retained references. Merely deleting files
or changing a future Git author setting does not erase historical metadata.

The repository was public at diagnosis. Its strategy implementation and
architecture are visible source; confidentiality is an owner decision. No
visibility change, strategy deletion or history force-push is part of this
patch. Existing branches retain their historical workflows until the change
is deliberately integrated into them. This patch is not a public-release
or production-security certificate.
