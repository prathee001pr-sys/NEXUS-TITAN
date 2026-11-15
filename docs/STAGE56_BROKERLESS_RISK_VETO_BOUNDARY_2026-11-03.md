# NEXUS TITAN — Stage56 Brokerless Risk & Veto Boundary Prototype

**Date:** 2026-11-03  
**Branch:** `feature/stage56-brokerless-risk-veto-boundary-2026-11-03`  
**Base:** Stage55 draft PR #47  
**Scope:** Pure synthetic risk-screening process experiment + read-only legacy API bypass inventory; no execution authorization

## Objective

Stage55 created a one-SQLite synthetic reserve/fill/cancel accounting
proof of concept. Stage56 makes the gap between **locally screening risk**
and **globally enforcing risk** explicit.

An admission process only becomes an independently enforced risk
security boundary when *all* order credentials and order/fill entry
points are held outside mutable strategy Python processes. That requires
an isolated, authenticated execution service whose broker interface
refuses calls without timely, bound risk evidence and human approval
as applicable. Simply importing a Python risk module, running it as
a subprocess, or naming a status "approved" does NOT create a secure
boundary.

This stage intentionally **does not pretend that global risk enforcement
has been achieved**.

## Code delivered

### `src/nexus_titan/operations/brokerless_risk_veto.py`

A deterministic, read-only conservative synthetic BUY screening function:
`inspect_stage56_synthetic_risk(intent, quote, account, policy, now)`.

Inputs are immutable local QA dataclasses:

- `Stage56SyntheticIntent`: bounded request ID, uppercase fictional
  equity-delivery symbol, positive integer quantity, **integer-cent**
  limit and stop prices, explicit fee buffer, BUY only. F&O, options,
  SELL and leverage are unsupported.
- `Stage56SyntheticQuote`: timestamped **untrusted**
  `SYNTHETIC/LOCAL_QA` bid/ask/depth, expected slippage and edge.
- `Stage56SyntheticRiskState`: caller-supplied initial/available/
  already-reserved paper cents, daily loss, drawdown, consecutive
  losses, kill switch and risk-module-health observations. **These
  values are not authenticated or reconciled with Stage43/Stage55 DBs.**
- `Stage56RiskPolicy`: bounded immutable QA risk limits. Default
  screening caps are maximum 20% synthetic notional, 50% existing+new
  reserved, 1% stop-distance exposure, 3% daily loss, 10% drawdown,
  three consecutive losses, spread 40bps, slippage 15bps, quote age
  20s. **These QA defaults are not a trading allocation recommendation.**

The evaluator vetoes invalid/missing/unsafe values, mismatched cash
arithmetic, kill switch, unavailable risk module, daily loss,
drawdown, consecutive losses, quote older than allowed, **any future
quote including microsecond skew**, excessive spread/slippage,
insufficient depth/edge, ask beyond limit, misplaced stop, capital
shortfall, per-order notional, aggregate reservation or stop-risk cap.

No broker, approved trading credential, fill handler, HTTP API,
user approval or account write methods are in this module.

A locally passing `Stage56RiskDecision` means
`local_synthetic_screen_passed=True`, **not** order permission.
`order_submission_authorized`, `synthetic_fill_authorized`,
`trusted_risk_service_boundary_enforced`,
`global_legacy_entrypoints_fenced`, `production_ready` and
`live_trading_enabled` are ALWAYS false. The local hashes are
unkeyed fingerprints of **untrusted** inputs, not signatures or
cryptographic account/quote provenance.

### `scripts/run_stage56_brokerless_risk_gate.py`

A standalone one-shot Python subprocess that accepts exactly one
bounded JSON document over standard input, 16 KiB maximum.

- Requires exact schema-v1 top-level, quote, intent and account keys.
- Rejects unknown/duplicate JSON fields, `NaN` / `Infinity`,
  missing or invalid timestamps, unknown schema and oversized input.
- Always uses a fixed default bounded Stage56 policy in the CLI;
  callers cannot loosen policy through a JSON field.
- Prints only a local screening result; a risk-policy denial exits
  normally but **does not approve an order**. Malformed JSON exits 2
  and prints an explicitly negative fail-closed status.
- No account, broker, approval or internet credentials are loaded.
  Running this subprocess is an isolation *experiment*, **not**
  OS-protected sandbox, privileged daemon, authenticated execution
  gateway or real-money risk-control service.

