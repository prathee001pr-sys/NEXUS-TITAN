# NEXUS TITAN — Stage 13 Specialist Evidence & EVOLVE Governance

**Scope:** additive integration on the verified Stage 12 package. Original Stage 11/12 archives remain unchanged. Research/shadow only; live trading disabled.

## Delivered

1. Added eight explicit specialist evidence lanes: market structure, trend/regime, momentum, volatility, options flow, liquidity/microstructure, event/context, and portfolio risk.
2. Added a strict evidence adapter. Each submitted role must provide a valid action, non-empty rationale, traceable evidence reference, and invalidation condition. Duplicate/unknown roles fail closed. Missing roles are not fabricated.
3. A single directional role cannot create consensus; the adapter adds a HOLD confirmation requirement so consensus waits for independent evidence.
4. Added `MasterTradingOrchestrator.run_cycle_from_evidence()` to connect role evidence to the existing market-state/consensus/risk/red-team/simulator path.
5. Added `GovernedEvolveService` to audit research notes and experiment proposal/approval/start/completion. Human approval is required before start.
6. EVOLVE snapshot explicitly reports code execution, strategy promotion and live trading as disabled. Protected targets remain risk controls, permissions and live trading.
7. Added five Stage 13 regression tests.

## Verification

- Targeted specialist/master/EVOLVE tests: **21 passed**.
- Full suite and advanced backtest evidence are recorded in the Stage 13 package reports.
- No broker connector, real order route, automatic strategy promotion, or generated-code execution was added.

## Important limitations

The eight specialist lanes are contracts/adapters, not eight autonomous agents. Evidence references are caller-supplied and are not cryptographically authenticated. EVOLVE research records and audit ledger are local process state unless a persistent audit database is configured. This stage does not establish statistical strategy performance or production readiness.

## Safety

Authoritative risk remains independent. EVOLVE cannot change risk controls, permissions, or live-trading state. Live orders transmitted: zero.
