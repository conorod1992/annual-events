"""Aggregate and optional per-event sensors."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_UPCOMING_DAYS,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    SIGNAL_UPDATED,
)
from .helpers import get_policy, local_today
from .manager import AnnualEventsManager
from .models import AnnualEvent, EventOccurrence


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[AnnualEventsManager],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up aggregate sensors and reconcile optional event entities."""
    manager = entry.runtime_data
    aggregates: list[AnnualEventsBaseSensor] = [
        NextAnnualEventSensor(hass, manager, important_only=False),
        NextAnnualEventSensor(hass, manager, important_only=True),
        NextAnnualEventNameSensor(hass, manager, important_only=False),
        NextAnnualEventNameSensor(hass, manager, important_only=True),
        UpcomingAnnualEventsSensor(hass, entry, manager),
    ]
    async_add_entities(aggregates)
    active: dict[str, AnnualEventSensor] = {}
    reconcile_lock = asyncio.Lock()
    reconcile_tasks: set[asyncio.Task[None]] = set()
    stopped = False

    async def _async_reconcile_once() -> None:
        events = manager.async_list_events()
        existing_ids = {event.id for event in events}
        desired = {event.id: event for event in events if event.enabled and event.expose_entity}

        for event_id, entity in list(active.items()):
            if event_id not in desired:
                active.pop(event_id)
                await entity.async_remove()

        # Registry rows are retained when an event is merely disabled or unexposed so
        # re-enabling preserves entity identity. Once the backing event is deleted,
        # however, remove its registry row even if it was already inactive.
        registry = er.async_get(hass)
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
            if (
                registry_entry.domain != "sensor"
                or registry_entry.platform != DOMAIN
                or not registry_entry.unique_id.startswith("event_")
            ):
                continue
            event_id = registry_entry.unique_id.removeprefix("event_")
            if event_id not in existing_ids:
                registry.async_remove(registry_entry.entity_id)

        new_entities: list[AnnualEventSensor] = []
        for event_id in desired.keys() - active.keys():
            entity = AnnualEventSensor(hass, manager, event_id)
            active[event_id] = entity
            new_entities.append(entity)
        if new_entities:
            async_add_entities(new_entities)
        for aggregate_entity in aggregates:
            if aggregate_entity.hass is not None:
                aggregate_entity.async_write_ha_state()
        for event_entity in active.values():
            if event_entity.hass is not None:
                event_entity.async_write_ha_state()

    async def _async_reconcile_serialized() -> None:
        async with reconcile_lock:
            if stopped:
                return
            await _async_reconcile_once()

    @callback
    def reconcile() -> None:
        """Queue an owned reconciliation task; the lock prevents overlap."""
        if stopped:
            return
        task = hass.async_create_task(
            _async_reconcile_serialized(), "annual_events_reconcile_sensors"
        )
        reconcile_tasks.add(task)
        task.add_done_callback(reconcile_tasks.discard)

    unsubscribe = async_dispatcher_connect(hass, SIGNAL_UPDATED, reconcile)

    @callback
    def async_stop() -> None:
        """Stop accepting updates and cancel queued or in-flight reconciliation."""
        nonlocal stopped
        stopped = True
        unsubscribe()
        for task in tuple(reconcile_tasks):
            task.cancel()
        reconcile_tasks.clear()

    entry.async_on_unload(async_stop)
    await _async_reconcile_serialized()


