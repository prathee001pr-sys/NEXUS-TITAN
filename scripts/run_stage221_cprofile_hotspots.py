#!/usr/bin/env python3
"""Stage 221 bounded CPU function profiler for FIXED synthetic workloads only."""
from __future__ import annotations
import argparse
import cProfile
import json
from pathlib import Path
import pstats

from nexus_titan.diagnostics.stage221_profile import fixed_synthetic_cases


def collect_hotspots(*, iterations: int = 5, top_n: int = 8) -> list[dict]:
    if type(iterations) is not int or not 1 <= iterations <= 50 or type(top_n) is not int or not 1 <= top_n <= 20:
        raise ValueError('bounded profiling configuration required')
    rows=[]
    for case in fixed_synthetic_cases():
        p=cProfile.Profile()
        for _ in range(iterations):
            p.enable()
            case.callable_fn()
            p.disable()
        stats=pstats.Stats(p)
        entries=[]
        for (file_name, line, func_name),(primitive,total,self_time,cum_time,callers) in stats.stats.items():
            if file_name.startswith('~'):
                continue
            # Only an unambiguous basename, never local checkout paths/secrets.
            entries.append({'module_file':Path(file_name).name, 'function':func_name,
                            'line':int(line), 'calls':int(total),
                            'self_ms':round(self_time*1000,4), 'cumulative_ms':round(cum_time*1000,4)})
        entries.sort(key=lambda x:(-x['self_ms'],x['module_file'],x['line']))
        rows.append({'target':case.name,'iterations':iterations,
                     'top_self_cpu_functions':entries[:top_n],
                     'real_market_latency_verified':False,
                     'live_trading_authorized':False})
    return rows


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--iterations',type=int,default=5)
    p.add_argument('--top',type=int,default=8)
    p.add_argument('--json-out',type=Path)
    a=p.parse_args()
    try:
        result={'schema':'titan.stage221.synthetic_hotspots.v1',
                'notes':'cProfile is intrusive: CPU attribution only; do not compare these times to latency/SLA results.',
                'targets':collect_hotspots(iterations=a.iterations,top_n=a.top),
                'rust_rewrite_authorized':False,
                'live_trading_authorized':False}
    except ValueError as e:
        print(f'PROFILE NOT ACCEPTED: {e}')
        return 2
    raw=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if a.json_out:
        a.json_out.parent.mkdir(parents=True,exist_ok=True)
        a.json_out.write_text(raw,encoding='utf-8')
    else:print(raw)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
