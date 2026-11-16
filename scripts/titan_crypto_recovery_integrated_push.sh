#!/usr/bin/env bash
# Publish only the verified synthetic Crypto research / recovery test candidate.
# Authenticated GitHub CLI required; no generated API commits, no main merge.
set -euo pipefail

ZIP="${1:?Pass the verified ZIP path}"
WORKSPACE="${HOME}/workspace/nexus-titan-github"
BRANCH="feature/crypto-recovery-acceptance-candidate-2026-11-15"
PARENT="1994d8cd4822a4d45d8c4f6760fdb976e8cbd58a"
NOREPLY="348311312+prathee001pr-sys@users.noreply.github.com"
TEST97="cf21f2adad99421280a81527a01219abaa28d85d"
TEST98="45e5efa13acd9b0a0f2e042e86541c4e80813b87"

[[ -f "$ZIP" && -d "$WORKSPACE/.git" ]] || { echo "STOP: ZIP or existing repository not found"; exit 2; }
cd "$WORKSPACE"
gh auth status -h github.com >/dev/null

# Verify every archive member and SHA; do not extract untrusted paths wholesale.
python - "$ZIP" <<'PY'
from pathlib import Path
import hashlib, stat, sys, zipfile
zpath=Path(sys.argv[1]); allowed={
 'src/nexus_titan/operations/crypto_research_preflight.py',
 'src/nexus_titan/operations/crypto_spot_research_gate.py',
 'scripts/run_recovery_repeatability_audit.py',
 'tests/test_crypto_research_preflight.py',
 'tests/test_crypto_spot_real_stage97_integration.py',
 'tests/test_recovery_repeatability_audit.py',
 'tests/test_stage97_crypto_paper.py',
 'tests/test_stage98_dual_market_review.py',
 'docs/ACCEPTANCE_CANDIDATE_CRYPTO_RECOVERY_2026-11-15.md',
 'docs/CRYPTO_STAGE97_REAL_INTEGRATION_RECEIPT_2026-11-15.md',
 'scripts/titan_crypto_recovery_integrated_push.sh',
}
with zipfile.ZipFile(zpath) as z:
    members=z.infolist()
    names=[i.filename for i in members]
    if len(names)!=len(set(names)) or set(names)!=allowed|{'SHA256SUMS.txt'}:
        raise SystemExit('STOP: ZIP contents not the exact expected allowlist')
    if z.testzip() is not None:raise SystemExit('STOP: ZIP CRC mismatch')
    for i in members:
        if i.is_dir() or i.file_size>100000 or stat.S_ISLNK(i.external_attr>>16):
            raise SystemExit('STOP: unexpected archive entry type/size')
    expected={}
    for line in z.read('SHA256SUMS.txt').decode().splitlines():
        sha,path=line.split('  ',1)
        if path in expected or path not in allowed or len(sha)!=64:
            raise SystemExit('STOP: invalid hash manifest')
        expected[path]=sha
    if set(expected)!=allowed:raise SystemExit('STOP: missing manifest item')
    for path in allowed:
        if hashlib.sha256(z.read(path)).hexdigest()!=expected[path]:
            raise SystemExit('STOP: ZIP member SHA mismatch: '+path)
print('ZIP allowlist, CRC and SHA256 checks passed.')
PY

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "STOP: existing tracked changes; preserve/review before switching";exit 3
fi
actual_origin="$(git remote get-url origin)"
case "$actual_origin" in
  https://github.com/prathee001pr-sys/NEXUS-TITAN|https://github.com/prathee001pr-sys/NEXUS-TITAN.git|git@github.com:prathee001pr-sys/NEXUS-TITAN.git) ;;
  *) echo "STOP: incorrect origin"; exit 3;;
esac

GITC=(git -c credential.helper= -c 'credential.helper=!gh auth git-credential')
"${GITC[@]}" fetch --no-tags origin "refs/heads/${BRANCH}"
[[ "$(git rev-parse FETCH_HEAD)" == "$PARENT" ]] || { echo "STOP: remote candidate changed; do not overwrite"; exit 3; }
if git show-ref --verify --quiet "refs/heads/${BRANCH}"; then
  git switch "$BRANCH"
  [[ "$(git rev-parse HEAD)" == "$PARENT" ]] || { echo "STOP: local candidate contains different work"; exit 3; }
else
  git switch -c "$BRANCH" "$PARENT"
