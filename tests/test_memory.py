from datetime import datetime
import pytest
from nexus_titan.core.memory import MemoryEntry, MemoryLayer, MemoryStore


def make_entry(layer=MemoryLayer.WORKING, **kwargs):
    return MemoryEntry("Test memory", layer, "unit-test", 0.9, **kwargs)


def test_memory_entry_records_metadata():
    entry = make_entry(MemoryLayer.KNOWLEDGE)
    assert entry.layer is MemoryLayer.KNOWLEDGE
    assert entry.source == "unit-test"
    assert entry.confidence == 0.9
    assert entry.created_at.tzinfo is not None


def test_store_add_get_and_filter():
    store = MemoryStore()
    working, knowledge = make_entry(), make_entry(MemoryLayer.KNOWLEDGE)
    store.add(working)
    store.add(knowledge)
    assert store.get(working.memory_id) == working
    assert store.list(layer=MemoryLayer.KNOWLEDGE) == (knowledge,)
    assert store.count() == 2


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_invalid_confidence_is_rejected(confidence):
    with pytest.raises(ValueError):
        make_entry(confidence=confidence)


def test_empty_content_source_and_naive_timestamp_are_rejected():
    with pytest.raises(ValueError):
        MemoryEntry("", MemoryLayer.WORKING, "test", 0.5)
    with pytest.raises(ValueError):
        MemoryEntry("content", MemoryLayer.WORKING, " ", 0.5)
    with pytest.raises(ValueError):
        make_entry(created_at=datetime(2026, 1, 1))


def test_duplicate_memory_id_is_rejected():
    store, entry = MemoryStore(), make_entry()
    store.add(entry)
    with pytest.raises(ValueError):
        store.add(entry)
