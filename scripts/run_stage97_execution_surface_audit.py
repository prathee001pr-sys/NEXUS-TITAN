"""Emit read-only NO-GO Stage97 direct-entrypoint static audit receipt."""
from __future__ import annotations

import json
from pathlib import Path
from nexus_titan.diagnostics.stage97_execution_surface import audit_stage97_paper_execution

if __name__=="__main__":
    root=Path(__file__).resolve().parents[1]
    report=audit_stage97_paper_execution(root)
    out=root/"reports"/"STAGE97_EXECUTION_SURFACE_NOGO_2026-11-16.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(f"Stage97 source integrity: {report['pinned_source_match']}; verdict: {report['verdict']}")
    print(f"Receipt: {out.relative_to(root)}")
    # A documented missing mandatory gate is a successful diagnostic; that
    # must NEVER be confused with green release/production permission.
    if (not report['source_parse_ok'] or not report['pinned_source_match'] or
            report['unknown_crypto_apply_calls'] or report.get('unreviewed_atomic_apply_calls')):
        raise SystemExit(1)
