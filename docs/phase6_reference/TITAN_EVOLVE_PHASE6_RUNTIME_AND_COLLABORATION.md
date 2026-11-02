# TITAN EVOLVE — Phase 6: Agent Runtime & Collaboration

## Purpose

Phase 5 added a governed Agent Creation Engine (ACE). Phase 6 adds the controlled
runtime that lets a **human-approved** declarative agent specification perform
work through pre-installed tool adapters and coordinate with other approved agents.
It does not execute generated agent source code or grant unrestricted computer access.

## Runtime path

1. ACE validates a proposed agent specification and creates a non-executable prototype.
2. A human reviews and registers the agent in `permanent_agent_registry`.
3. The runtime loads that registered specification and verifies its identity and grants.
4. An operator submits a durable task containing JSON inputs and explicit tool calls.
5. The runtime checks every requested tool against both the agent's granted tools and
   the trusted adapter registry.
6. The task runs with bounded retry only for adapters explicitly marked retry-safe.
7. Outputs, errors, attempts, duration and state transitions are persisted.
8. `AgentWorkflowCoordinator` schedules a dependency graph and delivers upstream
   results through dependency context and an auditable agent inbox.
9. Per-agent task success, failure, latency and attempts are measured.

## Main interfaces

```python
from nexus_titan.self_improvement import (
    AgentRuntime, AgentWorkflowCoordinator, LearningStore, TitanEvolveEngine,
    register_core_local_tools,
)

engine = TitanEvolveEngine(LearningStore("data/titan_learning.db"))
runtime = AgentRuntime(engine.store.db_path)
register_core_local_tools(runtime, engine)

# Then execute tasks from a JSON workflow. All agent IDs must already be approved.
workflow = AgentWorkflowCoordinator(runtime)
result = workflow.execute_workflow(tasks, workflow_id="research-2026-01")
print(result["status"], runtime.metrics())
```

CLI entry point: `scripts/run_agent_runtime.py`. It never approves agents. Its
sample workflow in `examples/agent_workflow.sample.json` uses placeholder agent IDs;
replace them with actual IDs already present in the approved registry.

## Built-in local adapters

- `knowledge_base_read` / `learning_memory_read`: bounded local text search.
- `learning_memory_propose`: records an evidence-tagged learning item.
- `proposal_store`: writes an improvement proposal, not an approved change.
- `agent_status_read`: reads the static 12-agent specialist roster.
- `report_writer`: returns a structured report object in the task result; it does
  not write to an arbitrary path.

Additional adapters such as market data, backtests or QA runners must be implemented
as reviewed host code and registered explicitly. They are not enabled by default.

## Durable state and coordination

SQLite tables:

- `runtime_tasks`: state, inputs, allowlisted calls, outputs, attempts, latency,
  error and idempotency key. `pending_task_ids()` and `run_pending()` provide a
  bounded FIFO local worker interface.
- `runtime_task_events`: append-only task events.
- `agent_messages`: explicit inter-agent handoff messages and inbox consumption state.

Workflow dependencies are validated for unknown nodes and cycles. A failed or blocked
upstream task blocks downstream tasks. A repeated idempotency key returns the existing
task rather than making a duplicate call. On restart, any task found in `RUNNING` is
failed closed and is **not automatically replayed**, because a previous tool may have
completed before the process crashed.

## Security boundaries

- Only `permanent_agent_registry` agents run. Unapproved proposals cannot be scheduled.
- A task tool must be in the approved agent spec and have a trusted runtime adapter.
- Adapter registration accepts only ACE allowlisted tool names.
- No broker orders, live trading, credentials, risk-limit writes, permission admin,
  arbitrary network, shell, filesystem write or self-deployment are allowed.
- No generated Python is imported, evaluated or executed.
- Human approval is represented by ACE's named approver field. Production should
  replace this local name string with authenticated identity, session binding and MFA.
- Tool adapters are trusted host code; review them like privileged application code.

## Measurable performance

`AgentRuntime.metrics()` reports task count, completed/failed count, success rate,
average task duration and tool attempts per agent. These are operational metrics,
not proof that an agent's conclusions are factually correct. Task results still need
acceptance criteria and human review for consequential outcomes.

## Not yet complete

- Process/container isolation for untrusted generated code (intentionally not enabled).
- Authenticated operator identity and per-user ACL on task submission and inbox reads.
- Distributed queue/worker scaling; this phase is single-host SQLite and in-process.
- Automatic code deployment or self-modifying agents; intentionally prohibited.
- Live broker, exchange data and automatic live trading.
