# Stage 26 — Historical NIFTY/BANKNIFTY F&O Data-Source Preflight

**Status: Research integration added; actual NSE data has not been obtained,
authenticated, imported or backtested.** This stage is deliberately **not**
automated market-data scraping, vendor access or real-money trading.

## New working components

- `src/nexus_titan/data/historical_fo_bundle.py` composes the already tested
  Stage16 strict single-snapshot SHA-256 CSV importer with Stage16+ history
  continuity and point-in-time options contract checks. It accepts **multiple
  CSV snapshots for exactly one underlying and one expiry/contract**. Supported
  underlyings: `NIFTY` and `BANKNIFTY`.
- `scripts/run_stage26_fo_bundle_preflight.py` is a read-only command-line
  front-end accepting an operator JSON manifest and a local CSV directory.
  CSV inputs must have columns prescribed by
  `nexus_titan.data.option_chain_ingest.COLUMNS`.
- `tests/test_stage26_historical_fo_bundle.py` checks valid synthetic
  per-contract batches and rejects mismatched hashes, gaps, duplicate/replayed
  timestamps, unlicensed claims promoted to authenticity, symbol mismatch,
  session/holiday mismatches, wrong point-in-time metadata, symlink/path
  traversal, excessive file sizes and malformed JSON fields.

All generated output has:
`strategy_promotion_allowed=false`, `broker_orders_sent=0`,
`self_declared_licence_or_vendor_authenticated=false`,
`official_exchange_metadata_authenticated=false` and
`exchange_calendar_authenticated=false`. A label claiming to be
`LICENSED_EXCHANGE_HISTORY` or an operator's `source_verified=True`
**does not authenticate the vendor, contract or actual exchange source**.

## Preflight usage from Replit / desktop

1. Obtain a dataset **legally** from a vendor whose data-use/redistribution
   rights are acceptable to the owner. Do not commit vendor data, keys, or
   private contract notes to the repository. Store them in a separate local
   folder such as `/tmp/titan-vendor-contract`.
2. Normalize each point-in-time **option-chain snapshot** to one strict
   CSV and compute each file's SHA-256 *independently*. Record the source
   timestamps, actual contract symbol, expiry, strike step, tick size, lot
   size and freeze quantity valid at that historic timestamp; record vendor,
   calendar, licence, and contract references in the manifest JSON.
3. Provide exact declared first/last observations. The preflight verifies all
   expected **1-minute grid slots between those boundaries only**; it does
   not infer missing data outside them. For full-day coverage the manifest
   must explicitly start at 09:15:00 and end at the last expected in-session
   minute, subject to the *supplied* calendar.
4. Run:

```bash
python scripts/run_stage26_fo_bundle_preflight.py \
  --root /tmp/titan-vendor-contract \
  --declaration /tmp/titan-contract-manifest.json
```

### Manifest JSON schema (example values ONLY, not genuine NSE metadata)

```json
{
  "dataset_id": "example-unverified-contract",
  "underlying": "NIFTY",
  "provider_reference": "example/vendor-review-required",
  "licence_reference": "example/licence-not-verified",
  "calendar_reference": "example/holiday-review-required",
  "contract_reference": "example/contract-review-required",
  "declared_start": "2026-11-02T09:15:00+05:30",
  "declared_end": "2026-11-02T09:16:00+05:30",
  "dataset_class_claim": "UNVERIFIED_RESEARCH_SAMPLE",
  "source_review_reference": "",
  "declared_holidays": [],
  "contract": {
    "symbol": "EXAMPLE-NIFTY-OPT", "underlying": "NIFTY",
    "exchange": "NSE", "segment": "OPTIONS",
    "lot_size": 25, "tick_size": 0.05, "freeze_quantity": 1000,
    "effective_from": "2026-11-01",
    "effective_to": "2026-11-05",
    "expiry_date": "2026-11-05",
    "strike_step": 50.0, "max_lots_per_trade": 10,
    "source_reference": "example/contract-review-required",
    "source_verified": true
  },
  "snapshots": [
    {
      "filename": "snapshot_0915.csv",
      "observed_at": "2026-11-02T09:15:00+05:30",
      "sha256": "<replace-with-full-sha256-of-your-first-CSV>"
    },
    {
      "filename": "snapshot_0916.csv",
      "observed_at": "2026-11-02T09:16:00+05:30",
      "sha256": "<replace-with-full-sha256-of-your-second-CSV>"
    }
  ]
}
```

The above example is **not runnable** until both files, genuine matching
sha256 values, historically appropriate valid contract fields and a reviewed
calendar are supplied. Even then it **only structurally passes**; it is not
official verification.

### Important boundaries

- Each package covers **one fixed contract and expiry**, not the entire
  underlying's 15-year changing derivatives universe. The batch default is
  at most 500 snapshots, 8 MiB/file, 64 MiB total. Full-history integration
  requires partitioning many contracts and dates, instrument-master versioning,
  licensed snapshots, coverage audits and a separate safe aggregator.
- Existing Stage16 snapshot checks enforce quote coherence, CE/PE, lot size,
  expiration, timestamps, source digest and configured exchange sessions.
  Existing Stage16 history checks enforce duplicate/replayed source prevention,
  strike retention and missing interval detection.
- File hash matching proves byte stability, not a cryptographically authenticated
  vendor origin. Read-only preflight rereads hashes to detect changes during
  validation but is not a fully atomic defense against malicious filesystem
  writers; untrusted directories still need OS permissions/immutable storage.
- Calendar is a *supplied* regular NSE session baseline with operator holiday
  exclusions; it must not be treated as an independently reviewed official
  historical exchange calendar.
- This preflight only supports normalized **option-chain snapshots**. It is
  not an official 15-year 1-minute futures/OHLCV importer, a Level 2
  historical order-book feed, a broker adapter, or a real market backtest.

## P0 Risk & Veto bypass audit — unresolved

Previous Stage23 `guarded_options_research_buy()` calls the existing
`Action.PAPER_TRADE` default-deny permission, `AuthoritativeRiskEngine`,
exact contract risk and Red-Team veto before the research reserve. However:

1. Stage19 `DurableResearchShadowLedger.reserve_buy()` remains directly
   callable and does **not** itself require a valid authoritative risk token.
2. Stage24 `simulate_and_settle_long_exit()` is an optional paper-research
   adapter, not a globally managed trader/order router.
3. No durable, independently signed risk approval is atomically bound
   to broker-like order/ledger admission across processes.
4. No owner-reviewed global broker-credential permission or live routing
   has been authenticated. These absences are deliberate fail-closed
   *production blockers*, not evidence of fully enforcing portfolio risk.

**Next priority:** Stage27 must design an unbypassable **paper-only**
execution admission interface and transaction-bound risk decision and
concurrency tests, while preserving all protected Risk & Veto settings.
Real broker operations must remain physically disconnected until separate
human approval, verified data, security controls, and genuine shadow results.

## Test evidence and release decision

Full suite and Stage25 offline backtesting continue to run through the
existing `.github/workflows/ci.yml` Python 3.11/3.12/3.13 matrix.
The Stage26 new tests are synthetic only; genuine vendor data cannot be
tested until legal data packages are supplied.

**Release decision: BLOCKED for live trading / strategy promotion.**
Work remains on a stacked draft branch, without merging protected `main`.
