# Offline Option-Chain CSV Research Import — 2026-11-02

This increment extends draft PR #7's opt-in `chain_integrity` validator with
an **all-or-nothing CSV ingestion entry point**:
`nexus_titan.data.option_chain_ingest.load_research_option_chain_csv`.

## Accepted file format

CSV with exactly these 13 columns (reordering allowed):

`timestamp,symbol,underlying,expiry_date,strike,option_type,bid,ask,ltp,volume,open_interest,underlying_spot,lot_size`

- `timestamp`: ISO 8601 including explicit timezone, e.g. `2026-11-02T09:15:59+05:30`.
- `expiry_date`: `YYYY-MM-DD`; `option_type`: `CE` or `PE`.
- Prices must be positive, finite, and on the injected contract tick grid.
- Strike must align with the injected strike step; lot size must match metadata.
- One synchronized option expiry + underlying; both CE/PE legs at each strike.
- Exactly one row per contract, strike and side, with no duplicate columns.
- Max 8 MiB and 20,000 quote rows by default (configurable, positive limits).
- **Synthetic fixture only** until independently reviewed historical data exists.

## Example integration (offline, no network/broker)

```python
from datetime import datetime
from nexus_titan.data.option_chain_ingest import load_research_option_chain_csv
from nexus_titan.data.sessions import nse_equity_derivatives_baseline

# 'contract' must be an injected reviewed PointInTimeContractSpec
# for NSE OPTIONS with expiry_date, lot size, tick size and strike step.
# 'reviewed_holidays' should come from documented exchange calendar evidence;
# never assume a weekday-only schedule is official.
snapshot = load_research_option_chain_csv(
    "research/options_2026_11_02.csv",
    expected_sha256="64-character independently recorded hex digest",
    contract=contract,
    observed_at=datetime.fromisoformat("2026-11-02T09:16:00+05:30"),
    calendar=nse_equity_derivatives_baseline(holidays=reviewed_holidays),
    provider_reference="evidence/data-vendor-contract.pdf",
    licence_evidence_reference="evidence/licence-review.pdf",
    calendar_evidence_reference="evidence/nse-session-calendar.csv",
)
assert not snapshot.approved_for_strategy_promotion
```

A real SHA-256 checksum must be used. References are strings recording an
operator's evidence; this software does **not** verify their authenticity or
market-data licensing. No production route should treat this flag or report
as an authorization to execute trades.

## Fail-closed quality gates

1. Strict UTF-8 CSV/header, exact required columns and no extra/blank fields.
2. Single-read SHA-256 equality prevents accidental unnoticed input changes
   between hashing and parsing; cannot prevent falsified vendor data.
3. Explicit market-session calendar supplied by caller; reject non-session
   quotes, holidays and non-session observations.
4. Historical quote timestamps must be timezone-aware and aligned with the
   observation clock and injected point-in-time verified contract metadata.
5. Existing synchronized option-chain structural validator is required to pass.
6. Any failure raises `OptionChainIngestionError`; **no partial quotes** return.
7. Output is immutable `ResearchOptionChainSnapshot`, always carrying
   `approved_for_strategy_promotion=False`.

## Remaining gates

- Source/vendor identity and licence independently authenticated.
- Exchange-reviewed point-in-time contract master and holiday/session files.
- Ingestion across many timestamped snapshots with gap/ordering analysis.
- Official market execution/settlement margin and transaction charge evidence.
- Out-of-sample, walk-forward, multi-day shadow evidence and security review.
- Explicit human sign-off; no live-money trading in this branch.

This implementation does not modify existing risk/permissions, orders,
strategies, `main`, PR #6, or the live-trading-disabled boundary.
