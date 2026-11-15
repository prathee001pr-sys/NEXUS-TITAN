# NEXUS TITAN — Phase 02 / Stages 112–116 (offline data-quality candidate)

Date: 2026-11-10. Status: **ADD-ONLY / OFFLINE-SYNTHETIC-TESTED / NO-GO FOR MARKET AUTHENTICITY / NO LIVE TRADING**.

## Exact parent and preservation rules

- GitHub repository: `prathee001pr-sys/NEXUS-TITAN`.
- Verified Stage 108–111 Phase 01 PR #100 head: `41c7a3166bbaad30e65db0a9cf158a081b98082f` (PR CI and secret scan green).
- Continue on a *separate feature branch*, NOT on `main`. Keep PR #100 Draft; do not merge or change repository visibility.
- This patch adds five modules, six test/support files, a read-only validation script and documentation. It does not edit existing trading, risk, broker, crypto or governance modules.

## New modules

| Stage | Module | Evidence produced | Strict limit |
|---|---|---|---|
| 112 | `stage112_fo_contract_master.py` | Date-effective and SHA-fingerprinted contract definitions | No official lot/expiry/tick master verification |
| 113 | `stage113_fo_source_provenance.py` | Bounded in-memory quote CSV with byte SHA-256, checked field types, on-tick bid/ask, checked contract identities | User-declared SHA != trusted publisher identity; source rights unverified |
| 114 | `stage114_option_asof_alignment.py` | Latest bid/ask quotes not later than decision time; staleness/skew limits; complete CE/PE pair | No exchange or broker timestamp authenticity |
| 115 | `stage115_session_coverage.py` | Explicit declared-open/close minute coverage, sample missing minutes, out-of-session rows | Exchange holiday calendar and 15-year coverage NOT verified |
| 116 | `stage116_data_readiness_gate.py` | Single deterministic evidence record joining Stage 111 and Stages 112–115 | Always NO-GO: no broker/strategy/live authority |

## CSV quote chunk schema

Exactly the following header, in this order, UTF-8 with **no** additional columns:

```
contract_id,observed_at_ist,bid_paise,ask_paise,volume,open_interest
```

Example values used in test fixtures are made-up. They are not NSE, BSE or broker observations. `contract_id` MUST appear in the supplied Stage112 master and the quote date MUST equal the review trading date. `observed_at_ist` is an exact ISO8601 minute timestamp with `+05:30` offset. Price fields are positive integer paise with caller-supplied contract tick-size checking. `volume` and `open_interest` are nonnegative integer quantities. Maximum 4 MiB and 10,000 quote rows per in-memory chunk.

A file name is a basename only: this package **does not open arbitrary paths**. The calling application, not this research module, is responsible for authorized access and secure file handling. The CSV source may be an unverified local file or synthetic fixture; neither path becomes license-verified merely by passing a hash.

## Governance rules

1. No bundled live-market subscription, feed credentials or real trading data.
2. No hard-coded lot size, expiry weekday, expiry date or exact NSE trading session schedule; **official date-effective contract master and holiday/session evidence remain missing**.
3. The Stage112 type is limited to index futures and index options for NIFTY/BANKNIFTY. No stock options, BSE index options, crypto, market orders or broker API.
4. A complete three-minute synthetic CSV is **not** the same as 15 years of minute coverage. Stage115 `chunk_coverage_complete=True` is explicitly structural; all verification/authorization flags remain `False`.
5. Phase 01 Stage111 remains a synthetic predecessor fingerprint. Stage116 does not upgrade it to market, risk or execution certification.
6. Raw CSV parsing never executes formulas, pickles, generated Python or untrusted scripts. No filesystem writes, network connections or credential access.
7. `Stage116Phase02Report.verdict` is always `PHASE02_UNVERIFIED_DATA_FOUNDATION_ONLY_NO_GO`.

## What still requires separate evidence before advancing

- Actual licensed historical minute/tick quote files, source permission terms, immutable vendor or exchange provenance, independent reconciliation, and date-effective official contract metadata.
- Official session/holiday calendar with segment-specific special sessions and expiry-day rules. Calendar **cannot** be inferred from weekday alone.
- Multi-day, long-span 15-year coverage inventory, corporate/contract actions, roll mappings and actual missing-session reconciliation.
- Bid/ask/tick volume vs true executed volume and real liquidity evidence; broker-specific charges; independently verified risk-veto runtime.
- Prospective paper/shadow operation and independently approved testing gates. **Never permit real trade orders here.**

## Official reference starting points (not an API license)

- NSE contract specs: https://www.nseindia.com/static/products-services/equity-derivatives-contract-specifications
- NSE market-data subscriptions: https://www.nseindia.in/static/nse-data-and-analytics/data-information-vending
- NSE historical order/trade data: https://www.nse.in/static/market-data/eod-historical-data-subscription
- NSE historical contract-wise F&O data: https://www.nseindia.com/report-detail/fo_eq_security

No source bytes were copied from these websites. The sources are for verification/procurement planning only.

## Local tests

After copying **only** the Phase02 additive paths to a checked-out Phase01 PR #100 feature base:

```bash
python3 scripts/validate_phase02_install.py --focused
python3 scripts/validate_phase02_install.py --full
```

The validator ensures the four predecessor Stage108–111 Git blobs match the pinned Phase 01 PR head and intentionally refuses an unexpected ancestor snapshot. `--ancestor-only` must be invoked from the delta/extracted copy with `--root <target_checkout>` before installing files. The code does not perform a Git push or merge.
