"""
In-process event bus.

WHAT THIS DOES
---------------
A minimal synchronous publish/subscribe mechanism. Modules can `subscribe`
a callback to a named event, and any module can `publish` that event with
a payload; every subscriber is called in registration order.

WHY IT EXISTS
-------------
Several features described in the project spec are naturally reactions to
something else happening, not independent logic:
- completing a task should be able to trigger a notification
- creating a task should be able to append an ActivityLog entry
- a habit completion should be able to update streak statistics

Without an event bus, that wiring tends to happen by having e.g. the task
service directly import and call the notification service, which quietly
turns "tasks" into a module that knows about "notifications", "logging",
and eventually everything else. The event bus lets `tasks` stay ignorant
of who's listening — it just announces "a task was completed" — which
keeps modules independently testable and lets Phase 2+ features (logging,
notifications, stats) be added without editing Phase 1 code.

This is deliberately NOT a message queue, async framework, or third-party
library. For a single local process, an in-memory synchronous bus is the
simplest thing that solves the actual problem. If the project later needs
cross-process events (it shouldn't, given the "local PC app" scope), that
would be a deliberate, explained architectural change — not a default.

HOW DATA FLOWS
---------------
subscribe("task.completed", handler) stores handler in a dict keyed by
event name -> publish("task.completed", payload) looks up that key and
calls each stored handler with payload, in order, synchronously ->
publish returns only after every handler has run.

IMPORTANT DESIGN DECISIONS
----------------------------
- Synchronous and in-order: a handler that raises will stop later handlers
  from running for that publish() call. This is intentional for now: it
  surfaces bugs immediately during development instead of swallowing them.
  Revisit if/when a handler's failure shouldn't be allowed to block others.
- No wildcard subscriptions, no priorities, no async support yet. Adding
  those before there's a concrete need would be speculative complexity.

HOW TO TEST
------------
See tests/test_events.py. Because this module has no dependencies (not
even on app.core.config), it can be tested with plain pytest and no
fixtures, database, or app context.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

EventHandler = Callable[[dict[str, Any]], None]


class EventBus:
    """A synchronous, in-process publish/subscribe event bus."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register `handler` to be called whenever `event_name` is published."""
        self._subscribers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: EventHandler) -> None:
        """Remove a previously registered handler.

        Raises ValueError if the handler was never subscribed to this event,
        matching list.remove()'s behavior — silent no-ops tend to hide bugs
        where the caller expected the unsubscribe to matter.
        """
        self._subscribers[event_name].remove(handler)

    def publish(self, event_name: str, payload: dict[str, Any] | None = None) -> None:
        """Call every handler subscribed to `event_name` with `payload`."""
        for handler in self._subscribers.get(event_name, []):
            handler(payload or {})

    def subscriber_count(self, event_name: str) -> int:
        """Number of handlers currently subscribed to `event_name` (test helper)."""
        return len(self._subscribers.get(event_name, []))


# Process-local audit seam for operations that do not have a database record of
# their own (such as workspace files). Subscribers may persist or display these
# events without coupling the file service to a storage implementation.
file_events = EventBus()
