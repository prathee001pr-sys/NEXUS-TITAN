#!/usr/bin/env bash
# Resumable, noreply-privacy-safe, feature-branch-only Stage97 research NO-GO audit.
set -euo pipefail
ZIP="${1:?Usage: bash push.sh <archive.zip>}"
ROOT="$HOME/workspace/nexus-titan-github"
REPO="prathee001pr-sys/NEXUS-TITAN"
BRANCH="feature/stage97-execution-surface-nogo-audit-2026-11-16"
PARENT="626819f3f8b7e6a6e48228651f75a7235aca146d"
EXPECTED_STAGE97="0c1600848c8095e05581531e4e04f3acc7265bd7"
EXPECTED_GATEWAY="43fc5a77e0ca908ba409116634519fbe4046acb3"
if [[ ! -d "$ROOT/.git" ]]; then echo 'BLOCK: exact Replit Git repository missing'; exit 1; fi
cd "$ROOT"
GH_LOGIN="$(gh api user --jq '.login')"
GH_ID="$(gh api user --jq '.id')"
[[ "$GH_LOGIN" == 'prathee001pr-sys' && "$GH_ID" =~ ^[0-9]+$ ]] || { echo 'BLOCK: different GitHub owner'; exit 1; }
[[ "$(git remote get-url origin)" == "https://github.com/$REPO.git" || "$(git remote get-url origin)" == "https://github.com/$REPO" ]] || { echo 'BLOCK: unexpected Git origin'; exit 1; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'BLOCK: tracked working tree is not clean'; exit 1; }
git fetch origin "refs/heads/$BRANCH:refs/remotes/origin/$BRANCH"
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then git switch "$BRANCH"; else git switch -c "$BRANCH" --track "origin/$BRANCH"; fi
[[ "$(git rev-parse HEAD)" == "$PARENT" ]] || { echo 'BLOCK: candidate HEAD is not exact reviewed parent'; exit 1; }
[[ "$(git hash-object src/nexus_titan/operations/stage97_crypto_paper.py)" == "$EXPECTED_STAGE97" ]] || { echo 'BLOCK: Stage97 changed'; exit 1; }
[[ "$(git hash-object src/nexus_titan/operations/crypto_spot_reviewed_paper.py)" == "$EXPECTED_GATEWAY" ]] || { echo 'BLOCK: reviewed gateway changed'; exit 1; }
python - "$ZIP" <<'PYINNER'
import hashlib,stat,sys,zipfile
from pathlib import Path
zpath=Path(sys.argv[1]); dst=Path.cwd()
allowed={
 'src/nexus_titan/diagnostics/stage97_execution_surface.py',
 'tests/test_stage97_execution_surface.py',
 'scripts/run_stage97_execution_surface_audit.py',
 'docs/STAGE97_EXECUTION_SURFACE_NOGO_2026-11-16.md',
 'reports/STAGE97_EXECUTION_SURFACE_NOGO_2026-11-16.json',
 'scripts/titan_stage97_entrypoint_audit_push.sh',
 'README_STAGE97_ENTRYPOINT_AUDIT_2026-11-16.txt',
}
with zipfile.ZipFile(zpath) as z:
 names=z.namelist()
 if len(names)!=len(set(names)) or set(names)!=(allowed|{'SHA256SUMS.txt'}):
  raise SystemExit('BLOCK: unexpected ZIP contents')
 if z.testzip() is not None:raise SystemExit('BLOCK: ZIP CRC error')
 sums={}
 for line in z.read('SHA256SUMS.txt').decode().splitlines():
  digest,rel=line.split('  ',1)
  if rel in sums or len(digest)!=64:raise SystemExit('BLOCK: bad checksum manifest')
  sums[rel]=digest
 if set(sums)!=allowed:raise SystemExit('BLOCK: checksum path mismatch')
 for rel in names:
  i=z.getinfo(rel)
  if (rel.startswith('/') or '..' in Path(rel).parts or
      stat.S_ISLNK(i.external_attr>>16) or i.file_size>80000):
   raise SystemExit('BLOCK: untrusted path/symlink/size')
  if rel!='SHA256SUMS.txt' and hashlib.sha256(z.read(rel)).hexdigest()!=sums[rel]:
   raise SystemExit('BLOCK: checksum mismatch: '+rel)
 for rel in allowed:
  t=dst/rel
  if t.exists() or t.is_symlink():raise SystemExit('BLOCK: destination already exists: '+rel)
 for rel in allowed:
  target=dst/rel;target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(z.read(rel))
