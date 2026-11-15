#!/usr/bin/env python3
"""Read-only Stage108-111 structural preflight and optional offline pytest.

Works inside project root. Never modifies repository or pushes to GitHub.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import subprocess
import sys

EXPECTED = {
    "src/nexus_titan/operations/stage99_expiry_margin_review.py": "bf9bd8858ddb15ff1aa19444d0d48c478285de62",
    "src/nexus_titan/operations/stage100_fo_reconciliation_gate.py": "b2840609123fc28dbfeae48c7ab6f0afe96e9aa7",
    "src/nexus_titan/operations/stage101_historical_bar_preflight.py": "ab550314a97ca7acc7cd6b76c3a121c81d4d97b0",
    "src/nexus_titan/operations/stage102_option_chain_preflight.py": "b92c6b8b1f57bdf48092a3a83b000006871cf82a",
    "src/nexus_titan/operations/stage103_readonly_assurance_gate.py": "f1acc8603e4918f254e619aa61aac50367d835af",
    "src/nexus_titan/operations/stage104_historical_catalog_review.py": "b99fe6170a8cff6758b1182190bf762888ea4b6b",
    "src/nexus_titan/operations/stage105_execution_stress_review.py": "b96297b5ae5517afd8afd9755ba97fd835fc51f4",
    "src/nexus_titan/operations/stage106_holdout_research_gate.py": "29250bd44b7b4960c959c870ec8d3dc1636cd238",
    "src/nexus_titan/operations/stage107_adversarial_assurance_review.py": "440699f5c19e52ed057daeaf8e729f7666b493d8",
}
SOURCES = tuple(f"src/nexus_titan/operations/stage{s}_{name}.py" for s,name in (
    (108,"upgrade_compatibility"),(109,"effective_dated_stt"),
    (110,"deterministic_execution_replay"),(111,"phase01_acceptance")))


def _blob_hash(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode()+data).hexdigest()


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--ancestor-only",action="store_true",help="Verify Stage99-107 ancestry and NO existing Stage108-111 files before additive patch")
    parser.add_argument("--focused",action="store_true",help="Run only the four new test files")
    parser.add_argument("--full",action="store_true",help="Run complete existing regression (potentially slow)")
    args=parser.parse_args()
    root=Path.cwd()
    fails=[]
    for rel,sha in EXPECTED.items():
        p=root/rel
        if not p.is_file() or _blob_hash(p)!=sha:
            fails.append(rel)
    for rel in SOURCES:
        if args.ancestor_only:
            if (root/rel).exists():
                fails.append(rel + " (already exists; do not overwrite)")
        elif not (root/rel).is_file():
            fails.append(rel)
    if fails:
        for path in fails:print("MISSING/MISMATCH:",path,file=sys.stderr)
        print("STOP: wrong ancestor snapshot; do not apply/merge without review",file=sys.stderr)
        return 2
    print("PASS: 9 predecessor source blob hashes + "
          + ("4 add-on paths absent (safe preflight)" if args.ancestor_only else "4 new source modules present")
          + "; read-only")
    if args.ancestor_only:
        if args.focused or args.full:
            print("STOP: run tests only after installing patch",file=sys.stderr)
            return 2
        return 0
    if args.focused or args.full:
        tests=([f"tests/test_stage{s}_{name}.py" for s,name in (
            (108,"upgrade_compatibility"),(109,"effective_dated_stt"),
            (110,"deterministic_execution_replay"),(111,"phase01_acceptance"))]
               if args.focused else ["tests/"])
        cmd=[sys.executable,"-m","pytest","-q","-o","addopts=",*( ["-W","error"] if args.focused else ["--disable-warnings"] ),*tests]
        print("Run:"," ".join(cmd),flush=True)
        try:return subprocess.run(cmd,cwd=root,timeout=230,check=False).returncode
        except subprocess.TimeoutExpired:
            print("STOP: timed out; no CI green claim",file=sys.stderr);return 124
    return 0


if __name__=="__main__":
    raise SystemExit(main())
