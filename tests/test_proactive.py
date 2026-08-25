"""Tests for restart-safe proactive occurrence delivery."""

from datetime import timedelta

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN, EVENT_OCCURRENCE
from custom_components.annual_events.manager import AnnualEventsManager
from custom_components.annual_events.proactive import ProactiveEventCoordinator

from .conftest import MemoryStorage, event_data


class MemoryDeliveryStorage:
    """Persistent-across-coordinators delivery storage double."""

    def __init__(self, deliveries=None):
        self.deliveries = dict(deliveries or {})
        self.save_count = 0

    async def async_load(self):
        return dict(self.deliveries)

    async def async_save(self, deliveries):
        self.deliveries = dict(deliveries)
        self.save_count += 1


async def prepare(hass, options=None):
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"leap_day_policy": "feb_28", **(options or {})},
    )
    entry.runtime_data = manager
    entry.add_to_hass(hass)
    return manager, entry


async def test_advance_day_of_disabled_and_restart_deduplication(hass, freezer):
    freezer.move_to("2026-08-01 18:00:00+00:00")
    manager, entry = await prepare(hass)
    advance = await manager.async_create_event(
        event_data(name="Advance", day=8, year=2000, important=True)
    )
    today = await manager.async_create_event(event_data(name="Today", day=1))
    await manager.async_create_event(event_data(name="Disabled", day=8, enabled=False))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda event: seen.append(event.data))
    storage = MemoryDeliveryStorage()

    coordinator = ProactiveEventCoordinator(hass, entry, manager, storage)
    await coordinator.async_start()
    await hass.async_block_till_done()
    assert {item["trigger"] for item in seen} == {"advance", "today"}
    advance_payload = next(item for item in seen if item["trigger"] == "advance")
    assert advance_payload == {
        "event_id": advance.id,
        "name": "Advance",
        "category": "birthday",
        "occurrence_date": "2026-08-08",
        "occurrence_number": 26,
        "important": True,
        "days_until": 7,
        "trigger": "advance",
        "advance_days": 7,
    }
    assert next(item for item in seen if item["trigger"] == "today")["event_id"] == today.id
    coordinator.async_stop()

    restarted = ProactiveEventCoordinator(hass, entry, manager, storage)
    await restarted.async_start()
    await hass.async_block_till_done()
    assert len(seen) == 2
    restarted.async_stop()


async def test_restart_before_trigger_waits_and_after_trigger_catches_up(hass, freezer):
    freezer.move_to("2026-12-31 15:00:00+00:00")
    manager, entry = await prepare(hass)
    event = await manager.async_create_event(event_data(name="Year boundary", month=1, day=7))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    storage = MemoryDeliveryStorage()
    before = ProactiveEventCoordinator(hass, entry, manager, storage)
    await before.async_start()
    assert seen == []
    before.async_stop()

    freezer.move_to("2026-12-31 18:00:00+00:00")
    after = ProactiveEventCoordinator(hass, entry, manager, storage)
    await after.async_start()
    await hass.async_block_till_done()
    assert len(seen) == 1
    assert seen[0]["event_id"] == event.id
    assert seen[0]["occurrence_date"] == "2027-01-07"
    after.async_stop()


async def test_leap_policy_edit_new_occurrence_and_pruning(hass, freezer):
    freezer.move_to("2026-02-21 18:00:00+00:00")
    manager, entry = await prepare(hass)
    event = await manager.async_create_event(event_data(name="Leap", month=2, day=29, year=2020))
    old_date = (freezer.time_to_freeze.date() - timedelta(days=401)).isoformat()
    storage = MemoryDeliveryStorage({"obsolete": old_date})
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    coordinator = ProactiveEventCoordinator(hass, entry, manager, storage)
    await coordinator.async_start()
    await hass.async_block_till_done()
    assert seen[0]["occurrence_date"] == "2026-02-28"
    assert "obsolete" not in storage.deliveries

    await manager.async_update_event(event.id, {"month": 3, "day": 1})
    freezer.move_to("2026-02-22 18:00:00+00:00")
    await coordinator.async_reconcile()
    await hass.async_block_till_done()
    assert [item["occurrence_date"] for item in seen] == ["2026-02-28", "2026-03-01"]
    coordinator.async_stop()


async def test_day_of_can_be_disabled(hass, freezer):
    freezer.move_to("2026-08-01 18:00:00+00:00")
    manager, entry = await prepare(hass, {"emit_day_of": False})
    await manager.async_create_event(event_data(name="Today", day=1))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    coordinator = ProactiveEventCoordinator(hass, entry, manager, MemoryDeliveryStorage())
    await coordinator.async_start()
    await hass.async_block_till_done()
    assert seen == []
    coordinator.async_stop()
