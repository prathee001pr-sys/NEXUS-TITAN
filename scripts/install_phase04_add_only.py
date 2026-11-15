#!/usr/bin/env python3
"""Phase04 hash-pinned additive installer; refuse conflicting/modified targets."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from validate_phase04_install import check_ancestor


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True)
    p.add_argument('--target',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    args=p.parse_args()
    src=args.source.resolve()
    dst=args.target.resolve()
    try:
        check_ancestor(dst)
        manifest=json.loads((src/'PHASE04_DELTA_MANIFEST.json').read_text())
        files=manifest['new_paths_sha256']
        manifest_dest=dst/'PHASE04_DELTA_MANIFEST.json'
        if manifest_dest.exists() or manifest_dest.is_symlink():
            raise FileExistsError('BLOCKED existing Phase04 manifest; no changes made')
        for name, digest in files.items():
            path=Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe path')
            original=src/path
            target=dst/path
            if not original.is_file() or hashlib.sha256(original.read_bytes()).hexdigest()!=digest:
                raise ValueError(f'invalid source manifest entry: {name}')
            if target.exists() or target.is_symlink():
                raise FileExistsError(f'BLOCKED existing target file: {name}')
        if not args.apply:
            print(f'SAFE DRY-RUN: {len(files)} new paths, all absent, base verified; no files copied.')
            return 0
        # No overwrite; stop if another process creates a file during copy.
        for name in sorted(files):
            to=dst/name
            to.parent.mkdir(parents=True,exist_ok=True)
            if to.parent.is_symlink():
                raise PermissionError('unsafe symlink parent')
            with open(to,'xb') as writer:
                writer.write((src/name).read_bytes())
        # Manifest itself is not a tracked Stage04 path and cannot be silently replaced.
        with open(manifest_dest,'xb') as writer:
            writer.write((src/'PHASE04_DELTA_MANIFEST.json').read_bytes())
        print(f'INSTALLED {len(files)} new paths + manifest; no existing source overwritten.')
        return 0
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as ex:
        print(str(ex),file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