### `src/nexus_titan/operations/risk_boundary_inventory.py`

Read-only AST review of selected known Python code paths:

- `VirtualAccount.submit_order / approve_order / execute_fill /`
  `cancel_order / emergency_square_off`
- `PaperOnlyDeployment.request_buy / request_sell_to_close`
- `Stage47OfflineRiskVetoEntry.request_buy`
- `Stage48SignedPaperSession.request_synthetic_buy /`
  `approve_pending_buy`
- `Stage49DurablePaperFence.request_first_synthetic_buy`
- `Stage55IsolatedSyntheticExecutionBook.reserve_synthetic_buy /`
  `record_simulated_fill / cancel_unfilled`

It detects missing, renamed, symlinked, malformed or unexpectedly large
reviewed files as **unknown**, never as "secured". Even when all selected
methods are found, `legacy_order_paths_globally_disabled=false` and
`all_execution_paths_proven_fenced=false`. The checker is incomplete
by design: dynamic Python reflection/imports and unreviewed files
are outside its scope.

Stage52 source structural inventory is extended to cover the new
Stage56 policy and audit-report classes; this is still not a formal
security or dependency-graph proof.

### Supporting tests and demo

- `tests/test_stage56_brokerless_risk_veto.py` exercises valid local
  screening with **no order approval**, kill switch, loss limits,
  current drawdown, quote freshness—including fractional seconds—,
  fake real quote sources, invalid F&O proposals, malformed cents/bools,
  capital/reserve caps, slippage/edge, depth and stop-risk limits,
  invalid policy, deterministic local fingerprints, strict JSON
  parser, oversized input, duplicate JSON keys, NaN/Infinity rejection,
  and known direct-order bypass findings.
- `scripts/run_stage56_risk_veto_smoke.py` starts the one-shot local
  evaluator twice with fabricated synthetic input. One passes local
  screening; the kill-switch variant is vetoed. The bypass inventory
  reports old direct Python order/fill paths remain exposed.
  **No orders or paper holds are created in the demo.**

## Supported tests

```bash
python scripts/run_stage56_risk_veto_smoke.py
python -m pytest -q tests/test_stage56_brokerless_risk_veto.py
python -m pytest -q
```

A code test is only verified after final PR-head GitHub Actions
Python 3.11/3.12/3.13 pass. The existing Stage25 offline synthetic
integration test does NOT authenticate live NSE/crypto prices or trading
performance.

## Known blockers — explicit NO-GO for real trading

1. Legacy direct Python order/fill APIs can still bypass this evaluator;
   **there is no unbypassable global Risk & Veto enforcement**.
2. Broker/exchange credentials are not placed behind an independently
   controlled service with OS-level isolation, least privilege, source
   authentication, revocation, TLS/mTLS or hardware-backed key custody.
3. The subprocess accepts untrusted caller statements about quote,
   portfolio capital, realized loss, kill-switch state, risk health
   and simulated market depth. An attacker can forge them.
4. **Stage55's single-db book is isolated** from Stage43 VirtualAccount,
   Stage19 research reservations, Stage49 admission marker and Stage53
   holds. No cross-ledger settlement or global capital authority.
5. Signed HMAC manual tokens from Stage48 prove key possession,
   **not independently authenticated human identity**; execution
   approval/recheck and revocation are separate work.
6. Protected emergency exits and genuine cancel/reconciliation must
   not be accidentally blocked when eventually hardening BUY admission.
7. Real licensed point-in-time NIFTY/BANKNIFTY futures and options,
   authentic fees, lot and margin rules, realistic shadow records,
   execution slippage and daily P&L drawdown have not been validated.
8. Prior draft PR stacks remain unmerged and require owner semantic
   reconciliation, branch/ruleset review and prospective integrated CI.
9. Exact user-approved digital-human TITAN face asset is still pending
   frontend integration; do not substitute a new image.

## Stage57 proposed next

Implement a *separate synthetic identity/approval threat-model and
revocation proof*, without issuing real credentials. Then design how
a trusted execution process must verify identity, policy/quote digest,
expiry, one-time nonce and fill-time risk against one authoritative
capital source. Do not connect any existing broker or unlock real
trading by turning on a code flag.

**All orders and production permissions remain disabled. Keep this PR
DRAFT and UNMERGED pending owner review.**
