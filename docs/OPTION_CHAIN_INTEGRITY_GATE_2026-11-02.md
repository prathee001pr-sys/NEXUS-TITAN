# Option Chain Integrity Gate — research-only increment (2026-11-02)

## Added API

`nexus_titan.derivatives.chain_integrity.inspect_verified_option_chain`
checks a **single** synchronized option-chain snapshot, using existing
`OptionChainQuote`, existing row-level `inspect_option_chain_snapshot`,
and injected `PointInTimeContractSpec` metadata.

The function rejects:
- Empty, malformed, naive, future, or stale quotes and excessive snapshot time skew.
- Mixed symbol/underlying/expiry, duplicate contract-side/strike, missing CE/PE pairs.
- Quote lot-size discrepancies, invalid strike steps and off-grid strike/premium prices.
- Inconsistent spot references across quote rows.
- Expired or out-of-effective-window contract metadata.
- Missing `source_verified=True` / source reference **declarations**.

Expiry and metadata effective dates are compared using **Asia/Kolkata** calendar
dates; historical quote timestamps can use any explicit timezone offset.

### Example (research fixture, not a licensed NSE dataset)

```python
from datetime import datetime
from nexus_titan.derivatives.chain_integrity import inspect_verified_option_chain

# quotes: 2+ OptionChainQuote objects (matching CE/PE strike).
# contract: injected PointInTimeContractSpec for this exact symbol/expiry,
#           with independently reviewed official exchange metadata.
report = inspect_verified_option_chain(
    quotes, contract,
    observed_at=datetime.fromisoformat("2026-11-02T09:16:00+05:30"),
)
if not report.is_valid:
    raise ValueError("Reject option chain: " + "; ".join(report.issues))
```

## Explicit limits

1. This API is an **opt-in validator**. It is *not yet wired into* the trading
   engine, backtest promotion gates, shadow trading or execution.
2. `source_verified=True` and an evidence reference are caller assertions; no
   official NSE identity, licensing, digital signature or exchange provenance is
   independently authenticated by this module.
3. Quote freshness default is 120 seconds, max inter-quote time skew 2 seconds,
   maximum spot dispersion 0.5%; adjust only with documented evidence.
4. Tick/strike grids come from an injected contract and are **not** fetched from
   official exchange records. No regulatory constants were updated.
5. A structurally valid snapshot is not evidence of executable fills, sufficient
   liquidity, profitable strategies, or a production-ready system.
6. Risk and Veto logic, production permissions, main branch and live-trading
   disabled boundary remain unchanged.

## Follow-on checks before integration

- Connect authentic point-in-time contract master and per-provider data lineage.
- Add provider-source authentication, synchronized collector watermarking,
  and partial option-chain completeness requirements.
- Integrate this gate into an explicit fail-closed pre-research workflow,
  with audited evidence and rollback/kill-switch checks.
- Run exchange/broker-calibrated spread, latency, fees, liquidity and margin
  simulation, then multi-day paper validation. No live broker orders.
