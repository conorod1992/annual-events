"""Tests for restart-safe proactive occurrence delivery."""

import asyncio
from datetime import UTC, date, datetime, timedelta

from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.annual_events.const import DOMAIN, EVENT_OCCURRENCE, SIGNAL_UPDATED
from custom_components.annual_events.manager import AnnualEventsManager
from custom_components.annual_events.proactive import DeliveryState, ProactiveEventCoordinator

from .conftest import MemoryStorage, event_data


class MemoryDeliveryStorage:
    """Persistent-across-coordinators delivery storage double."""

    def __init__(self, deliveries=None, last_reconciled_date=None):
        self.state = DeliveryState(dict(deliveries or {}), last_reconciled_date)
        self.save_count = 0

    @property
    def deliveries(self):
        return self.state.deliveries

    @property
    def last_reconciled_date(self):
        return self.state.last_reconciled_date

    async def async_load(self):
        return DeliveryState(dict(self.state.deliveries), self.state.last_reconciled_date)

    async def async_save(self, state):
        self.state = DeliveryState(dict(state.deliveries), state.last_reconciled_date)
        self.save_count += 1


class FailingDeliveryStorage(MemoryDeliveryStorage):
    """Delivery storage that fails when startup pruning tries to persist."""

    def __init__(self, deliveries=None):
        super().__init__(deliveries)
        self.fail_saves = True

    async def async_save(self, state):
        if self.fail_saves:
            raise RuntimeError("simulated ledger persistence failure")
        await super().async_save(state)


class BlockingDeliveryStorage(MemoryDeliveryStorage):
    """Delivery storage that can pause a save until the coordinator is stopped."""

    def __init__(self, deliveries=None, last_reconciled_date=None):
        super().__init__(deliveries, last_reconciled_date)
        self.block_saves = False
        self.save_started = asyncio.Event()
        self.release_save = asyncio.Event()

    async def async_save(self, state):
        if self.block_saves:
            self.save_started.set()
            await self.release_save.wait()
        await super().async_save(state)


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
    assert storage.last_reconciled_date == date(2026, 8, 1)
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


async def test_startup_replays_missed_due_dates_and_advances_checkpoint(hass, freezer):
    freezer.move_to("2026-08-10 18:00:00+00:00")
    manager, entry = await prepare(hass)
    event = await manager.async_create_event(event_data(name="Missed reminder", day=15))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    storage = MemoryDeliveryStorage(last_reconciled_date=date(2026, 8, 7))

    coordinator = ProactiveEventCoordinator(hass, entry, manager, storage)
    await coordinator.async_start()
    await hass.async_block_till_done()

    assert len(seen) == 1
    assert seen[0]["event_id"] == event.id
    assert seen[0]["occurrence_date"] == "2026-08-15"
    assert seen[0]["advance_days"] == 7
    assert seen[0]["days_until"] == 7
    assert storage.last_reconciled_date == date(2026, 8, 10)
    coordinator.async_stop()


async def test_startup_before_trigger_only_catches_up_completed_days(hass, freezer):
    freezer.move_to("2026-08-10 08:00:00+00:00")
    manager, entry = await prepare(hass)
    completed = await manager.async_create_event(event_data(name="Completed day", day=16))
    await manager.async_create_event(event_data(name="Not due yet", day=17))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    storage = MemoryDeliveryStorage(last_reconciled_date=date(2026, 8, 7))

    coordinator = ProactiveEventCoordinator(hass, entry, manager, storage)
    await coordinator.async_start()
    await hass.async_block_till_done()

    assert [item["event_id"] for item in seen] == [completed.id]
    assert seen[0]["occurrence_date"] == "2026-08-16"
    assert storage.last_reconciled_date == date(2026, 8, 9)
    coordinator.async_stop()


