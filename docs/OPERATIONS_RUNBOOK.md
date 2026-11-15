# NEXUS TITAN Offline Operations Runbook

## Intended operating mode
Research and virtual/shadow simulation only. No real broker order transmission is authorized by this package.

## Clean setup (Python 3.11+)
```bash
python -m venv .venv
# Linux/macOS
. .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Validate before each research run
```bash
python scripts/run_project_validation.py
python scripts/run_advanced_backtest_suite.py --json-out reports/latest_backtest.json
```

## Safe workflow
1. Work on a copy/branch; retain the previous known-good ZIP and its SHA-256.
2. Inspect dataset licence, provenance, timezone, instrument master and session coverage.
3. Run validation before and after changes.
4. Review the report's dataset class, test evidence, G0-G9 statuses and promotion decisions.
5. Treat synthetic fixtures as QA only. Never use them to claim strategy profitability.
6. Keep risk controls, permissions and kill-switch state under human ownership.
7. Back up SQLite state before migrations or experiments.

## Stop conditions
Stop and investigate if tests fail, a report claims licensed data without evidence, reconciliation discrepancy is non-zero, a dataset hash changes unexpectedly, a component is stale/critical, or any live-order route/credential appears.

## Android/Replit note
A browser-based Replit workspace can run the same commands in its Shell if Python 3.11+ and dependencies are available. On Android, avoid editing ZIP contents manually; upload/extract into a new workspace or branch, preserve the original archive, and use the Shell commands above. Replit runtime behaviour and storage persistence must be verified in that workspace; this runbook does not certify a specific deployment.
