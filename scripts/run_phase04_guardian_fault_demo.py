#!/usr/bin/env python3
"""Explicit, offline-only Stage123 fault test; temporary fixtures auto-cleaned."""
from __future__ import annotations
from dataclasses import asdict
import argparse
import json
from pathlib import Path
from nexus_titan.operations.stage123_recovery_fault_lab import run_guardian_fault_lab

if __name__=='__main__':
    p=argparse.ArgumentParser(description='No network / live trading; local temp simulated worker only')
    p.add_argument('--run-offline-fault-test',action='store_true')
    args=p.parse_args()
    report=run_guardian_fault_lab(explicit_opt_in=args.run_offline_fault_test)
    print(json.dumps(asdict(report),indent=2))
    raise SystemExit(0 if report.all_passed else 2)
