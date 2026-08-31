"""Annual Events calendar entity."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import SIGNAL_UPDATED
from .helpers import get_policy, local_today
from .manager import AnnualEventsManager
from .models import EventOccurrence


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[AnnualEventsManager],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the single collection calendar."""
    entity = AnnualEventsCalendar(hass, entry.runtime_data)
    async_add_entities([entity])

    @callback
    def handle_update() -> None:
        if entity.hass is not None:
            entity.async_write_ha_state()

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_UPDATED, handle_update))


class AnnualEventsCalendar(CalendarEntity):
    """Expand annual records into all-day calendar events."""

    _attr_has_entity_name = True
    _attr_name = "Annual Events"
    _attr_unique_id = "annual_events_calendar"
    _attr_icon = "mdi:calendar-heart"

    def __init__(self, hass: HomeAssistant, manager: AnnualEventsManager) -> None:
        self._hass_ref = hass
        self._manager = manager

    def _calendar_event(self, occurrence: EventOccurrence) -> CalendarEvent:
        number = (
            f" ({occurrence.occurrence_number})" if occurrence.occurrence_number is not None else ""
        )
        return CalendarEvent(
            start=occurrence.occurrence_date,
            end=occurrence.occurrence_date + timedelta(days=1),
            summary=f"{occurrence.name}{number}",
            description=f"Annual Events category: {occurrence.category or 'uncategorized'}",
            uid=f"{occurrence.event_id}:{occurrence.occurrence_date.isoformat()}",
            recurrence_id=occurrence.occurrence_date.isoformat(),
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next event from in-memory records."""
        occurrence = self._manager.async_get_next(
            local_today(), policy=get_policy(self._hass_ref)
        )
        return self._calendar_event(occurrence) if occurrence else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return expanded events using the calendar API's end-exclusive range."""
        start = start_date.date()
        end = end_date.date()
        if end_date.time() == datetime.min.time():
            end -= timedelta(days=1)
        if end < start:
            return []
        occurrences = self._manager.async_get_occurrences_between(
            start, end, policy=get_policy(hass), limit=5000, enabled_only=True
        )
        return [self._calendar_event(item) for item in occurrences]
