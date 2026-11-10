#!/usr/bin/env python3
"""Safe, explicit add-only Phase03 copier for a previously verified Phase02 checkout.

Dry-run by default; --apply copies only *new* files, no Git or permission writes.
Requires SHA-verified Stage112–116 ancestor; refuses any existing destination file.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

from validate_phase03_install import PRIOR

FILES = (
 'src/nexus_titan/operations/stage117_guardian_jobs.py',
 'src/nexus_titan/operations/stage118_titan_learn.py',
 'src/nexus_titan/operations/stage119_titan_advisor.py',
 'src/nexus_titan/operations/stage120_governed_learning_advisor.py',
 'tests/test_stage117_guardian_jobs.py',
 'tests/test_stage118_titan_learn.py',
 'tests/test_stage119_titan_advisor.py',
 'tests/test_stage120_governed_learning_advisor.py',
 'scripts/run_titan_advisor_demo.py',
 'scripts/validate_phase03_install.py',
 'scripts/install_phase03_add_only.py',
 'docs/PHASE03_GUARDIAN_LEARN_ADVISOR_2026-11-10.md',
 'PHASE03_README_FIRST_HINGLISH.md',
 'PHASE03_DELTA_MANIFEST.json',
)


def main() -> int:
    arg=argparse.ArgumentParser()
    arg.add_argument('--source',type=Path,default=Path(__file__).resolve().parent.parent)
    arg.add_argument('--target',type=Path,required=True)
    arg.add_argument('--apply',action='store_true',help='copy after showing a dry-run')
    args=arg.parse_args()
    src=args.source.resolve();dst=args.target.resolve()
    if src==dst or not (dst/'pyproject.toml').is_file():
        print('BLOCKED: choose a separate existing TITAN checkout',file=sys.stderr);return 2
    for name,expected in PRIOR.items():
        f=dst/name
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:
            print('BLOCKED mismatched ancestor:',name,file=sys.stderr);return 3
    for name in FILES:
        if not (src/name).is_file() or (dst/name).exists():
            print('BLOCKED missing source or destination already occupied:',name,file=sys.stderr);return 4
    print('Ancestor hashes match; all 14 Phase03 paths are absent in target.')
    if not args.apply:
        print('DRY-RUN only. Add --apply to install new paths (not older modules).')
        return 0
    installed=[]
    try:
        for name in FILES:
            target=dst/name
            target.parent.mkdir(parents=True,exist_ok=True)
            # Exclusive create: never overwrites a source, config, or existing module.
            with target.open('xb') as f:
                installed.append(target)
                f.write((src/name).read_bytes())
        print('Copied',len(installed),'new research-only paths. Run focused/full tests before committing.')
        return 0
    except Exception:
        for f in reversed(installed):
            f.unlink(missing_ok=True)
        raise


if __name__=='__main__':
    raise SystemExit(main())
