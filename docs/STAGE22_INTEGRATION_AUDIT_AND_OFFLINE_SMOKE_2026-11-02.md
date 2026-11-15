# Stage 22 — Integration Audit and Synthetic Offline E2E Smoke

## Scope and starting point

This stage is deliberately **integration work, not another trading agent**.
It exercises the existing Stage 7–21 research components together, without
rewriting or replacing any existing module.

Run from the repository root (Python 3.11+):

```bash
python scripts/run_stage22_research_smoke.py
python -m pytest -q tests/test_stage22_offline_integration.py
python scripts/run_project_validation.py
```

The first command creates a unique temporary workspace; it removes the
generated SQLite and synthetic CSV fixtures after displaying a JSON report.
It does not contact a broker, request NSE quotes, use credentials, place
orders, modify the user account or change trading permissions.

## Integration trace (real module calls, synthetic inputs)

| Stage | Input / contract | Exercise and assertion |
|---|---|---|
| PR #7 | Strict CSV with separately calculated SHA-256 | `load_research_option_chain_csv` / no release on mismatched hash |
| PR #8 | Validated option snapshot + explicit session calendar | `assemble_research_option_chain_history`, no gaps in covered synthetic window |
| PR #9 | Matching CE quote + **independent synthetic displayed depth** | `simulate_historical_option_fill`: whole-lot fill/partial/no-fill, indicative fees |
| PR #10 | Simulated fragment with exact order residual | `reconcile_options_research_order` via Stage19 settlement |
| PR #11 | Configurable research capital + source declarations | SQLite reservation, settlement, stable cash/inventory, replay/restart checks |
| PR #12 | Research ledger state and day-close record | Independent SQLite-backup reopen + one-day structural audit |
| PR #13 | Day-close, local recovery, operator-supplied evidence | `prepare_unified_shadow_readiness` remains BLOCKED, never live-approved |
| Stage 22 | Whole workflow | Runnable CLI + pytest subprocess and negative-path integration tests |

All exchange names/prices in the synthetic fixture are arbitrary regression
samples. Even a source flag set to `source_verified=True` is only a test
declaration. The example performs **one synthetic day** and no actual closed
round-trip trade. The readiness decision therefore remains
`BLOCKED_STRUCTURAL_VALIDATION` with default minimum 20 sessions / 30
closed trades. This is expected and desirable.

## Guardrails exercised end-to-end

- Changed CSV bytes / hash mismatch block processing **before** creating a
  virtual ledger. Invalid displayed depth cannot create a simulated position.
- Missing displayed ask liquidity gives an `UNFILLED` order with **no**
  charges or position. Partial depth produces whole-lot partial execution.
- Virtual capital is configurable (e.g. ₹23,000 / ₹50,000), **not fixed**.
  Insufficient unreserved cash cannot be spent or reserved.
- Settlement never leaves phantom open reservations, and recovery reports must
  match the persisted SQLite state. Reusing an order ID after restart fails.
- Existing local files are never intentionally overwritten by the example.
- No real orders transmitted; no automatic promotion or external market-data
  verification is claimed or implied.

## Audit findings: not yet connected / verified

**Critical release blockers**

1. Draft upstream PR stack (#6 through #13) remains unmerged; the current
   integration branch is *not* the deployed `main` branch.
2. The shadow-research BUY-only ledger bypasses the **authoritative pretrade
   Risk & Veto admission path by design**. It must not be misrepresented as
   a risk-authorized trading runtime. A future integration gate must require
   independent risk decisions and permission checks before production paper
   order admission.
3. Official/licensed **real** NIFTY/BANKNIFTY minute option-chain data, true
   point-in-time metadata, exchange holiday exceptions, and genuine top-book
   depth remain unverified.
4. Actual broker fee schedules, timestamps/queue/partial fill calibration,
   margin/SPAN/ELM, order lifecycle, sell-side closing trades, expiry/
   exercise handling, and realized P&L are not integrated end-to-end.
5. Multi-day real-feed shadow results, external security review, offsite
   encrypted restore, operator signoff and full regression release approvals
   remain outstanding.

**Engineering integration still needed**

- Supervised, data-licensed feed import with session, checksum and schema
  lineage; explicit data rights and observed market-data clock synchronization.
- A **separate, human-reviewed paper-only** adapter that cannot be activated
  by self-declared evidence and preserves independent Risk & Veto controls.
- Full trade lifecycle and position accounting with authoritative broker-like
  paper reconciliation, then multi-day reproducible scorecards.
- UI wiring to the locked black-and-silver dashboard **after** API contracts
  and release/paper safety boundaries have been verified.
- Draft PR stack review and merge sequencing with protected `main`, rollback
  and an operator-controlled deployment process.

## What passing tests do—and don't—mean

Passing Stage22 tests validates a deterministic offline integration route
across already built modules, plus its tested fail-closed cases. It **does
not** validate profitability, NSE market-data authenticity, execution
realism, strategy quality, exchange compliance or live-trading readiness.
The smoke output always asserts `live_trading_enabled=false` and
`automatic_strategy_promotion=false`.
