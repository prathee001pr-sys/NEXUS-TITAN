"""Composition root for the lightweight NEXUS TITAN core."""
from collections.abc import Callable, Mapping
from typing import Any

from nexus_titan.core.audit import AuditLedger
from nexus_titan.core.config import Settings
from nexus_titan.core.events import Event, EventBus
from nexus_titan.core.memory import MemoryEntry, MemoryStore
from nexus_titan.core.modules import ModuleRegistry
from nexus_titan.core.permissions import Action, Decision, decide


class CoreRuntime:
    """Wire core services without importing trading or broker implementations.

    Defaults are in-memory and suitable for tests/development. Applications
    may inject durable stores and a configured audit ledger at construction.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        events: EventBus | None = None,
        memory: Any | None = None,
        audit: AuditLedger | None = None,
        modules: ModuleRegistry | None = None,
    ) -> None:
        self.settings = settings or Settings()
        self.events = events or EventBus()
        self.memory = memory or MemoryStore()
        self.audit = audit or AuditLedger()
        self.modules = modules or ModuleRegistry()
        self._closed = False

    def authorize(self, action: Action) -> Decision:
        """Evaluate an action using the central conservative permission policy."""
        self._ensure_open()
        decision = decide(
            action,
            paper_trading_enabled=self.settings.paper_trading_enabled,
        )
        self.audit.append(
            actor="core",
            action="permission_check",
            outcome=decision.value,
            details={"requested_action": action.value},
        )
        return decision

    def publish(self, event: Event) -> int:
        """Publish an internal event and audit success or handler failure."""
        self._ensure_open()
        try:
            delivered = self.events.publish(event)
        except Exception as exc:
            self.audit.append(
                actor="core",
                action="event_publish",
                outcome="failed",
                details={
                    "event_id": event.event_id,
                    "event_name": event.name,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        self.audit.append(
            actor="core",
            action="event_publish",
            outcome="success",
            details={
                "event_id": event.event_id,
                "event_name": event.name,
                "handler_count": delivered,
            },
        )
        return delivered

    def remember(self, entry: MemoryEntry) -> None:
        self._ensure_open()
        self.memory.add(entry)
        self.audit.append(
            actor="core",
            action="memory_add",
            outcome="success",
            details={"memory_id": entry.memory_id, "layer": entry.layer.value},
        )

    def load_module(self, name: str) -> Any:
        self._ensure_open()
        module = self.modules.load(name)
        self.audit.append(
            actor="core",
            action="module_load",
            outcome="success",
            details={"module_name": name},
        )
        return module

    def subscribe(self, event_name: str, handler: Callable[[Event], None]) -> Callable[[], None]:
        self._ensure_open()
        return self.events.subscribe(event_name, handler)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("core runtime is closed")

    def close(self) -> None:
        """Close owned persistent services; injected services remain caller-owned."""
        if self._closed:
            return
        self._closed = True
        close = getattr(self.audit, "close", None)
        if callable(close):
            close()
        close = getattr(self.memory, "close", None)
        if callable(close):
            close()
