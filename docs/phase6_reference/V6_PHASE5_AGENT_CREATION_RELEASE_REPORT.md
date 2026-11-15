# V6 Phase 5 Agent Creation Engine — Release Notes

## Scope

The V6 build already contained the initial 12 deterministic TITAN EVOLVE
specialist agents. Phase 5 added the governed Agent Creation Engine (ACE),
integrated it with the Evolution Manager and documented the 12-agent architecture.

## Phase 5 changes

- Declarative agent specs, strict allowlists, non-executable sandbox prototypes,
  validation checks, SQLite proposal store, audit events and permanent registry.
- Evolution Manager can propose a new declarative agent prototype.
- ACE exports are available from `nexus_titan.self_improvement`.
- Focused tests cover safety denials, approval and registry isolation.

## Verification

The uploaded archive's standalone pytest suite previously passed **246 tests**.
The V2 combined integration suite is tracked separately by GitHub Actions.

## Important limitation

ACE creates declarative, non-executable prototypes. It does not run arbitrary
Python, dynamically load code or deploy agents. Permanent registration requires
a named human approval; production authentication (MFA/session binding) remains
a separate requirement.

The project remains a development/research and virtual-trading baseline, not a
live-trading system. Market-data, broker, full options and production deployment
limitations remain.
