#!/usr/bin/env python3
"""Read-only Stage112-116 ancestry preflight and bounded validation runner.

Use --ancestor-only against checked-out Phase01 branch BEFORE installing new
files. Use --focused or --full only after copying the additive Stage112-116 files.
Neither mode changes Git history, market data, credentials or trading controls.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys

# GitHub PR100 commit 41c7a3166bbaad30e65db0a9cf158a081b98082f
# Pinned Git blob hashes; reject drift rather than layering on unknown source.
EXPECTED = {
    "src/nexus_titan/operations/stage108_upgrade_compatibility.py": "171ea7c2c09f94f33355a1c91169f4432924fc85",
    "src/nexus_titan/operations/stage109_effective_dated_stt.py": "483c5d208a9b623c9d7e81158416092be5387491",
    "src/nexus_titan/operations/stage110_deterministic_execution_replay.py": "bd1c5608758397bb7a56db6d33979224af1ba87d",
    "src/nexus_titan/operations/stage111_phase01_acceptance.py": "66d2fa114b1b500fcf0c70451fa160201287e337",
}
NAMES = {
    112:"fo_contract_master",
    113:"fo_source_provenance",
    114:"option_asof_alignment",
    115:"session_coverage",
    116:"data_readiness_gate",
}
SOURCES=tuple(f"src/nexus_titan/operations/stage{k}_{v}.py" for k,v in NAMES.items())
TESTS=tuple(f"tests/test_stage{k}_{v}.py" for k,v in NAMES.items())
SUPPORT=("tests/phase02_fixtures.py",)


def _blob(path:Path)->str:
    data=path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ancestor-only',action='store_true')
    p.add_argument('--focused',action='store_true')
    p.add_argument('--full',action='store_true')
    p.add_argument('--root',type=Path,default=Path.cwd(),help='Checkout root (defaults to current directory)')
    opts=p.parse_args()
    if opts.focused and opts.full:
        p.error('Select at most one test mode')
    root=opts.root.expanduser().resolve()
    errors=[]
    for rel,expected in EXPECTED.items():
        if not (root/rel).is_file() or _blob(root/rel)!=expected:
            errors.append(f"PREDECESSOR_HASH_MISMATCH: {rel}")
    for rel in SOURCES+TESTS+SUPPORT:
        exists=(root/rel).is_file()
        if opts.ancestor_only and (root/rel).exists():
            errors.append(f"STAGE112_116_TARGET_ALREADY_EXISTS: {rel}")
        elif not opts.ancestor_only and not exists:
            errors.append(f"STAGE112_116_TARGET_MISSING: {rel}")
    if errors:
        print('\n'.join(errors),file=sys.stderr)
        return 2
    print('PASS: Phase01 PR100 predecessor hashes matched',flush=True)
    print('PASS: Phase02 target paths '+('absent' if opts.ancestor_only else 'present'),flush=True)
    if opts.ancestor_only:
        return 0
    if opts.focused or opts.full:
        tests=list(TESTS) if opts.focused else ['tests/']
        cmd=[sys.executable,'-m','pytest','-q','-o','addopts=',
             *(['-W','error'] if opts.focused else ['--disable-warnings']),*tests]
        print('RUN: '+' '.join(cmd),flush=True)
        env=os.environ.copy()
        env['PYTHONPATH']=str(root/'src') + os.pathsep + env.get('PYTHONPATH','')
        try:
            return subprocess.run(cmd,cwd=root,env=env,timeout=300,check=False).returncode
        except subprocess.TimeoutExpired:
            print('STOP: pytest timed out',file=sys.stderr)
            return 124
    return 0


if __name__=='__main__':
    raise SystemExit(main())
