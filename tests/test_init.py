"""End-to-end config entry setup and unload tests."""

from homeassistant.components import frontend
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN, PANEL_URL


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
