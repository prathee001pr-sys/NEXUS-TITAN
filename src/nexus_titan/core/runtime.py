"""Composition root for the lightweight NEXUS TITAN core."""
from collections.abc import Callable
from typing import Any

from nexus_titan.core.audit import AuditLedger
from nexus_titan.core.config import Settings
from nexus_titan.core.events import Event, EventBus
from nexus_titan.core.memory import MemoryEntry, MemoryStore
from nexus_titan.core.modules import ModuleRegistry
from nexus_titan.core.permissions import Action, Decision, decide


class CoreRuntime:
    """Wire core services without importing trading or broker implementations.

    Defaults are owned by this runtime and closed with it. Injected services
    remain caller-owned and are never closed by the runtime.
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
        self.settings = settings if settings is not None else Settings()
        self.events = events if events is not None else EventBus()
        self.memory = memory if memory is not None else MemoryStore()
        self.audit = audit if audit is not None else AuditLedger()
        self.modules = modules if modules is not None else ModuleRegistry()
        self._owns_memory = memory is None
        self._owns_audit = audit is None
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
        """Close only persistent services created and owned by this runtime."""
        if self._closed:
            return
        self._closed = True
        if self._owns_audit:
            close = getattr(self.audit, "close", None)
            if callable(close):
                close()
        if self._owns_memory:
            close = getattr(self.memory, "close", None)
            if callable(close):
                close()
