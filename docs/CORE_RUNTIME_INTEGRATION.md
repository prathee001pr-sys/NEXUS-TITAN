# Core Runtime Integration

The `CoreRuntime` composition root wires existing Core services:
configuration, in-process events, memory, audit ledger, module registry, and
the central permission policy.

## Guarantees
- Services can be injected, including SQLite-backed memory and audit stores.
- Event publication records success or failure in the audit ledger.
- Permission checks use the existing conservative policy.
- Paper trading remains opt-in; live trading and changes to risk controls or
  permissions still require separate human approval.
- Modules remain lazy-loaded.
- No broker, exchange, market-data, order, or Telegram client is imported.

## Lifecycle
Create one runtime at application startup, inject durable stores when needed,
subscribe event handlers, and close it during orderly shutdown. In-memory
defaults are for tests and development only. The caller owns injected services;
the runtime closes the services passed to it in this initial implementation.

This is an orchestration foundation, not production readiness. It does not
provide multi-process coordination, transactional outbox delivery, or crash
recovery for in-flight event handlers.
