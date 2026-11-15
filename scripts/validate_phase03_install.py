#!/usr/bin/env python3
"""TITAN Phase03 add-only preflight. No auto-copy, Git writes or live trading."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

PRIOR = {
  'src/nexus_titan/operations/stage112_fo_contract_master.py': '9440df2efea076efd0aa917530fbd7536e15ae3999869419bd2b536f5c63f5b2',
  'src/nexus_titan/operations/stage113_fo_source_provenance.py': 'cd231bcccefd9d6f8b06a5e6239d8801bee4ed89716cb4a6f4f5ed4e44a35ae1',
  'src/nexus_titan/operations/stage114_option_asof_alignment.py': 'c972ee6b92f87d901a27c42c164e40e9d55a1b2725298a5f2f0578b908cf0a57',
  'src/nexus_titan/operations/stage115_session_coverage.py': 'febb1ada4b8d5861f5e9d19632e28775dcee818fc2f695b0b713eeff5bef1d15',
  'src/nexus_titan/operations/stage116_data_readiness_gate.py': 'a3fb0e1c60c9ae837578d677f8df21979bb41f0e71d8f235aebe126de460dcad',
}
NEW = (
  'src/nexus_titan/operations/stage117_guardian_jobs.py',
  'src/nexus_titan/operations/stage118_titan_learn.py',
  'src/nexus_titan/operations/stage119_titan_advisor.py',
  'src/nexus_titan/operations/stage120_governed_learning_advisor.py',
  'tests/test_stage117_guardian_jobs.py',
  'tests/test_stage118_titan_learn.py',
  'tests/test_stage119_titan_advisor.py',
  'tests/test_stage120_governed_learning_advisor.py',
)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--ancestor-only',action='store_true',help='verify ancestor before installing add-only files')
    parser.add_argument('--focused',action='store_true')
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args()
    root=args.root.resolve()
    for name,expected in PRIOR.items():
        p=root/name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
            print('BLOCKED Phase02 ancestor source hash mismatch:',name,file=sys.stderr)
            return 2
    print('Phase02 five module SHA256 ancestor matches')
    if args.ancestor_only:
        existing=[name for name in NEW if (root/name).exists()]
        if existing:
            print('BLOCKED: new files already exist in target; manual review required:',existing,file=sys.stderr)
            return 3
        print('Ancestor clean. Copy add-only files only after manual review.')
        return 0
    for name in NEW:
        if not (root/name).is_file():
            print('BLOCKED missing Phase03 file:',name,file=sys.stderr)
            return 4
    if args.focused or args.full:
        cmd=[sys.executable,'-m','pytest','-q','-o','addopts=']
        if args.focused:
            cmd+=['-W','error',*[f'tests/test_stage{i}_'+s+'.py' for i,s in (
                (117,'guardian_jobs'),(118,'titan_learn'),(119,'titan_advisor'),(120,'governed_learning_advisor'))]]
        else:
            cmd+=['--disable-warnings','tests/']
        env=os.environ.copy();env['PYTHONPATH']=str(root/'src')
        print('Running bounded tests (no repository modification)...',flush=True)
        try:
            return subprocess.run(cmd,cwd=root,env=env,timeout=600,check=False).returncode
        except subprocess.TimeoutExpired:
            print('Test timeout exceeded; no code approval.',file=sys.stderr)
            return 124
    return 0


if __name__=='__main__':
    raise SystemExit(main())
