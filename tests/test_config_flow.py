"""Tests for the single-entry config and options flows."""

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN


async def test_config_flow_success(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Annual Events"
    assert result["data"] == {}


async def test_duplicate_prevention(hass):
    MockConfigEntry(domain=DOMAIN, data={}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "leap_day_policy": "mar_1",
            "upcoming_days": 60,
            "show_panel": False,
            "advance_notice_days": "30, 5, 1",
            "trigger_time": "08:30:00",
            "emit_day_of": False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["leap_day_policy"] == "mar_1"
    assert entry.options["advance_notice_days"] == [30, 5, 1]
