"""Tests for privacy-safe diagnostics."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN
from custom_components.annual_events.diagnostics import async_get_config_entry_diagnostics
from custom_components.annual_events.manager import AnnualEventsManager

from .conftest import MemoryStorage, event_data


async def test_diagnostics_include_counts_and_exclude_personal_data(hass):
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    await manager.async_create_event(
        event_data(
            name="Private Person",
            notes="Private note",
            year=1980,
            important=True,
            expose_entity=True,
        )
    )
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={"leap_day_policy": "feb_28"})
    entry.runtime_data = manager
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["event_count"] == 1
    assert result["important_count"] == 1
    assert result["exposed_entity_count"] == 1
    serialized = str(result)
    assert "Private Person" not in serialized
    assert "Private note" not in serialized
    assert "1980" not in serialized
    assert "aliases" not in serialized
