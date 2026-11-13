# NEXUS TITAN Stages 201–205 — Indian F&O Historical Data Readiness (Offline)

**Scope:** Python-only, fail-closed, locally evaluated research intake. All new data consumed is operator supplied; all output is **structural/manual QA evidence** rather than exchange-grade or vendor-authenticated evidence. No network access, broker integration, live trading, permission escalation, strategy promotion, or merge into `main`.

## Modules

- **201** `stage201_fo_catalog_inventory.py`: validates and reconciles Stage44 `HistoricalCatalogResult` aggregate counts, timezone-aware windows, partition identities, declared CSV SHA-256 manifests, and produces a structured digest. Stage44 receipts remain *caller-supplied* for this check. No source authentication.
- **202** `stage202_fo_contract_master_review.py`: validates point-in-time NSE `PointInTimeContractSpec` records for NIFTY/BANKNIFTY F&O, expiry, lot/freeze sizing and duplicate identities. `source_verified=True` is still a **claim**, not external verification of NSE circulars.
- **203** `stage203_fo_source_integrity.py`: bounded, read-only, SHA-256 byte integrity checks of flat CSV basenames under a non-symlink local directory, size and duplicate controls. It cannot prove bytes came from a licensed/official provider.
- **204** `stage204_fo_temporal_embargo.py`: strictly increasing UTC timestamps, dataset identities, non-overlapping TRAIN/HOLDOUT splits, minimum embargo and per-dataset sufficiency. It cannot prove feature engineering used only historical inputs.
- **205** `stage205_fo_data_readiness_gate.py`: ties 201–204 receipts and Stage200's **synthetic-only** NO-GO receipt to a single internal manual QA digest; dataset IDs, declared source hashes, catalog temporal coverage and underlyings must match. All real-market validation, provider authentication, licensing, official calendar certification, broker execution and trade authorization remain **false**, even if the internal manual review flag is true.

## Verification notes

- Reconstructed offline snapshot includes user-provided Stage153 full ZIP + user-provided Stage154–195 overlays + the Stage196–200 GitHub-first source ZIP. Stage185–200 source hashes were checked against GitHub during integration work; GitHub CI for Stage200 is green.
- Run: `PYTHONPATH=src python -m pytest -q -o addopts='' -W error tests/test_stage201_205_batch.py`.
- Local tests: **63 passed** Stage201–205; **553 passed** combined 154–205 plus existing Stage26/44/104 interoperability tests; no failures in these selected batches.
- **NOT completed:** full repository regression, official NSE expiry/calendar reconciliation, live or historical vendor dataset ingestion, independently verified market provenance/licence, production backtest, crash-recovery or broker validation.
- The fixtures in the focused unit tests are deliberately synthetic; some fixtures directly construct Stage26/44 receipts. Passing tests must not be described as market-data readiness or performance proof.

## Gate policy and next steps

- Integrate only into the existing Stage200 head as a stacked draft PR, never `main`.
- Require full GitHub Actions matrix, secret scan and review before considering Stage205 implementation verified.
- For Stage206+ actual quote-level backtesting, obtain and independently validate historical NIFTY/BANKNIFTY F&O contract master, exchange calendar, vendor license and dataset integrity first. Real-data claims remain blocked until separately evidenced.
