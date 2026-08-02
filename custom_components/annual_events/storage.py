"""Versioned Home Assistant storage adapter."""

from __future__ import annotations

from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY, STORAGE_MINOR_VERSION, STORAGE_VERSION


class AnnualEventsStorage:
    """Persist the versioned event collection."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._store = Store[dict[str, Any]](
            hass,
            STORAGE_VERSION,
            STORAGE_KEY,
            minor_version=STORAGE_MINOR_VERSION,
        )

    async def async_load(self) -> list[dict[str, Any]]:
        """Load raw records; exceptions deliberately propagate to protect data."""
        data = await self._store.async_load()
        if data is None:
            return []
        if not isinstance(data, dict) or not isinstance(data.get("events"), list):
            raise ValueError("Annual Events storage has an invalid top-level structure")
        return cast(list[dict[str, Any]], data["events"])

    async def async_save(self, records: list[dict[str, Any]]) -> None:
        """Atomically save a deterministic snapshot."""
        await self._store.async_save(
            {
                "schema_version": STORAGE_VERSION,
                "events": sorted(records, key=lambda row: row["id"]),
            }
        )