async def test_startup_catchup_is_bounded_to_recent_31_days(hass, freezer):
    freezer.move_to("2026-08-10 18:00:00+00:00")
    manager, entry = await prepare(hass)
    await manager.async_create_event(event_data(name="Outside cap", month=7, day=17))
    inside = await manager.async_create_event(event_data(name="Inside cap", month=7, day=18))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    storage = MemoryDeliveryStorage(last_reconciled_date=date(2026, 6, 1))

    coordinator = ProactiveEventCoordinator(hass, entry, manager, storage)
    await coordinator.async_start()
    await hass.async_block_till_done()

    advance = [item for item in seen if item["trigger"] == "advance"]
    assert [item["event_id"] for item in advance] == [inside.id]
    assert advance[0]["occurrence_date"] == "2026-07-18"
    assert storage.last_reconciled_date == date(2026, 8, 10)
    coordinator.async_stop()


async def test_reload_cancels_old_edit_reconcile_and_new_coordinator_recovers(hass, freezer):
    freezer.move_to("2026-08-01 18:00:00+00:00")
    manager, entry = await prepare(hass)
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    storage = BlockingDeliveryStorage()
    coordinator = ProactiveEventCoordinator(hass, entry, manager, storage)
    await coordinator.async_start()

    event = await manager.async_create_event(event_data(name="Late edit", day=1))
    storage.block_saves = True
    async_dispatcher_send(hass, SIGNAL_UPDATED)
    await asyncio.wait_for(storage.save_started.wait(), timeout=1)

    coordinator.async_stop()
    await hass.async_block_till_done()
    assert seen == []
    assert not any(event.id in key for key in storage.deliveries)

    storage.release_save.set()
    fresh = ProactiveEventCoordinator(hass, entry, manager, storage)
    await fresh.async_start()
    await hass.async_block_till_done()
    assert len(seen) == 1
    assert seen[0]["event_id"] == event.id
    fresh.async_stop()


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


async def test_failed_startup_cleans_up_listeners(hass, freezer):
    freezer.move_to("2026-08-01 00:00:00+00:00")
    manager, entry = await prepare(hass)
    await manager.async_create_event(event_data(name="Today", day=1))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))

    storage = FailingDeliveryStorage({"obsolete": "2025-01-01"})
    failed = ProactiveEventCoordinator(
        hass,
        entry,
        manager,
        storage,
    )
    try:
        await failed.async_start()
    except RuntimeError as err:
        assert str(err) == "simulated ledger persistence failure"
    else:
        raise AssertionError("startup should fail")
    assert failed._unsubscribers == []
    assert failed._tasks == set()

    storage.fail_saves = False
    freezer.move_to("2026-08-01 18:00:00+00:00")
    async_dispatcher_send(hass, SIGNAL_UPDATED)
    async_fire_time_changed(hass, datetime(2026, 8, 1, 16, 0, tzinfo=UTC))
    await hass.async_block_till_done()
    assert seen == []

    fresh = ProactiveEventCoordinator(hass, entry, manager, storage)
    await fresh.async_start()
    await hass.async_block_till_done()
    assert len(seen) == 1
    fresh.async_stop()


async def test_configured_trigger_time_uses_scheduled_callback(hass, freezer):
    freezer.move_to("2026-08-01 00:00:00+00:00")
    manager, entry = await prepare(hass, {"trigger_time": "08:30:00"})
    await manager.async_create_event(event_data(name="Today", day=1))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda item: seen.append(item.data))
    coordinator = ProactiveEventCoordinator(hass, entry, manager, MemoryDeliveryStorage())
    await coordinator.async_start()

    async_fire_time_changed(hass, datetime(2026, 8, 1, 15, 29, tzinfo=UTC))
    await hass.async_block_till_done()
    assert seen == []

    async_fire_time_changed(hass, datetime(2026, 8, 1, 15, 30, tzinfo=UTC))
    await hass.async_block_till_done()
    assert len(seen) == 1
    assert seen[0]["trigger"] == "today"

    async_fire_time_changed(hass, datetime(2026, 8, 1, 15, 30, tzinfo=UTC))
    await hass.async_block_till_done()
    assert len(seen) == 1
    coordinator.async_stop()