class AnnualEventsBaseSensor(SensorEntity):
    """Common in-memory sensor behaviour."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, manager: AnnualEventsManager) -> None:
        self._hass_ref = hass
        self._manager = manager

    def _next(self, event: AnnualEvent) -> EventOccurrence:
        return self._manager.next_for_event(event, local_today(), get_policy(self._hass_ref))


class NextAnnualEventSensor(AnnualEventsBaseSensor):
    """Expose the next enabled annual event without an unbounded list."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-arrow-right"

    def __init__(
        self, hass: HomeAssistant, manager: AnnualEventsManager, *, important_only: bool
    ) -> None:
        super().__init__(hass, manager)
        self._important_only = important_only
        self._attr_unique_id = (
            "next_important_annual_event" if important_only else "next_annual_event"
        )
        self._attr_translation_key = self._attr_unique_id

    def _value(self) -> tuple[AnnualEvent, EventOccurrence] | None:
        candidates = [
            (event, self._next(event))
            for event in self._manager.async_list_events()
            if event.enabled and (not self._important_only or event.important)
        ]
        return (
            min(
                candidates,
                key=lambda pair: (pair[1].occurrence_date, pair[0].name.casefold(), pair[0].id),
            )
            if candidates
            else None
        )

    @property
    def native_value(self) -> date | None:
        """Return the next local date."""
        value = self._value()
        return value[1].occurrence_date if value else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return bounded metadata for the single next event."""
        value = self._value()
        if value is None:
            return {}
        event, occurrence = value
        return {
            "event_id": event.id,
            "name": event.name,
            "category": event.category,
            "days_until": (occurrence.occurrence_date - local_today()).days,
            "occurrence_number": occurrence.occurrence_number,
            "important": event.important,
        }


class NextAnnualEventNameSensor(AnnualEventsBaseSensor):
    """Expose the name and bounded metadata of the next enabled event."""

    _attr_icon = "mdi:calendar-text"

    def __init__(
        self, hass: HomeAssistant, manager: AnnualEventsManager, *, important_only: bool
    ) -> None:
        super().__init__(hass, manager)
        self._important_only = important_only
        self._attr_unique_id = (
            "next_important_annual_event_name" if important_only else "next_annual_event_name"
        )
        self._attr_translation_key = self._attr_unique_id

    def _value(self) -> EventOccurrence | None:
        return self._manager.async_get_next(
            local_today(),
            policy=get_policy(self._hass_ref),
            important_only=self._important_only,
        )

    @property
    def native_value(self) -> str | None:
        """Return the next event name."""
        value = self._value()
        return value.name if value else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return bounded metadata for the single next occurrence."""
        value = self._value()
        if value is None:
            return {}
        occurrence_date = value.occurrence_date.isoformat()
        return {
            "event_id": value.event_id,
            "date": occurrence_date,
            "occurrence_date": occurrence_date,
            "days_until": (value.occurrence_date - local_today()).days,
            "category": value.category,
            "occurrence_number": value.occurrence_number,
            "important": value.important,
        }


class UpcomingAnnualEventsSensor(AnnualEventsBaseSensor):
    """Count enabled concrete occurrences in the configured horizon."""

    _attr_icon = "mdi:calendar-multiselect"
    _attr_native_unit_of_measurement = "events"
    _attr_unique_id = "upcoming_annual_events"
    _attr_translation_key = "upcoming_annual_events"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, manager: AnnualEventsManager
    ) -> None:
        super().__init__(hass, manager)
        self._entry = entry

    @property
    def native_value(self) -> int:
        """Return the bounded occurrence count."""
        days = self._entry.options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS)
        return len(
            self._manager.async_get_upcoming(
                local_today(), days=days, policy=get_policy(self._hass_ref), limit=5000
            )
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"period_days": self._entry.options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS)}


class AnnualEventSensor(AnnualEventsBaseSensor):
    """Dynamically exposed sensor for one stable record ID."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, hass: HomeAssistant, manager: AnnualEventsManager, event_id: str) -> None:
        super().__init__(hass, manager)
        self._event_id = event_id
        self._attr_unique_id = f"event_{event_id}"

    @property
    def _event(self) -> AnnualEvent:
        return self._manager.async_get_event(self._event_id)

    @property
    def name(self) -> str:
        return self._event.name

    @property
    def icon(self) -> str:
        return self._event.icon or "mdi:calendar-star"

    @property
    def native_value(self) -> date:
        return self._next(self._event).occurrence_date

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self._event
        occurrence = self._next(event)
        return {
            "event_id": event.id,
            "name": event.name,
            "category": event.category,
            "month": event.month,
            "day": event.day,
            "original_year": event.year,
            "days_until": (occurrence.occurrence_date - local_today()).days,
            "occurrence_number": occurrence.occurrence_number,
            "important": event.important,
            "notes": event.notes,
        }
