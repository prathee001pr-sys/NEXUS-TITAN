#!/usr/bin/env python3
"""Stage 224 local-only read-only audit; never grants execution or Rust access."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from nexus_titan.diagnostics.stage224_final_audit import (
    evaluate_stage224_final_audit, safe_stage224_evidence_template,
)

ROOT = Path(__file__).resolve().parents[1]

def _read(path: Path) -> object:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 100_000:
        raise ValueError('Missing, symlinked, or oversized evidence file')
    return json.loads(path.read_text(encoding='utf-8'),
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError('invalid constant')))


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage222-report',type=Path,default=ROOT/'reports/STAGE222_LOCAL_PYTHON_AB_2026-11-14.json')
    p.add_argument('--local-evidence',type=Path)
    p.add_argument('--json-out',type=Path)
    a=p.parse_args(argv)
    try:
        stage222=_read(a.stage222_report)
        evidence=_read(a.local_evidence) if a.local_evidence else safe_stage224_evidence_template()
        receipt=evaluate_stage224_final_audit(stage222,evidence,project_root=ROOT)
        # Invalid evidence produces *no* output artifact (fail closed).
        if not receipt.accepted_for_offline_evidence_record:
            print('REJECTED: invalid, tampered or unsafe local audit evidence',file=sys.stderr)
            return 2
        report={
            'schema':'titan.stage224.final_offline_review.v1',
            'receipt':asdict(receipt),
            'test_data_origin':'caller-supplied-local-observation-not-independent-attestation',
            'stage222_source':a.stage222_report.name,
            'production_release':'NO_GO',
            'rust_integration':'NO_GO',
            'live_trading_authorized':False,
        }
        raw=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+'\n'
        if a.json_out:
            if a.json_out.is_symlink():
                raise ValueError('Output symlink prohibited')
            # avoid overwriting an existing immutable audit record
            with a.json_out.open('x',encoding='utf-8') as target:
                target.write(raw)
        else:
            print(raw,end='')
        return 0
    except (OSError,ValueError,TypeError,UnicodeError,RecursionError) as exc:
        print('REJECTED:',exc,file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
