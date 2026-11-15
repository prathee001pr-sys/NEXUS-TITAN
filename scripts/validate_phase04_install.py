#!/usr/bin/env python3
"""Phase04 add-only structural checks and bounded pytest. No Git writes/trades."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PRIOR = {
  'src/nexus_titan/operations/stage117_guardian_jobs.py':'91767943565bb57b6863f7a0d61b0d3f4cd7d573e76c852abe3300ef12f142e2',
  'src/nexus_titan/operations/stage118_titan_learn.py':'1c040734369585fab9e986b9600b47fe5c3be2b6b08c09113895df6046362e76',
  'src/nexus_titan/operations/stage119_titan_advisor.py':'8d585e3e924bcd3674cb9530ea8ee6cfbe3471e59302e7cb0ee304fb3eed7809',
  'src/nexus_titan/operations/stage120_governed_learning_advisor.py':'8047cc5ef0d59590900537020d59d0c02b9f77723ae3f96697acc8f0e56f1c69',
}


def check_ancestor(root: Path) -> None:
    for name, sha in PRIOR.items():
        p=root/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
            raise ValueError(f'BLOCKED Phase03 ancestor SHA256 mismatch: {name}')


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--ancestor-only',action='store_true')
    parser.add_argument('--focused',action='store_true')
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args()
    root=args.root.resolve()
    try:
        check_ancestor(root)
        print('Verified exact four Stage117-120 Phase03 GitHub source SHA256 hashes',flush=True)
        manifest=json.loads((Path(__file__).resolve().parent.parent/'PHASE04_DELTA_MANIFEST.json').read_text())
        paths=manifest['new_paths_sha256']
        if args.ancestor_only:
            existing=[x for x in paths if (root/x).exists()]
            if existing:
                raise ValueError('BLOCKED Phase04 destination path already exists: '+', '.join(existing))
            print('Ancestor-only dry-run passed; zero old files changed.')
            return 0
        for name, expected in paths.items():
            p=root/name
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
                raise ValueError(f'BLOCKED Phase04 expected file/hash mismatch: {name}')
        print('All Phase04 new-file hashes verified.',flush=True)
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as ex:
        print(str(ex),file=sys.stderr)
        return 2
    if not args.focused and not args.full:
        return 0
    cmd=[sys.executable,'-m','pytest','-q','-o','addopts=']
    if args.focused:
        cmd+=['-W','error',*[f'tests/test_stage{i}_{name}.py' for i,name in (
          (121,'research_supervisor'),(122,'verified_recovery'),
          (123,'recovery_fault_lab'),(124,'guardian_release_gate'))]]
    else:
        cmd+=['--disable-warnings','tests/']
    env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
    print('Running bounded tests without any trading authority...',flush=True)
    try:
        return subprocess.run(cmd,cwd=root,env=env,check=False,timeout=600).returncode
    except subprocess.TimeoutExpired:
        print('BLOCKED: pytest exceeded 600s; no approval',file=sys.stderr)
        return 124

if __name__=='__main__':
    raise SystemExit(main())
