"""Small in-process event bus for decoupled core components."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("event name must not be empty")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


Handler = Callable[[Event], None]


class EventBus:
    """Synchronous event dispatcher; handler failures are visible to callers."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}

    def subscribe(self, event_name: str, handler: Handler) -> Callable[[], None]:
        if not event_name or not event_name.strip():
            raise ValueError("event name must not be empty")
        if not callable(handler):
            raise TypeError("handler must be callable")
        handlers = self._handlers.setdefault(event_name, [])
        if handler not in handlers:
            handlers.append(handler)

        def unsubscribe() -> None:
            current = self._handlers.get(event_name, [])
            if handler in current:
                current.remove(handler)
            if not current:
                self._handlers.pop(event_name, None)

        return unsubscribe

    def publish(self, event: Event) -> int:
        """Dispatch to a snapshot; return the number of handlers called."""
        handlers = tuple(self._handlers.get(event.name, ()))
        for handler in handlers:
            handler(event)
        return len(handlers)

    def subscriber_count(self, event_name: str) -> int:
        return len(self._handlers.get(event_name, ()))
