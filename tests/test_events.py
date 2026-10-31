import pytest

from nexus_titan.core.events import Event, EventBus


def test_publish_delivers_event_to_subscriber():
    bus = EventBus()
    received = []
    bus.subscribe("market.tick", received.append)
    event = Event("market.tick", {"symbol": "NIFTY"})
    assert bus.publish(event) == 1
    assert received == [event]


def test_unsubscribe_stops_future_delivery():
    bus = EventBus()
    received = []
    unsubscribe = bus.subscribe("system.ready", received.append)
    unsubscribe()
    unsubscribe()
    assert bus.publish(Event("system.ready")) == 0
    assert received == []


def test_duplicate_subscription_is_not_added_twice():
    bus = EventBus()
    handler = lambda event: None
    bus.subscribe("x", handler)
    bus.subscribe("x", handler)
    assert bus.subscriber_count("x") == 1


def test_event_payload_is_copied_and_read_only():
    original = {"count": 1}
    event = Event("test.event", original)
    original["count"] = 2
    assert event.payload["count"] == 1
    with pytest.raises(TypeError):
        event.payload["count"] = 3


def test_empty_event_name_is_rejected():
    with pytest.raises(ValueError):
        Event(" ")


def test_handler_failure_is_visible():
    bus = EventBus()

    def fail(event):
        raise RuntimeError("handler failed")

    bus.subscribe("x", fail)
    with pytest.raises(RuntimeError, match="handler failed"):
        bus.publish(Event("x"))
