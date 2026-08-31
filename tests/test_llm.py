"""Tests for contributed read-only LLM tools."""

import pytest
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.llm import LLMContext, ToolInput
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN
from custom_components.annual_events.llm import async_get_tools
from custom_components.annual_events.manager import AnnualEventsManager

from .conftest import MemoryStorage, event_data


async def test_llm_read_tools(hass, freezer):
    freezer.move_to("2026-08-01 12:00:00+00:00")
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    await manager.async_create_event(event_data(year=2000, important=True))
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)
    context = LLMContext(
        platform="conversation",
        context=None,
        language="en",
        assistant="conversation",
        device_id=None,
    )
    contribution = async_get_tools(hass, context, "assist")
    tools = {tool.name: tool for tool in contribution.tools}
    assert set(tools) == {
        "search_annual_events",
        "get_upcoming_annual_events",
        "get_annual_events_between",
    }
    assert "read-only" in contribution.prompt

    searched = await tools["search_annual_events"].async_call(
        hass, ToolInput("search_annual_events", {"query": "mam", "limit": 10}), context
    )
    assert searched["count"] == 1
    assert searched["events"][0]["occurrence_number"] == 26

    upcoming = await tools["get_upcoming_annual_events"].async_call(
        hass,
        ToolInput(
            "get_upcoming_annual_events",
            {"days": 10, "important_only": True, "limit": 10},
        ),
        context,
    )
    assert upcoming["occurrences"][0]["days_until"] == 6

    between = await tools["get_annual_events_between"].async_call(
        hass,
        ToolInput(
            "get_annual_events_between",
            {"start": "2026-08-01", "end": "2026-08-08", "important_only": False, "limit": 10},
        ),
        context,
    )
    assert between["count"] == 1

    with pytest.raises(vol.Invalid, match="expected integer"):
        tools["get_upcoming_annual_events"].parameters(
            {"days": 7.9, "important_only": False, "limit": 10}
        )

    with pytest.raises(HomeAssistantError):
        await tools["get_annual_events_between"].async_call(
            hass,
            ToolInput(
                "get_annual_events_between",
                {"start": "2027-01-01", "end": "2026-01-01", "important_only": False, "limit": 10},
            ),
            context,
        )
