# TITAN EVOLVE — Agent Creation Engine (ACE), Phase 5

## Purpose

ACE extends the fixed 12-specialist TITAN EVOLVE team with a governed way to
identify and propose additional specialist agents. The 12 existing specialists
remain the initial roster; there is no fixed lifetime agent-count ceiling.

## Current implementation

`src/nexus_titan/self_improvement/agent_creation.py` implements:

1. Declarative agent-spec validation (identity, purpose, inputs, outputs,
   capabilities, tools, coordination targets and acceptance criteria).
2. Strict capability/tool allowlists. Broker orders, live trading, risk-limit
   writes, permission administration, credentials, arbitrary network access,
   shell execution, filesystem writes, dynamic code execution and self-deploy
   are prohibited capabilities.
3. A non-executable sandbox prototype with simulated tool calls and a check
   report covering schema, allowlists, coordination targets, acceptance
   criteria and protected permissions.
4. SQLite proposal persistence and immutable-style audit events.
5. A separate permanent registry. Only a sandbox-passed proposal can be
   reviewed; registration requires an explicit boolean decision and named
   human approver. Rejection never adds the agent to the registry.

The Evolution Manager can turn a complete `new_agent_idea` payload into a
sandbox prototype and a normal improvement proposal. Missing fields receive
conservative declarative defaults; unknown tools/capabilities or unsafe
permissions are blocked. Its result is included in the cycle report.

## Critical safety boundary

The sandbox prototype is currently a declarative contract/workflow simulation,
not an operating-system container and not executable Python. ACE does not
generate/import/execute agent code, install packages, access credentials,
connect to brokers, submit orders, alter capital/risk/permissions, or
auto-register a new runtime agent. Human registration records a reviewed
specification only; a separately engineered runtime adapter and deployment
review are required before execution.

Human approver identity is currently a required named string, not cryptographic
account authentication. Production use must connect it to the application's
authenticated identity/session system.

## Example

```python
from nexus_titan.self_improvement import AgentCreationEngine

engine = AgentCreationEngine(
    "data/titan_learning.db",
    existing_agent_ids=("SELF_ANALYSIS", "QUALITY_ASSURANCE", "EVOLUTION_MANAGER"),
)
record = engine.create_prototype({
    "agent_id": "VOLATILITY_RESEARCH",
    "name": "Volatility Research Agent",
    "purpose": "Research volatility regimes and summarize evidence.",
    "capabilities": ["research", "analysis", "reporting"],
    "tools": ["approved_research_sources", "backtest_runner", "report_writer"],
    "inputs": ["approved_market_data"],
    "outputs": ["regime_report"],
    "coordination_with": ["SELF_ANALYSIS", "QUALITY_ASSURANCE"],
    "acceptance_criteria": ["All findings cite evidence."],
})
# After reviewing the sandbox report, an authorized human must decide:
# engine.review_and_register(record.creation_id, approved=True, approved_by="...")
```

## Verification

The integration tests cover successful prototype creation, protected capability
rejection, approval requirements, registry isolation and runtime gate checks.
