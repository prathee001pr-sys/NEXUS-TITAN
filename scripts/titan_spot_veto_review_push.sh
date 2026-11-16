#!/usr/bin/env bash
# NEXUS TITAN: ONLY add verified offline Crypto spot review onto PR #138.
# Never merges main, changes visibility, live trading or production risk policy.
set -euo pipefail
ZIP="${1:?Usage: bash titan_spot_veto_review_push.sh /path/to/verified.zip}"
REPO="prathee001pr-sys/NEXUS-TITAN"
ROOT="$HOME/workspace/nexus-titan-github"
PARENT="298ffe060db3e15a7b215d444866aefffa2a79cb"
BRANCH="feature/crypto-spot-independent-review-2026-11-16"
BASE="feature/crypto-recovery-acceptance-candidate-2026-11-15"
cd "$ROOT"
gh auth status -h github.com >/dev/null
[ -z "$(git status --porcelain)" ] || { echo 'STOP: checkout has existing changes'; exit 2; }
origin="$(git remote get-url origin)"
case "$origin" in
  https://github.com/$REPO|https://github.com/$REPO.git|git@github.com:$REPO|git@github.com:$REPO.git) ;;
  *) echo "STOP: unexpected origin repository"; exit 2;;
esac
# No force/merge: fetch only the previously created review branch.
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' fetch --no-tags origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  git switch "$BRANCH"
else
  git switch --track "origin/$BRANCH"
fi
[ "$(git rev-parse HEAD)" = "$PARENT" ] || { echo 'STOP: feature branch has unexpected head'; exit 2; }
[ "$(git rev-parse refs/remotes/origin/$BRANCH)" = "$PARENT" ] || { echo 'STOP: remote branch advanced'; exit 2; }
[ "$(git hash-object src/nexus_titan/operations/stage97_crypto_paper.py)" = '0c1600848c8095e05581531e4e04f3acc7265bd7' ] || { echo 'STOP: Stage97 source changed'; exit 2; }
[ "$(git hash-object src/nexus_titan/operations/crypto_spot_research_gate.py)" = '87db9e08bce476349e4c0a809d97f2a8d1fe4bc3' ] || { echo 'STOP: Stage97 gate changed'; exit 2; }
# Strict archive member allowlist and SHA-256 manifest; no symlinks/unsafe extraction.
python - "$ZIP" "$ROOT" <<'PY'
import hashlib, pathlib, sys, zipfile
archive=pathlib.Path(sys.argv[1]).resolve()
root=pathlib.Path(sys.argv[2]).resolve()
allowed=[
 'src/nexus_titan/operations/crypto_spot_independent_review.py',
 'tests/test_crypto_spot_independent_review.py',
 'docs/CRYPTO_SPOT_INDEPENDENT_REVIEW_2026-11-16.md',
 'scripts/titan_spot_veto_review_push.sh',
]
with zipfile.ZipFile(archive) as z:
 names=z.namelist()
 if len(names)!=len(allowed)+1 or set(names)!=set(allowed)|{'SHA256SUMS.txt'}:
  raise SystemExit('STOP: unexpected archive paths')
 manifest={}
 for line in z.read('SHA256SUMS.txt').decode('ascii').splitlines():
  digest,name=line.split('  ',1)
  if name in manifest or name not in allowed or len(digest)!=64:
   raise SystemExit('STOP: invalid file manifest')
  manifest[name]=digest
 if set(manifest)!=set(allowed):raise SystemExit('STOP: incomplete manifest')
 for name in allowed:
  info=z.getinfo(name)
  if info.is_dir() or ((info.external_attr>>16)&0o170000)==0o120000:
   raise SystemExit('STOP: bad archive member')
  content=z.read(name)
  if hashlib.sha256(content).hexdigest()!=manifest[name]:
   raise SystemExit('STOP: file checksum mismatch')
  dest=(root/name).resolve()
  if not dest.is_relative_to(root) or dest.exists():
   raise SystemExit('STOP: file already exists or unsafe destination')
 for name in allowed:
  dest=root/name
  dest.parent.mkdir(parents=True,exist_ok=True)
  dest.write_bytes(z.read(name))
print('Exactly four audited files staged into isolated review branch')
PY
if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
PYTHONPATH=src "$PY" -m compileall -q src/nexus_titan/operations/crypto_spot_independent_review.py tests/test_crypto_spot_independent_review.py
PYTHONPATH=src "$PY" -m pytest -q -o addopts='' -W error \
 tests/test_crypto_spot_independent_review.py \
 tests/test_crypto_spot_real_stage97_integration.py \
 tests/test_crypto_research_preflight.py \
 tests/test_stage97_crypto_paper.py tests/test_stage98_dual_market_review.py \
 tests/test_stage121_research_supervisor.py tests/test_stage121_startup_hardening.py \
 tests/test_stage123_recovery_fault_lab.py tests/test_recovery_repeatability_audit.py \
 tests/test_stage211_215_batch.py
files=("src/nexus_titan/operations/crypto_spot_independent_review.py" \
       "tests/test_crypto_spot_independent_review.py" \
       "docs/CRYPTO_SPOT_INDEPENDENT_REVIEW_2026-11-16.md" \
       "scripts/titan_spot_veto_review_push.sh")
git add -- "${files[@]}"
git diff --cached --check
uid="$(gh api user --jq '.id')"
login="$(gh api user --jq '.login')"
[[ "$uid" =~ ^[0-9]+$ && "$login" =~ ^[A-Za-z0-9-]+$ ]] || { echo 'STOP: GitHub identity invalid'; exit 2; }
email="${uid}+${login}@users.noreply.github.com"
GIT_AUTHOR_NAME='NEXUS TITAN Research' GIT_COMMITTER_NAME='NEXUS TITAN Research' \
GIT_AUTHOR_EMAIL="$email" GIT_COMMITTER_EMAIL="$email" \
  git -c user.name='NEXUS TITAN Research' -c user.email="$email" commit -m 'Research: independent tighter synthetic BTC spot risk review, no execution'
[ "$(git log -1 --format=%ae)" = "$email" ] && [ "$(git log -1 --format=%ce)" = "$email" ] || { echo 'STOP: unsafe author metadata'; exit 2; }
git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push -u origin "$BRANCH"
echo "PUSH SUCCESS: $(git rev-parse HEAD) — main unchanged"
if gh pr view "$BRANCH" --json url --jq '.url' >/dev/null 2>&1; then
  gh pr view "$BRANCH" --json url --jq '.url'
else
  gh pr create --draft --base "$BASE" --head "$BRANCH" \
  --title 'Research: independent tighter synthetic Crypto spot risk review (no live)' \
  --body 'Additive no-permit/no-execution Stage97 read-only review, with stricter bounded risk policy, fail-closed source and journal checks. Focused strict tests pass. Stacked on Draft PR #138, no main merge, no live trading. Real-market and authenticated operator/gateway acceptance remain blocked.' \
  || echo 'Push is complete; Draft PR creation needs manual GitHub review.'
fi