print('Installed only exact audited Stage97 NO-GO diagnostics.')
PYINNER
PYTHON=".venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python)"
PYTHONPATH=src "$PYTHON" -m pytest -q -o addopts='' -W error \
  tests/test_stage97_execution_surface.py \
  tests/test_crypto_spot_reviewed_paper.py \
  tests/test_crypto_spot_independent_review.py \
  tests/test_crypto_spot_real_stage97_integration.py \
  tests/test_stage97_crypto_paper.py \
  tests/test_stage98_dual_market_review.py \
  tests/test_stage121_research_supervisor.py \
  tests/test_stage121_startup_hardening.py \
  tests/test_stage123_recovery_fault_lab.py
PYTHONPATH=src "$PYTHON" scripts/run_stage97_execution_surface_audit.py
[[ "$(PYTHONPATH=src "$PYTHON" -c 'from nexus_titan.diagnostics.stage97_execution_surface import audit_stage97_paper_execution; from pathlib import Path; print(audit_stage97_paper_execution(Path.cwd())["verdict"])')" == 'BLOCKED_PUBLIC_DIRECT_STAGE97_APPLY' ]] || { echo 'BLOCK: incorrect NO-GO audit verdict'; exit 1; }
git add -- \
 src/nexus_titan/diagnostics/stage97_execution_surface.py \
 tests/test_stage97_execution_surface.py \
 scripts/run_stage97_execution_surface_audit.py \
 docs/STAGE97_EXECUTION_SURFACE_NOGO_2026-11-16.md \
 reports/STAGE97_EXECUTION_SURFACE_NOGO_2026-11-16.json \
 scripts/titan_stage97_entrypoint_audit_push.sh \
 README_STAGE97_ENTRYPOINT_AUDIT_2026-11-16.txt
git diff --cached --check
EMAIL="$GH_ID+$GH_LOGIN@users.noreply.github.com"
GIT_AUTHOR_NAME='NEXUS TITAN Research' GIT_AUTHOR_EMAIL="$EMAIL" \
GIT_COMMITTER_NAME='NEXUS TITAN Research' GIT_COMMITTER_EMAIL="$EMAIL" \
git commit -m 'Research: pin Stage97 public execution-surface NO-GO audit'
[[ "$(git log -1 --format='%ae')" == "$EMAIL" && "$(git log -1 --format='%ce')" == "$EMAIL" ]] || { echo 'BLOCK: wrong commit identity'; exit 1; }
git -c credential.helper= -c credential.helper='!gh auth git-credential' push -u origin "$BRANCH"
if gh pr view "$BRANCH" -R "$REPO" --json url --jq '.url' >/dev/null 2>&1; then
 gh pr view "$BRANCH" -R "$REPO" --json url --jq '.url'
else
 gh pr create -R "$REPO" \
 --head "$BRANCH" --base 'feature/crypto-reviewed-paper-gateway-2026-11-16' --draft \
 --title 'Research audit: Stage97 direct execution-surface NO-GO guard' \
 --body 'Read-only source-level diagnostic and negative tests. Pinned Stage97 and reviewed wrapper source SHA, static explicit callsite inventory, direct API bypass remains BLOCKED/NO-GO. Does not change code that can trade, sign permits, or change risk limits. Please independently verify Python 3.11/3.12/3.13 CI and Secret Scan. No main merge, no live trading.'
fi
echo 'PUSH COMPLETE: feature-only audit; NEVER interpret passing diagnostic as release GO.'
