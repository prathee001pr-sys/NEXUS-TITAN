# Dataset Provenance & Promotion Gate (DATA-011)

## Purpose

A dataset is not promotion-ready merely because its CSV parses or its SHA-256 matches. A checksum proves the exact bytes inspected; it does not prove vendor identity, licence rights, point-in-time instrument metadata, exchange-session completeness, or survivorship-bias-free coverage.

## Gate requirements

A `DatasetManifest` may set `allowed_for_strategy_promotion=true` only when all of the following are present:

1. Dataset class is `LICENSED_EXCHANGE_HISTORY`; vendor and licence identifiers are supplied.
2. Full 64-character SHA-256 is recorded and later matches the file.
3. Canonical CSV passes timestamp, OHLCV, duplicate and ordering validation.
4. A configured, source-reviewed `MarketCalendar` is supplied to the manifest builder; every candle is inside a configured session and no expected intervals are missing.
5. Missing-bar count and duplicate-bar count are both exactly zero. Coverage evidence reference is recorded.
6. Vendor identity, licence, and point-in-time instrument/contract metadata evidence references are recorded.
7. A named reviewer and timezone-aware review timestamp are recorded.
8. Survivorship-bias-free coverage is explicitly attested.

Verification requires the same market calendar to be supplied again. The calendar configuration must be based on the applicable official exchange sessions, holidays and special sessions. The built-in NSE regular-hours baseline is not a complete official holiday feed.

## Important limitation

Evidence references, reviewer identity, licence claims, and survivorship-bias-free claims are operator-supplied metadata. The code validates their presence and the local data checks; it does not authenticate external documents, confirm a vendor contract, or independently prove licensing. A human must inspect the referenced evidence. Dataset promotion remains blocked until this review is complete.

## Safe defaults

`build_manifest_from_csv()` leaves `missing_bars_count=None` and `coverage_verified=false` when no market calendar is supplied. Unknown is not silently converted to zero. Synthetic and unverified datasets can still be used for software smoke tests, but cannot pass the strategy-promotion gate.
