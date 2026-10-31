"""Small lazy module registry for optional TITAN capabilities."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    name: str
    description: str


class ModuleRegistry:
    """Register module factories and instantiate them only when requested."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], Any]] = {}
        self._instances: dict[str, Any] = {}
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, factory: Callable[[], Any], *, description: str = "") -> None:
        if not name or not name.strip():
            raise ValueError("module name must not be empty")
        if name in self._factories:
            raise ValueError(f"module already registered: {name}")
        if not callable(factory):
            raise TypeError("module factory must be callable")
        self._factories[name] = factory
        self._descriptions[name] = description

    def load(self, name: str) -> Any:
        if name not in self._factories:
            raise KeyError(f"module is not registered: {name}")
        if name not in self._instances:
            self._instances[name] = self._factories[name]()
        return self._instances[name]

    def is_loaded(self, name: str) -> bool:
        return name in self._instances

    def list_modules(self) -> tuple[ModuleInfo, ...]:
        return tuple(ModuleInfo(name, self._descriptions[name]) for name in sorted(self._factories))
