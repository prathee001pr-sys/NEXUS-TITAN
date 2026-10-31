import pytest

from nexus_titan.core.audit import AuditLedger
from nexus_titan.core.config import Settings
from nexus_titan.core.events import Event
from nexus_titan.core.memory import MemoryEntry, MemoryLayer, SQLiteMemoryStore
from nexus_titan.core.modules import ModuleRegistry
from nexus_titan.core.permissions import Action, Decision
from nexus_titan.core.runtime import CoreRuntime


def test_runtime_wires_events_and_audits_publish():
    runtime = CoreRuntime()
    received = []
    runtime.subscribe("market.snapshot", received.append)
    count = runtime.publish(Event("market.snapshot", {"symbol": "NIFTY"}))
    assert count == 1
    assert len(received) == 1
    assert runtime.audit.records()[-1].action == "event_publish"
    assert runtime.audit.verify()


def test_runtime_records_event_handler_failure_and_reraises():
    runtime = CoreRuntime()

    def fail(_event):
        raise ValueError("handler failed")

    runtime.subscribe("failure", fail)
    with pytest.raises(ValueError):
        runtime.publish(Event("failure"))
    assert runtime.audit.records()[-1].outcome == "failed"
    assert runtime.audit.verify()


def test_runtime_uses_central_permission_policy():
    runtime = CoreRuntime(settings=Settings(paper_trading_enabled=False))
    assert runtime.authorize(Action.READ) is Decision.ALLOW
    assert runtime.authorize(Action.PAPER_TRADE) is Decision.DENY
    assert runtime.authorize(Action.LIVE_TRADE) is Decision.REQUIRES_HUMAN_APPROVAL
    assert runtime.authorize(Action.CHANGE_RISK_CONTROLS) is Decision.REQUIRES_HUMAN_APPROVAL


def test_runtime_paper_trade_is_only_allowed_when_opted_in():
    runtime = CoreRuntime(settings=Settings(paper_trading_enabled=True))
    assert runtime.authorize(Action.PAPER_TRADE) is Decision.ALLOW


def test_runtime_memory_add_is_audited():
    runtime = CoreRuntime()
    entry = MemoryEntry(
        content="test", layer=MemoryLayer.WORKING,
        source="unit-test", confidence=0.8,
    )
    runtime.remember(entry)
    assert runtime.memory.get(entry.memory_id) == entry
    assert runtime.audit.records()[-1].action == "memory_add"


def test_runtime_lazy_loads_registered_modules_and_audits():
    registry = ModuleRegistry()
    registry.register("research", lambda: object())
    runtime = CoreRuntime(modules=registry)
    assert not registry.is_loaded("research")
    loaded = runtime.load_module("research")
    assert loaded is registry.load("research")
    assert registry.is_loaded("research")
    assert runtime.audit.records()[-1].action == "module_load"


def test_runtime_can_use_durable_memory_and_audit(tmp_path):
    memory = SQLiteMemoryStore(str(tmp_path / "memory.sqlite3"))
    audit = AuditLedger(str(tmp_path / "audit.sqlite3"))
    runtime = CoreRuntime(memory=memory, audit=audit)
    entry = MemoryEntry(
        content="durable", layer=MemoryLayer.KNOWLEDGE,
        source="test", confidence=1.0,
    )
    runtime.remember(entry)
    runtime.authorize(Action.READ)
    assert memory.get(entry.memory_id) == entry
    assert audit.verify()
    runtime.close()


def test_closed_runtime_rejects_new_work():
    runtime = CoreRuntime()
    runtime.close()
    with pytest.raises(RuntimeError):
        runtime.authorize(Action.READ)


def test_runtime_does_not_close_injected_persistent_services(tmp_path):
    memory = SQLiteMemoryStore(str(tmp_path / "injected-memory.sqlite3"))
    audit = AuditLedger(str(tmp_path / "injected-audit.sqlite3"))
    runtime = CoreRuntime(memory=memory, audit=audit)

    runtime.close()

    # The caller owns injected services and can continue using them.
    entry = MemoryEntry(
        content="still open", layer=MemoryLayer.WORKING,
        source="ownership-test", confidence=1.0,
    )
    memory.add(entry)
    audit.append(actor="test", action="after_runtime_close", outcome="success")
    assert memory.get(entry.memory_id) == entry
    assert audit.records()[-1].action == "after_runtime_close"
    memory.close()
    audit.close()
