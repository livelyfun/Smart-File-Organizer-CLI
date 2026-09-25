"""Thread-safe event bus for the shared application layer.

Frontends subscribe to events published by the application services.
"""

from __future__ import annotations

import sys
import threading
from typing import Callable, List

from smart_organizer.application.services.events import OrganizerEvent

EventCallback = Callable[[OrganizerEvent], None]


class EventBus:
    """Simple synchronous publish/subscribe bus with listener error isolation."""

    def __init__(self) -> None:
        self._subscribers: List[EventCallback] = []
        self._lock = threading.Lock()

    def subscribe(self, callback: EventCallback) -> None:
        """Registers a listener; does nothing if it is already registered."""
        with self._lock:
            if callback not in self._subscribers:
                self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        """Removes a previously registered listener."""
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def publish(self, event: OrganizerEvent) -> None:
        """Dispatches an event to all listeners synchronously.

        Listener exceptions are isolated and reported to stderr so a faulty
        frontend can never break the organizing pipeline.
        """
        with self._lock:
            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(event)
            except Exception as exc:  # noqa: BLE001 - intentional isolation
                sys.stderr.write(
                    f"[event-bus] subscriber {getattr(callback, '__name__', callback)!r} "
                    f"raised an error while handling {event.name}: {exc}\n"
                )