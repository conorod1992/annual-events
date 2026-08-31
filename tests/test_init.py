"""End-to-end config entry setup and unload tests."""

import asyncio
from unittest.mock import AsyncMock

from homeassistant.components import frontend
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events import async_unload_entry
from custom_components.annual_events.const import DOMAIN, PANEL_URL
from custom_components.annual_events.sensor import AnnualEventSensor


async def test_setup_and_unload_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert frontend.async_panel_exists(hass, PANEL_URL)
    assert hass.services.has_service(DOMAIN, "create_event")
    assert hass.states.get("sensor.next_annual_event") is not None
    assert hass.states.get("sensor.next_important_annual_event") is not None
    assert hass.states.get("sensor.next_annual_event_name") is not None
    assert hass.states.get("sensor.next_important_annual_event_name") is not None
    assert hass.states.get("sensor.upcoming_annual_events") is not None
    assert hass.states.get("calendar.annual_events") is not None

    created = await hass.services.async_call(
        DOMAIN,
        "create_event",
        {
            "name": "Exposed birthday",
            "month": 8,
            "day": 7,
            "enabled": True,
            "expose_entity": True,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    event_id = created["event"]["id"]
    registry = er.async_get(hass)
    sensor_id = registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}")
    assert sensor_id is not None
    assert hass.states.get(sensor_id) is not None

    await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event_id, "name": "Renamed birthday", "expose_entity": False},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id).state == "unavailable"
    assert registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}") == sensor_id

    await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event_id, "expose_entity": True},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}") == sensor_id
    assert hass.states.get(sensor_id) is not None

    await hass.services.async_call(
        DOMAIN,
        "delete_event",
        {"event_id": event_id},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}") is None

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not frontend.async_panel_exists(hass, PANEL_URL)
    assert not hass.services.has_service(DOMAIN, "create_event")


async def test_delete_unexposed_event_removes_orphan_registry_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    created = await hass.services.async_call(
        DOMAIN,
        "create_event",
        {
            "name": "Temporary birthday",
            "month": 8,
            "day": 7,
            "enabled": True,
            "expose_entity": True,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    event_id = created["event"]["id"]
    registry = er.async_get(hass)
    sensor_id = registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}")
    assert sensor_id is not None

    await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event_id, "expose_entity": False},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}") == sensor_id
    assert hass.states.get(sensor_id).state == "unavailable"

    await hass.services.async_call(
        DOMAIN,
        "delete_event",
        {"event_id": event_id},
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}") is None


async def test_failed_platform_unload_keeps_panel_and_services(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    original_unload_platforms = hass.config_entries.async_unload_platforms
    failed_unload = AsyncMock(return_value=False)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", failed_unload)

    assert not await async_unload_entry(hass, entry)
    assert frontend.async_panel_exists(hass, PANEL_URL)
    assert hass.services.has_service(DOMAIN, "create_event")
    failed_unload.assert_awaited_once()

    monkeypatch.setattr(
        hass.config_entries,
        "async_unload_platforms",
        original_unload_platforms,
    )
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_rapid_exposure_updates_do_not_overlap_reconciliation(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    created_entities = []
    original_init = AnnualEventSensor.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        created_entities.append(self)

    remove_started = asyncio.Event()
    release_remove = asyncio.Event()
    original_remove = AnnualEventSensor.async_remove

    async def slow_remove(self, *args, **kwargs):
        remove_started.set()
        await release_remove.wait()
        await original_remove(self, *args, **kwargs)

    monkeypatch.setattr(AnnualEventSensor, "__init__", tracking_init)
    monkeypatch.setattr(AnnualEventSensor, "async_remove", slow_remove)

    created = await hass.services.async_call(
        DOMAIN,
        "create_event",
        {
            "name": "Rapid toggle birthday",
            "month": 8,
            "day": 7,
            "enabled": True,
            "expose_entity": True,
        },
        blocking=True,
        return_response=True,
    )
    await hass.async_block_till_done()
    event_id = created["event"]["id"]
    registry = er.async_get(hass)
    sensor_id = registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}")
    assert sensor_id is not None
    assert len(created_entities) == 1

    await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event_id, "expose_entity": False},
        blocking=True,
        return_response=True,
    )
    await remove_started.wait()

    await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event_id, "expose_entity": True},
        blocking=True,
        return_response=True,
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # A second entity must not be created until the first removal has completed.
    assert len(created_entities) == 1

    release_remove.set()
    await hass.async_block_till_done()
    assert len(created_entities) == 2
    assert registry.async_get_entity_id("sensor", DOMAIN, f"event_{event_id}") == sensor_id
    assert hass.states.get(sensor_id) is not None
