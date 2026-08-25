"""Tests for sensor and calendar projections."""

from datetime import UTC, date, datetime

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.calendar import AnnualEventsCalendar
from custom_components.annual_events.const import DOMAIN
from custom_components.annual_events.manager import AnnualEventsManager
from custom_components.annual_events.sensor import (
    AnnualEventSensor,
    NextAnnualEventNameSensor,
    NextAnnualEventSensor,
)

from .conftest import MemoryStorage, event_data


async def prepare(hass):
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"leap_day_policy": "feb_28"})
    entry.runtime_data = manager
    entry.add_to_hass(hass)
    return manager


async def test_aggregate_sensor_state_and_attributes(hass, freezer):
    freezer.move_to("2026-08-01 12:00:00+00:00")
    manager = await prepare(hass)
    event = await manager.async_create_event(event_data(year=2000, important=True))
    sensor = NextAnnualEventSensor(hass, manager, important_only=False)
    assert sensor.native_value == date(2026, 8, 7)
    assert sensor.extra_state_attributes == {
        "event_id": event.id,
        "name": "Mum's birthday",
        "category": "birthday",
        "days_until": 6,
        "occurrence_number": 26,
        "important": True,
    }

    name_sensor = NextAnnualEventNameSensor(hass, manager, important_only=False)
    assert name_sensor.native_value == "Mum's birthday"
    assert name_sensor.extra_state_attributes == {
        "event_id": event.id,
        "date": "2026-08-07",
        "occurrence_date": "2026-08-07",
        "days_until": 6,
        "category": "birthday",
        "occurrence_number": 26,
        "important": True,
    }


async def test_important_name_sensor_filters_and_empty_state(hass, freezer):
    freezer.move_to("2026-08-01 12:00:00+00:00")
    manager = await prepare(hass)
    await manager.async_create_event(event_data(name="Ordinary", day=2))
    important = await manager.async_create_event(
        event_data(name="Important", day=3, important=True)
    )
    sensor = NextAnnualEventNameSensor(hass, manager, important_only=True)
    assert sensor.native_value == "Important"
    assert sensor.extra_state_attributes["event_id"] == important.id
    await manager.async_update_event(important.id, {"enabled": False})
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


async def test_individual_sensor_unique_id_survives_rename(hass, freezer):
    freezer.move_to("2026-08-01 12:00:00+00:00")
    manager = await prepare(hass)
    event = await manager.async_create_event(event_data(expose_entity=True))
    sensor = AnnualEventSensor(hass, manager, event.id)
    unique_id = sensor.unique_id
    await manager.async_update_event(event.id, {"name": "Renamed birthday"})
    assert sensor.unique_id == unique_id == f"event_{event.id}"
    assert sensor.name == "Renamed birthday"
    assert sensor.native_value == date(2026, 8, 7)


async def test_calendar_range_expands_all_day_events(hass):
    manager = await prepare(hass)
    event = await manager.async_create_event(event_data(name="New year", month=1, day=1, year=2020))
    calendar = AnnualEventsCalendar(hass, manager)
    results = await calendar.async_get_events(
        hass,
        datetime(2026, 12, 30, tzinfo=UTC),
        datetime(2028, 1, 2, tzinfo=UTC),
    )
    assert [item.start for item in results] == [date(2027, 1, 1), date(2028, 1, 1)]
    assert results[0].end == date(2027, 1, 2)
    assert results[0].uid == f"{event.id}:2027-01-01"
    assert results[0].all_day is True
