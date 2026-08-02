"""Concurrency-safe in-memory annual event manager."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Callable
from datetime import date
from typing import Any, Protocol

from .calculations import LeapDayPolicy, next_occurrence, occurrences_between, search_events
from .models import (
    AnnualEvent,
    DuplicateEventIdError,
    EventNotFoundError,
    EventOccurrence,
    EventValidationError,
)

_LOGGER = logging.getLogger(__name__)


class StorageProtocol(Protocol):
    """Storage interface used by the manager and tests."""

    async def async_load(self) -> list[dict[str, Any]]: ...
    async def async_save(self, records: list[dict[str, Any]]) -> None: ...


class AnnualEventsManager:
    """Own the collection and make mutations atomic."""

    def __init__(self, storage: StorageProtocol, notify: Callable[[], None]) -> None:
        self._storage = storage
        self._notify = notify
        self._events: dict[str, AnnualEvent] = {}
        self._lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load stored events once, skipping malformed individual records."""
        raw_records = await self._storage.async_load()
        loaded: dict[str, AnnualEvent] = {}
        invalid = 0
        for record in raw_records:
            try:
                event = AnnualEvent.from_dict(record)
                if event.id in loaded:
                    raise DuplicateEventIdError("duplicate stored event id")
                loaded[event.id] = event
            except (EventValidationError, TypeError, AttributeError):
                invalid += 1
        if invalid:
            _LOGGER.error(
                "Annual Events storage contains %d malformed record(s); valid records remain available",
                invalid,
            )
        self._events = loaded

    def _snapshot(self) -> list[dict[str, Any]]:
        return [
            event.to_dict() for event in sorted(self._events.values(), key=lambda item: item.id)
        ]

    async def _persist_and_notify(self) -> None:
        await self._storage.async_save(self._snapshot())
        self._notify()

    async def async_create_event(self, data: dict[str, Any]) -> AnnualEvent:
        """Create and persist one event."""
        event = AnnualEvent.create(data)
        async with self._lock:
            if event.id in self._events:
                raise DuplicateEventIdError(f"event id already exists: {event.id}")
            self._events[event.id] = event
            try:
                await self._persist_and_notify()
            except Exception:
                self._events.pop(event.id, None)
                raise
        return event

    async def async_update_event(self, event_id: str, changes: dict[str, Any]) -> AnnualEvent:
        """Apply only explicit fields and persist."""
        async with self._lock:
            old = self._events.get(event_id)
            if old is None:
                raise EventNotFoundError(event_id)
            new = old.updated(changes)
            self._events[event_id] = new
            try:
                await self._persist_and_notify()
            except Exception:
                self._events[event_id] = old
                raise
        return new

    async def async_delete_event(self, event_id: str) -> AnnualEvent:
        """Delete exactly one record by ID."""
        async with self._lock:
            old = self._events.get(event_id)
            if old is None:
                raise EventNotFoundError(event_id)
            del self._events[event_id]
            try:
                await self._persist_and_notify()
            except Exception:
                self._events[event_id] = old
                raise
        return old

    def async_get_event(self, event_id: str) -> AnnualEvent:
        """Return one immutable event."""
        event = self._events.get(event_id)
        if event is None:
            raise EventNotFoundError(event_id)
        return event

    def async_list_events(self) -> list[AnnualEvent]:
        """Return a deterministic immutable-record snapshot."""
        return sorted(self._events.values(), key=lambda item: (item.name.casefold(), item.id))

    def async_search_events(
        self,
        query: str,
        *,
        limit: int = 50,
        category: str | None = None,
        enabled: bool | None = None,
    ) -> list[AnnualEvent]:
        """Search and optionally filter records."""
        events = [
            event
            for event in self._events.values()
            if (category is None or event.category == category)
            and (enabled is None or event.enabled is enabled)
        ]
        return search_events(events, query, limit)

    def async_get_upcoming(
        self,
        today: date,
        *,
        days: int,
        policy: LeapDayPolicy,
        limit: int = 100,
        category: str | None = None,
        important_only: bool = False,
        enabled_only: bool = True,
    ) -> list[EventOccurrence]:
        """Return sorted occurrences within a day horizon."""
        from datetime import timedelta

        return self.async_get_occurrences_between(
            today,
            today + timedelta(days=days),
            policy=policy,
            limit=limit,
            category=category,
            important_only=important_only,
            enabled_only=enabled_only,
        )

    def async_get_occurrences_between(
        self,
        start: date,
        end: date,
        *,
        policy: LeapDayPolicy,
        limit: int = 5000,
        category: str | None = None,
        important_only: bool = False,
        enabled_only: bool = True,
    ) -> list[EventOccurrence]:
        """Expand filtered annual records into concrete occurrences."""
        selected = [
            event
            for event in self._events.values()
            if (category is None or event.category == category)
            and (not important_only or event.important)
            and (not enabled_only or event.enabled)
        ]
        if not enabled_only:
            selected = [
                event
                if event.enabled
                else AnnualEvent.from_dict({**event.to_dict(), "enabled": True})
                for event in selected
            ]
        return occurrences_between(selected, start, end, policy)[:limit]

    def next_for_event(
        self, event: AnnualEvent, today: date, policy: LeapDayPolicy
    ) -> EventOccurrence:
        """Return the next occurrence for an event."""
        return next_occurrence(event, today, policy)

    def diagnostics_counts(self) -> dict[str, Any]:
        """Return aggregate-only, privacy-safe counts."""
        events = list(self._events.values())
        return {
            "event_count": len(events),
            "enabled_count": sum(event.enabled for event in events),
            "important_count": sum(event.important for event in events),
            "exposed_entity_count": sum(event.expose_entity for event in events),
            "category_counts": dict(
                sorted(Counter(event.category or "uncategorized" for event in events).items())
            ),
        }
