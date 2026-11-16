#!/usr/bin/env bash
# Publish the one audited, fail-closed Stage97 synthetic-paper atomic boundary fix.
# Exact GitHub noreply author+committer; feature branch only; never main.
set -euo pipefail
ZIP="${1:?Provide SHA-256 verified ZIP filepath}"
REPO="$HOME/workspace/nexus-titan-github"
BRANCH='feature/stage97-atomic-permit-hardening-2026-11-16'
PARENT='1c757b636a7e0de68b82c8f668f5fe34727dbef5'
BASE='feature/stage97-execution-surface-nogo-audit-2026-11-16'
REPO_SLUG='prathee001pr-sys/NEXUS-TITAN'

[ -f "$ZIP" ] && [ -d "$REPO/.git" ] || { echo 'ZIP or existing Git repo missing'; exit 2; }
command -v gh >/dev/null && gh auth status -h github.com >/dev/null || { echo 'GitHub CLI not authenticated'; exit 2; }
cd "$REPO"
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo 'Tracked working tree has modifications. Preserve work; aborting.'; exit 3
fi

# Validate every archive entry, its type and every exact file SHA before write.
python - "$ZIP" <<'PYVERIFY'
import sys,zipfile,hashlib,posixpath
z=sys.argv[1]
paths={
 'src/nexus_titan/operations/stage97_crypto_paper.py',
 'src/nexus_titan/diagnostics/stage97_execution_surface.py',
 'tests/test_stage97_execution_surface.py',
 'scripts/run_stage97_execution_surface_audit.py',
 'tests/test_stage97_atomic_permit_boundary.py',
 'docs/STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.md',
 'reports/STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.json',
 'scripts/titan_stage97_atomic_permit_push.sh',
 'README_STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.txt',
}
with zipfile.ZipFile(z) as a:
 names=a.namelist()
 if len(names)!=len(set(names)) or set(names)!=(paths|{'SHA256SUMS.txt'}):
  raise SystemExit('Unsafe or unexpected archive path list')
 for i in a.infolist():
  if i.is_dir() or i.filename.startswith('/') or '..' in i.filename.split('/') or (i.external_attr>>16)&0o170000 == 0o120000:
   raise SystemExit('Unsafe archive entry')
 checks={}
 for row in a.read('SHA256SUMS.txt').decode().strip().splitlines():
  digest,path=row.split('  ',1)
  if len(digest)!=64 or path in checks or path not in paths:
   raise SystemExit('Unexpected SHA row')
  checks[path]=digest
 if set(checks)!=paths:
  raise SystemExit('Incomplete SHA manifest')
 for path in paths:
  if hashlib.sha256(a.read(path)).hexdigest()!=checks[path]:
   raise SystemExit('SHA-256 mismatch: '+path)
print('ZIP allowlist, types and per-file SHA256: VERIFIED')
PYVERIFY

git fetch origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git switch "$BRANCH"
else
  git switch -c "$BRANCH" --track "origin/$BRANCH"
fi
[ "$(git rev-parse HEAD)" = "$PARENT" ] || { echo 'Unexpected branch head, aborting'; exit 3; }
# Exact authoritative pre-patch blobs, measured at GitHub PR #141.
for entry in \
 'src/nexus_titan/operations/stage97_crypto_paper.py:0c1600848c8095e05581531e4e04f3acc7265bd7' \
 'src/nexus_titan/diagnostics/stage97_execution_surface.py:fae41d567ec10c0c6ca3701d35c1aec49eb6275c' \
 'tests/test_stage97_execution_surface.py:96604a838a1b4a9ba72191c65231ea58b0cb23f3' \
 'scripts/run_stage97_execution_surface_audit.py:6438d7703b54981c7077fbd557d0c8d3f6058278'; do
  f="${entry%:*}"; expected="${entry##*:}"
  actual="$(git rev-parse "HEAD:$f")"
  [ "$actual" = "$expected" ] || { echo "Unexpected parent blob: $f"; exit 3; }
