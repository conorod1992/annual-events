"""Privacy-redacted diagnostics for Annual Events."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import STORAGE_VERSION, VERSION
from .manager import AnnualEventsManager


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[AnnualEventsManager]
) -> dict[str, Any]:
    """Return aggregate metadata without personal event content."""
    return {
        "integration_version": VERSION,
        "storage_schema_version": STORAGE_VERSION,
        "options": dict(entry.options),
        **entry.runtime_data.diagnostics_counts(),
    }
