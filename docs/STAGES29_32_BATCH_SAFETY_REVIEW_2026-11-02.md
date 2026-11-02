# NEXUS TITAN — Stages 29–32 Batch Engineering Review

**2026-11-02 · Four sequential, stacked draft PRs · Research-only**

No real-money orders, broker connections, strategy promotion or auto-merge.
Changes are built on Stage28 draft PR#20, not directly on protected `main`.

## Stage-by-stage delivery and acceptance

| Stage | Draft PR | Concrete change | Acceptance |
| --- | --- | --- | --- |
| 29 | [#21](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/21) | Direct user-set `is_emergency` rejected in VirtualAccount; internal protective SELL close checks current position and same-process provenance; restart of in-flight emergency order fails closed | 919 tests + 5 subtests, three Python versions |
| 30 | [#22](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/22) | Kill switch cancels pending, accepted and **partially filled BUY**; post-kill BUY fill denied even on forged state; emergency SELL close preserved | 928 tests + 5 subtests, three Python versions |
| 31 | [#23](https://github.com/prathee001pr-sys/NEXUS-TITAN/pull/23) | MANUAL_APPROVAL -> AUTO_PAPER requires literal-True identity callback for exact mode-transition action; emergency lock overrides even an approved escalation; tightened manual mode allowed | 940 tests + 5 subtests, three Python versions |
| 32 | New draft PR on Stage31 | Joint read-only preflight for VirtualAccount and Stage28 guarded research ledger. Checks risk flag, manual permission config, flat state, kill switch, virtual cash reconciliation, ledger hash chain and guarded mode. CLI smoke uses **temporary synthetic accounts** | Python CI matrix and CLI regression tests; no external data required |

## Stage32 diagnostic

`src/nexus_titan/shadow/paper_safety_preflight.py` has
`inspect_paper_safety_preflight(virtual, guarded_ledger)`. Its result
`flat_research_gate_passed=True` means a **very narrow flat paper
configuration** cleared conservative checks. It **never** means:

- an external identity provider actually authenticated the user;
- legal NSE data rights, timestamps, market calendar or depth were verified;
- all buy/sell paths are forced through one global order router;
- any broker order was sent or simulated P&L matches executable P&L;
- strategy promotion, production deployment or real-money trading is approved.

`scripts/run_stage32_paper_safety_smoke.py` demonstrates the preflight on
new **temporary** guarded ledger and manual VirtualAccount, with no
external downloads, keys, markets, or changes to an existing account.

## Important engineering limitations (not silently marked complete)

1. VirtualAccount is still an in-process mutable Python simulation. Application
   callers who can change code or private attributes are not cryptographically
   prevented from bypassing safety. The test-level safety checks do not
   replace external broker isolation, real identity or independent policy
   enforcement.
2. Stage28 `DurableResearchShadowLedger` is separate from VirtualAccount;
   even matching account IDs do not imply a single atomic ledger or verified
   reconciliation across both stores.
3. Legacy research accounts intentionally preserve direct Stage19
   `reserve_buy` and `require_pretrade_risk_check=False` test paths.
   Production-like deployment must disable/remove these legacy routes.
4. Stage24 options SELL-to-close, other research adapters and the VirtualAccount
   pipeline are **not globally unified** under one guarded order admission API.
5. Real index/F&O source verification, point-in-time contract metadata, 1-min
   option-chain depth, live feed shadow observation, real order charges and
   expiry/exercise are not verified. Synthetic CI does not establish a profitable
   strategy.
6. No implicit authorization to merge draft branches. Stage32 does not touch
   user-supplied CSV/ZIP uploads, Replit, external market vendors or brokers.

## Next stages (planning only)

Stage33: unify paper-only order-intent admission for opt-in callers.
Stage34: reconcile sell-to-close and no-short inventory with brokerless shadow.
Stage35: risk-config versioning, immutable approval receipts, concurrency
replay/restart security tests. Additional validation and data-integration
stages thereafter. Keep user preference to upload full market data last.

**Release verdict: OFFLINE RESEARCH ONLY; live trading blocked.**
