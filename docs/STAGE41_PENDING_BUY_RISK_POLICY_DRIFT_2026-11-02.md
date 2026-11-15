# NEXUS TITAN — Stage 41: Pending BUY Risk-Policy Drift Guard

**Scope:** Opt-in Stage40 gateway-only VirtualAccount. This check is
application-level evidence, not a broker-backed or externally signed
trade authorization.

## Problem

Stage35 could calculate an unsigned intent fingerprint, but Stage37/40
did not automatically bind the BUY approval/fill to the risk-policy
configuration captured when the paper order was originally submitted.
A pending order could be approved even after changes to an account's
per-trade risk budget, margin, capital baseline or effective risk-engine
limits. That risks granting an outdated paper order too much exposure.

## New behavior

- Gateway-only BUY records now contain
  `risk_policy_fingerprint: str | None`, a SHA256 of canonical structured
  account ID, configured/running portfolio risk settings, capital baseline,
  manual mode and pretrade-risk flag.
- `VirtualOrder.to_dict/from_dict` persist this fingerprint. The existing
  order approval snapshot hash includes it **when present**. Historic
  legacy orders lacking a fingerprint preserve their original hash exactly.
- Strict gateway-only manual `approve_order` **and** `execute_fill` both
  compare the issued risk snapshot against current policy and reject
  mismatches with `PermissionError` before accepting or charging a BUY.
- Changing local risk percentages, even just the effective internal
  PortfolioRiskManager configuration, or topping up/withdrawing the
  account invalidates pending BUY approval. The operator must cancel and
  reissue under current limits.
- Partial BUY fills remain possible when risk policy is unchanged;
  current exposure/market prices are deliberately not included in this
  **policy fingerprint**, since partial fills naturally change them.
- Owned SELL-to-close and emergency protective SELL remain available
  when risk policy tightens, so risk reduction isn't blocked by stale
  BUY authorization.
- Legacy strict research fixtures (without gateway-only mode) remain
  backwards compatible and don't require a fingerprint.

## Limitations and next gate

The fingerprint is not HMAC, signed, independently witnessed or trusted
against an attacker with runtime code, SQLite or Python object access.
A malicious process can recompute this evidence. This check does not
independently validate source prices, market data timestamps, actual
margin, bid/ask depth or execution costs. Risk should also be
authoritatively re-evaluated against latest portfolio state before
new paper BUY fills in future work; that is not accomplished solely
by a stable policy hash.

Stage40 gateway-only mode remains opt-in and research/VirtualAccount
cash ledgers remain separate and **not atomically reconciled**.

**Release verdict: offline research only. No live broker transmission.**
