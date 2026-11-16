#!/usr/bin/env bash
# Verified feature-only publication. Never merges main or enables trading.
set -euo pipefail
ZIP="${1:?Provide verified ZIP path as first argument}"
REPO="prathee001pr-sys/NEXUS-TITAN"
ROOT="${HOME}/workspace/nexus-titan-github"
BRANCH="feature/crypto-reviewed-paper-gateway-2026-11-16"
PARENT="da50b5e9a9375ff1c36e3bcaa73f2b36a3ef50fd"
BASE="feature/crypto-spot-independent-review-2026-11-16"

cd "$ROOT"
gh auth status -h github.com >/dev/null
python - "$ZIP" <<'PY'
import sys,zipfile,hashlib,stat
from pathlib import PurePosixPath
from pathlib import Path
zp=Path(sys.argv[1])
allow={
 'src/nexus_titan/operations/crypto_spot_reviewed_paper.py',
 'tests/test_crypto_spot_reviewed_paper.py',
 'docs/CRYPTO_REVIEWED_PAPER_GATEWAY_2026-11-16.md',
 'scripts/titan_crypto_reviewed_paper_push.sh',
 'SHA256SUMS.txt',
}
with zipfile.ZipFile(zp) as z:
 files=[i for i in z.infolist() if not i.is_dir()]
 assert {i.filename for i in files} == allow, 'Unexpected ZIP contents'
 for i in files:
  p=PurePosixPath(i.filename)
  assert not p.is_absolute() and '..' not in p.parts, 'Path traversal'
  assert (i.external_attr >>16)&0o170000!=0o120000, 'Symlink'
 manifest=z.read('SHA256SUMS.txt').decode().splitlines()
 expected={}
 for line in manifest:
  digest,filename=line.split('  ',1)
  assert filename in allow and filename!='SHA256SUMS.txt'
  assert filename not in expected and len(digest)==64
  expected[filename]=digest
 assert set(expected)==allow-{'SHA256SUMS.txt'}
 for filename,digest in expected.items():
  assert hashlib.sha256(z.read(filename)).hexdigest()==digest, filename+' bad SHA'
print('VALIDATED: explicit candidate allowlist and per-file SHA256 checks')
PY

test -z "$(git status --porcelain --untracked-files=no)" || { echo 'STOP: tracked worktree not clean'; exit 1; }
remote="$(git remote get-url origin)"
case "$remote" in
  "https://github.com/$REPO"|"https://github.com/$REPO.git"|"git@github.com:$REPO"|"git@github.com:$REPO.git") ;;
  *) echo "STOP: unexpected GitHub remote"; exit 1;;
esac
git fetch origin "$BRANCH" "$BASE"
# Existing branch is only safe when it is exactly its originally audited parent.
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git switch "$BRANCH"
else
  git switch -c "$BRANCH" --track "origin/$BRANCH"
fi
test "$(git rev-parse HEAD)" = "$PARENT" || { echo 'STOP: unexpected branch head'; exit 1; }
test "$(git rev-parse "origin/$BASE")" = "$PARENT" || { echo 'STOP: parent PR changed'; exit 1; }
for spec in \
 'src/nexus_titan/operations/stage97_crypto_paper.py:0c1600848c8095e05581531e4e04f3acc7265bd7' \
 'src/nexus_titan/operations/crypto_spot_research_gate.py:87db9e08bce476349e4c0a809d97f2a8d1fe4bc3' \
 'src/nexus_titan/operations/crypto_spot_independent_review.py:89c06bc373184c8ce24280ae33170d8a979f0358'; do
 p="${spec%%:*}"; sha="${spec#*:}"
 test "$(git hash-object "$p")" = "$sha" || { echo "STOP: upstream changed at $p"; exit 1; }
done

python - "$ZIP" <<'PY'
from pathlib import Path
import sys,zipfile
root=Path('.').resolve()
with zipfile.ZipFile(sys.argv[1]) as z:
  for name in (
   'src/nexus_titan/operations/crypto_spot_reviewed_paper.py',
   'tests/test_crypto_spot_reviewed_paper.py',
   'docs/CRYPTO_REVIEWED_PAPER_GATEWAY_2026-11-16.md',
   'scripts/titan_crypto_reviewed_paper_push.sh',
  ):
    dst=root/name
    if dst.exists(): raise SystemExit(f'STOP: destination already exists {name}')
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_bytes(z.read(name))
print('INSTALLED: 4 explicitly reviewed additive files')
PY

if [ -x ".venv/bin/python" ]; then PY=".venv/bin/python"; else PY="python"; fi
PYTHONPATH=src "$PY" -m compileall -q src/nexus_titan/operations/crypto_spot_reviewed_paper.py tests/test_crypto_spot_reviewed_paper.py
PYTHONPATH=src "$PY" -m pytest -q -o addopts='' -W error \
 tests/test_crypto_spot_reviewed_paper.py \
 tests/test_crypto_spot_independent_review.py \
 tests/test_crypto_spot_real_stage97_integration.py \
 tests/test_crypto_research_preflight.py \
 tests/test_stage97_crypto_paper.py \
 tests/test_stage98_dual_market_review.py \
 tests/test_recovery_repeatability_audit.py \
 tests/test_stage121_research_supervisor.py \
 tests/test_stage121_startup_hardening.py \
 tests/test_stage123_recovery_fault_lab.py \
 tests/test_stage211_215_batch.py

git add -- \
 src/nexus_titan/operations/crypto_spot_reviewed_paper.py \
 tests/test_crypto_spot_reviewed_paper.py \
 docs/CRYPTO_REVIEWED_PAPER_GATEWAY_2026-11-16.md \
 scripts/titan_crypto_reviewed_paper_push.sh
git diff --cached --check
login="$(gh api user --jq .login)"
uid="$(gh api user --jq .id)"
case "$login" in *[!a-zA-Z0-9-]*|"") echo 'STOP: bad GitHub identity'; exit 1;; esac
case "$uid" in *[!0-9]*|"") echo 'STOP: bad GitHub user id'; exit 1;; esac
noreply="${uid}+${login}@users.noreply.github.com"
git -c user.name='NEXUS TITAN Research' -c user.email="$noreply" \
  -c commit.gpgsign=false commit -m 'Research: reviewed Stage97 synthetic paper route, no live order'
newsha="$(git rev-parse HEAD)"
test "$(git rev-parse HEAD^)" = "$PARENT" || { echo 'STOP: commit parent mismatch'; exit 1; }
test "$(git show -s --format='%ae|%ce' HEAD)" = "$noreply|$noreply" || { echo 'STOP: unsafe commit identity'; exit 1; }
git -c credential.helper= -c credential.helper='!gh auth git-credential' push -u origin "$BRANCH"
echo "PUSH SUCCESS: $newsha (feature only; main untouched)"
if ! gh pr view "$BRANCH" --repo "$REPO" --json number --jq .number >/dev/null 2>&1; then
 gh pr create --repo "$REPO" --draft --base "$BASE" --head "$BRANCH" \
   --title 'Research: reviewed Stage97 synthetic paper gateway (not globally mandatory)' \
   --body 'Additive signed-TEST-permit Stage97 reviewed paper route; 313 targeted strict local tests, no live trading. **Known blocker:** existing direct Stage97 API does not enforce the optional tighter review globally. Keep Draft, issue #134 open and no main merge. All three Python CI versions and Secret Scan require new-head verification.'
else
 echo "Existing PR already found for $BRANCH"
fi
echo 'NEXT: review exact-head CI and full-history Secret Scan; do not merge main.'
