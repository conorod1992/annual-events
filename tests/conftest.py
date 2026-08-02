"""Shared Annual Events test fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.annual_events.manager import AnnualEventsManager

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations."""
    yield


class MemoryStorage:
    """Deterministic async storage double."""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = list(records or [])
        self.save_count = 0

    async def async_load(self) -> list[dict[str, Any]]:
        return list(self.records)

    async def async_save(self, records: list[dict[str, Any]]) -> None:
        self.records = list(records)
        self.save_count += 1


@pytest.fixture
async def manager() -> AnnualEventsManager:
    """Return an empty loaded manager."""
    instance = AnnualEventsManager(MemoryStorage(), lambda: None)
    await instance.async_load()
    return instance


def event_data(name: str = "Mum's birthday", **changes: Any) -> dict[str, Any]:
    """Build valid input data."""
    return {
        "name": name,
        "month": 8,
        "day": 7,
        "category": "birthday",
        "aliases": ["Mam"],
        **changes,
    }