fi
[[ "$(git hash-object tests/test_stage97_crypto_paper.py)" == "$TEST97" ]] || { echo "STOP: unexpected Stage97 test version"; exit 3; }
[[ "$(git hash-object tests/test_stage98_dual_market_review.py)" == "$TEST98" ]] || { echo "STOP: unexpected Stage98 test version"; exit 3; }

# All new paths must be absent (including untracked user files).
NEW=(
  src/nexus_titan/operations/crypto_research_preflight.py
  src/nexus_titan/operations/crypto_spot_research_gate.py
  scripts/run_recovery_repeatability_audit.py
  tests/test_crypto_research_preflight.py
  tests/test_crypto_spot_real_stage97_integration.py
  tests/test_recovery_repeatability_audit.py
  docs/ACCEPTANCE_CANDIDATE_CRYPTO_RECOVERY_2026-11-15.md
  docs/CRYPTO_STAGE97_REAL_INTEGRATION_RECEIPT_2026-11-15.md
  scripts/titan_crypto_recovery_integrated_push.sh
)
for path in "${NEW[@]}"; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "STOP: new-path collision: $path"; exit 3; }
done

python - "$ZIP" <<'PY'
from pathlib import Path
import sys, zipfile
z=zipfile.ZipFile(sys.argv[1]); repo=Path.cwd()
for name in z.namelist():
    if name=='SHA256SUMS.txt':continue
    p=repo/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(z.read(name))
print('Installed only explicitly approved candidate files.')
PY

PYBIN="python"
[[ -x .venv/bin/python ]] && PYBIN=".venv/bin/python"
PYTHONPATH=src "$PYBIN" -m compileall -q src/nexus_titan/operations/crypto_spot_research_gate.py tests/test_crypto_spot_real_stage97_integration.py
PYTHONPATH=src "$PYBIN" -m pytest -q -o addopts='' -W error \
  tests/test_crypto_research_preflight.py \
  tests/test_crypto_spot_real_stage97_integration.py \
  tests/test_recovery_repeatability_audit.py \
  tests/test_stage97_crypto_paper.py \
  tests/test_stage98_dual_market_review.py \
  tests/test_trading_intelligence_pipeline.py \
  tests/test_stage121_research_supervisor.py \
  tests/test_stage121_startup_hardening.py \
  tests/test_stage123_recovery_fault_lab.py

mapfile -t FILES < <(python - "$ZIP" <<'PY'
import sys,zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    print('\n'.join(sorted(n for n in z.namelist() if n!='SHA256SUMS.txt')))
PY
)
git add -- "${FILES[@]}"
git diff --cached --check
GIT_AUTHOR_NAME="NEXUS TITAN Research" GIT_AUTHOR_EMAIL="$NOREPLY" \
GIT_COMMITTER_NAME="NEXUS TITAN Research" GIT_COMMITTER_EMAIL="$NOREPLY" \
  git -c user.name="NEXUS TITAN Research" -c user.email="$NOREPLY" \
  commit -m "Research: integrate synthetic BTC spot Stage97 gate and recovery audit"
[[ "$(git log -1 --format=%ae)" == "$NOREPLY" && "$(git log -1 --format=%ce)" == "$NOREPLY" ]] || {
 echo 'STOP: commit email identity mismatch; not pushing'; exit 4;
}
"${GITC[@]}" push origin "HEAD:refs/heads/${BRANCH}"
echo "PUSH SUCCESS: privacy-safe feature branch only $(git rev-parse HEAD). Main unchanged."

# Non-fatal Draft PR attempt: a failed PR creation never changes successful push.
if gh pr view "$BRANCH" --json number >/dev/null 2>&1; then
  echo "Existing PR found; verify checks and keep it Draft."
else
  gh pr create --draft --base feature/stable-research-baseline-premerge-2026-11-15 \
    --head "$BRANCH" \
    --title "Research candidate: Stage97 crypto spot integration & recovery repeatability" \
    --body "Research-only synthetic candidate: real typed Stage97 spot preflight, independent local signed test-permit boundary, 23 integrated tests, recovery repeatability helper, two SQLite test-cleanup fixes. Local strict focused 156 passed; GitHub final-head CI and Secret Scan are mandatory. No live trading, main merge, public PWA deployment, risk-permission change or Rust migration. #131 #134 #135" || \
    echo "PR creation unavailable; branch is pushed; ask ChatGPT to create the stacked Draft PR."
fi
