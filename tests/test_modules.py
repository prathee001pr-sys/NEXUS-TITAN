import pytest
from nexus_titan.core.modules import ModuleRegistry


def test_module_is_loaded_lazily_and_cached():
    calls = []
    registry = ModuleRegistry()
    registry.register("research", lambda: calls.append("loaded") or object())
    assert calls == []
    first = registry.load("research")
    assert registry.load("research") is first
    assert calls == ["loaded"]


def test_duplicate_registration_and_unknown_module_are_rejected():
    registry = ModuleRegistry()
    registry.register("x", object)
    with pytest.raises(ValueError):
        registry.register("x", object)
    with pytest.raises(KeyError):
        registry.load("missing")


def test_catalog_does_not_load_modules():
    registry = ModuleRegistry()
    registry.register("zeta", object)
    registry.register("alpha", object)
    assert [m.name for m in registry.list_modules()] == ["alpha", "zeta"]
    assert not registry.is_loaded("alpha")
