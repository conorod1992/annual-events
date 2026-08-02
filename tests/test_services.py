"""Tests for response-data actions."""

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN
from custom_components.annual_events.manager import AnnualEventsManager
from custom_components.annual_events.services import async_register_services

from .conftest import MemoryStorage


async def setup_actions(hass):
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)
    await async_register_services(hass)
    return manager


async def test_create_search_update_delete_actions(hass):
    await setup_actions(hass)
    created = await hass.services.async_call(
        DOMAIN,
        "create_event",
        {"name": "Oscar's birthday", "month": 4, "day": 6, "aliases": ["Dog"]},
        blocking=True,
        return_response=True,
    )
    event_id = created["event"]["id"]
    searched = await hass.services.async_call(
        DOMAIN, "search", {"query": "dog"}, blocking=True, return_response=True
    )
    assert searched["count"] == 1
    assert searched["events"][0]["id"] == event_id
    updated = await hass.services.async_call(
        DOMAIN,
        "update_event",
        {"event_id": event_id, "day": 7},
        blocking=True,
        return_response=True,
    )
    assert updated["event"]["day"] == 7
    deleted = await hass.services.async_call(
        DOMAIN, "delete_event", {"event_id": event_id}, blocking=True, return_response=True
    )
    assert deleted == {"deleted": True, "event_id": event_id}


async def test_action_validation_and_unknown_id(hass):
    await setup_actions(hass)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "create_event",
            {"name": "Bad", "month": 2, "day": 30},
            blocking=True,
            return_response=True,
        )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "delete_event",
            {"event_id": "00000000-0000-0000-0000-000000000000"},
            blocking=True,
            return_response=True,
        )