done
for newpath in \
 tests/test_stage97_atomic_permit_boundary.py \
 docs/STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.md \
 reports/STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.json \
 scripts/titan_stage97_atomic_permit_push.sh \
 README_STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.txt; do
  [ ! -e "$newpath" ] || { echo "Unexpected existing candidate file: $newpath"; exit 3; }
done

python - "$ZIP" <<'PYINSTALL'
import sys,zipfile,pathlib
root=pathlib.Path.cwd().resolve()
with zipfile.ZipFile(sys.argv[1]) as z:
 for entry in z.namelist():
  if entry=='SHA256SUMS.txt':continue
  dst=root/entry
  dst.parent.mkdir(parents=True,exist_ok=True)
  dst.write_bytes(z.read(entry))
print('Installed exactly nine allowlisted candidate files')
PYINSTALL

# A strict focused safety test. Full regression is delegated to exact-head CI.
PYTHON="$(command -v python3)"
[ -x "$REPO/.venv/bin/python" ] && PYTHON="$REPO/.venv/bin/python"
PYTHONPATH=src "$PYTHON" -m pytest -q -o addopts='' -W error \
 tests/test_stage97_atomic_permit_boundary.py \
 tests/test_stage97_execution_surface.py \
 tests/test_stage97_crypto_paper.py \
 tests/test_crypto_spot_real_stage97_integration.py \
 tests/test_crypto_spot_reviewed_paper.py \
 tests/test_crypto_spot_independent_review.py

[ -z "$(git diff --name-only --diff-filter=D)" ] || { echo 'Unexpected deleted file'; exit 3; }
git add \
 src/nexus_titan/operations/stage97_crypto_paper.py \
 src/nexus_titan/diagnostics/stage97_execution_surface.py \
 tests/test_stage97_execution_surface.py \
 scripts/run_stage97_execution_surface_audit.py \
 tests/test_stage97_atomic_permit_boundary.py \
 docs/STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.md \
 reports/STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.json \
 scripts/titan_stage97_atomic_permit_push.sh \
 README_STAGE97_ATOMIC_PERMIT_HARDENING_2026-11-16.txt
git diff --cached --check
[ "$(git diff --cached --name-only | wc -l | tr -d ' ')" = 9 ] || { echo 'Unexpected staged file count'; exit 3; }
LOGIN="$(gh api user --jq '.login')"
ID="$(gh api user --jq '.id')"
[ -n "$LOGIN" ] && [ -n "$ID" ] || { echo 'Unable to derive noreply identity'; exit 3; }
EMAIL="$ID+$LOGIN@users.noreply.github.com"
GIT_AUTHOR_NAME='NEXUS TITAN Research' GIT_AUTHOR_EMAIL="$EMAIL" \
GIT_COMMITTER_NAME='NEXUS TITAN Research' GIT_COMMITTER_EMAIL="$EMAIL" \
 git -c user.name='NEXUS TITAN Research' -c user.email="$EMAIL" \
 commit -m 'Security: enforce local TEST permit at Stage97 atomic journal boundary'
[ "$(git rev-parse HEAD^)" = "$PARENT" ] || { echo 'Parent changed after commit'; exit 4; }
[ "$(git log -1 --format=%ae)" = "$EMAIL" ] && \
[ "$(git log -1 --format=%ce)" = "$EMAIL" ] || { echo 'Unsafe author/committer email'; exit 4; }
git -c credential.helper= -c credential.helper='!gh auth git-credential' \
 push origin "HEAD:refs/heads/$BRANCH"
echo "PUSH SUCCESS: $(git rev-parse HEAD) (feature branch only, main unchanged)"
if ! gh pr view "$BRANCH" --json url --jq .url; then
 gh pr create --draft --head "$BRANCH" --base "$BASE" \
  --title 'Security: Stage97 atomic signed TEST-permit boundary (research only)' \
  --body 'P1 synthetic-only permit bypass hardening; full reconstructed pytest 4,967 passed + 5 subtests, 4 known warnings. Strictly no live broker, no authenticated human identity, and NO-GO for mandatory all-path stricter Risk & Veto. Previous parent is Draft PR #141. Keep Draft and do not merge main.'
fi
echo 'NEXT: verify exact-head Python 3.11/3.12/3.13 CI and Secret Scan; no main merge.'
