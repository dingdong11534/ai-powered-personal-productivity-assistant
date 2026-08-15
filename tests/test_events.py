"""Tests for app.core.events.EventBus.

Run with: pytest tests/test_events.py -v
"""

from app.core.events import EventBus


def test_subscriber_receives_published_payload():
    bus = EventBus()
    received = []
    bus.subscribe("task.created", lambda payload: received.append(payload))

    bus.publish("task.created", {"task_id": 1})

    assert received == [{"task_id": 1}]


def test_multiple_subscribers_all_receive_event_in_order():
    bus = EventBus()
    order = []
    bus.subscribe("x", lambda p: order.append("first"))
    bus.subscribe("x", lambda p: order.append("second"))

    bus.publish("x")

    assert order == ["first", "second"]


def test_publish_with_no_subscribers_does_not_raise():
    bus = EventBus()
    bus.publish("nobody.listening", {"anything": True})  # should not raise


def test_publish_with_no_payload_passes_empty_dict():
    bus = EventBus()
    received = []
    bus.subscribe("ping", lambda payload: received.append(payload))

    bus.publish("ping")

    assert received == [{}]


def test_unsubscribe_stops_future_calls():
    bus = EventBus()
    received = []

    def handler(payload):
        received.append(payload)

    bus.subscribe("evt", handler)
    bus.unsubscribe("evt", handler)
    bus.publish("evt", {"should": "not appear"})

    assert received == []


def test_subscriber_count_reflects_subscriptions():
    bus = EventBus()
    assert bus.subscriber_count("evt") == 0
    bus.subscribe("evt", lambda p: None)
    assert bus.subscriber_count("evt") == 1
