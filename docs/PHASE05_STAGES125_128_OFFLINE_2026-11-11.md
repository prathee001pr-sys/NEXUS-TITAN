# NEXUS TITAN Phase 05 — Stages 125–128

Status: Offline code ready. 24 focused tests passed. Full regression attempted but timed out at ~37%; no full-suite pass claimed. GitHub CI not run for Phase 05.

- Stage 125: strict 23-column NSE-style local option-chain snapshot parser, raw SHA-256, missing quote and crossed-market flags.
- Stage 126: external declaration SHA-256, bounded filename, canonical IST capture time; missing time remains missing; user-declared time is NOT authenticated.
- Stage 127: deterministic structural quote quality and paired CE/PE count checks.
- Stage 128: combined fail-closed research-inventory acceptance, NO-GO for historical backtest, paper and live trading.

## Safety limits

Source, exchange contract master, expiry, rights, true observation time and quote provenance are not independently authenticated. A capture timestamp provided by a user is a declaration, not proof of the exchange quote time. No conversion to Stage 113 quote chunks is attempted, because it would require inventing contract identifiers and timestamps. Do not treat these snapshots as a time series. This implementation is an add-only offline research extension, not an authenticated market-data provider.

## Replit validation

Extract delta ZIP into an isolated checkout of the exact Phase 04 PR #103 head (`2b085facee536fb5f0b3507c54ee453d858677ec`). Do not overwrite existing tracked files. Run:

```
PYTHONPATH=src ~/workspace/nexus-titan/.venv/bin/python -m pytest -q -o addopts='' tests/test_stage125_nse_option_chain_snapshot.py tests/test_stage126_128_snapshot_pipeline.py
PYTHONPATH=src ~/workspace/nexus-titan/.venv/bin/python -m pytest -q -o addopts='' tests/
```

Use bounded batches if a single full-suite run stalls. Before pushing: inspect diff, validate hashes, configure GitHub noreply author/committer, run secret scan, open draft PR targeting Phase 04 branch; do not merge main, change repository visibility or enable live trading.
