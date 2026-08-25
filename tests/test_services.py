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


async def test_get_next_and_get_for_date_filters(hass, freezer):
    freezer.move_to("2026-08-01 12:00:00+00:00")
    manager = await setup_actions(hass)
    await manager.async_create_event(
        {
            "name": "Ignored disabled",
            "month": 8,
            "day": 2,
            "category": "birthday",
            "important": True,
            "enabled": False,
        }
    )
    selected = await manager.async_create_event(
        {
            "name": "Selected",
            "month": 8,
            "day": 3,
            "year": 2000,
            "category": "birthday",
            "important": True,
        }
    )
    await manager.async_create_event({"name": "Other", "month": 8, "day": 3, "category": "holiday"})

    next_result = await hass.services.async_call(
        DOMAIN,
        "get_next",
        {"category": "birthday", "important_only": True},
        blocking=True,
        return_response=True,
    )
    assert next_result == {
        "event": {
            "event_id": selected.id,
            "name": "Selected",
            "category": "birthday",
            "occurrence_date": "2026-08-03",
            "occurrence_number": 26,
            "important": True,
            "days_until": 2,
        }
    }
    for_date = await hass.services.async_call(
        DOMAIN,
        "get_for_date",
        {"date": "2026-08-03", "category": "birthday", "important_only": True},
        blocking=True,
        return_response=True,
    )
    assert for_date["count"] == 1
    assert for_date["occurrences"][0]["event_id"] == selected.id

    empty = await hass.services.async_call(
        DOMAIN,
        "get_next",
        {"category": "missing"},
        blocking=True,
        return_response=True,
    )
    assert empty == {"event": None}
