"""Regression tests for multiple proactive intervals and per-event overrides."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN, EVENT_OCCURRENCE
from custom_components.annual_events.helpers import normalize_advance_notice_days
from custom_components.annual_events.manager import AnnualEventsManager
from custom_components.annual_events.proactive import DeliveryState, ProactiveEventCoordinator

from .conftest import MemoryStorage, event_data


class MemoryDeliveryStorage:
    """In-memory proactive delivery ledger."""

    def __init__(self) -> None:
        self.state = DeliveryState({})

    async def async_load(self) -> DeliveryState:
        return DeliveryState(dict(self.state.deliveries), self.state.last_reconciled_date)

    async def async_save(self, state: DeliveryState) -> None:
        self.state = DeliveryState(dict(state.deliveries), state.last_reconciled_date)


async def prepare(hass, options):
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"leap_day_policy": "feb_28", **options},
    )
    entry.runtime_data = manager
    entry.add_to_hass(hass)
    return manager, entry


def test_normalize_advance_days_accepts_legacy_and_new_values():
    assert normalize_advance_notice_days(7) == (7,)
    assert normalize_advance_notice_days([1, 30, 7, 7]) == (30, 7, 1)
    assert normalize_advance_notice_days("30, 7, 1") == (30, 7, 1)
    assert normalize_advance_notice_days("") == ()


async def test_event_proactive_fields_round_trip(manager):
    inherited = await manager.async_create_event(event_data())
    assert inherited.proactive_mode == "default"
    assert inherited.proactive_advance_days == ()
    assert inherited.proactive_day_of is True

    custom = await manager.async_create_event(
        event_data(
            name="Custom",
            proactive_mode="custom",
            proactive_advance_days=[1, 30, 7, 7],
            proactive_day_of=False,
        )
    )
    assert custom.proactive_advance_days == (30, 7, 1)
    serialized = custom.to_dict()
    assert serialized["proactive_mode"] == "custom"
    assert serialized["proactive_advance_days"] == [30, 7, 1]
    assert serialized["proactive_day_of"] is False


async def test_multiple_global_advance_intervals(hass, freezer):
    freezer.move_to("2026-08-01 18:00:00+00:00")
    manager, entry = await prepare(
        hass,
        {"advance_notice_days": [30, 7], "emit_day_of": False},
    )
    seven = await manager.async_create_event(event_data(name="Seven", day=8))
    thirty = await manager.async_create_event(event_data(name="Thirty", day=31))
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda event: seen.append(event.data))

    coordinator = ProactiveEventCoordinator(hass, entry, manager, MemoryDeliveryStorage())
    await coordinator.async_reconcile()
    await hass.async_block_till_done()

    assert {(item["event_id"], item["advance_days"]) for item in seen} == {
        (seven.id, 7),
        (thirty.id, 30),
    }


async def test_per_event_custom_and_off_override_defaults(hass, freezer):
    freezer.move_to("2026-08-01 18:00:00+00:00")
    manager, entry = await prepare(
        hass,
        {"advance_notice_days": [7], "emit_day_of": True},
    )
    inherited = await manager.async_create_event(event_data(name="Inherited", day=8))
    custom = await manager.async_create_event(
        event_data(
            name="Custom",
            day=4,
            proactive_mode="custom",
            proactive_advance_days=[3],
            proactive_day_of=False,
        )
    )
    await manager.async_create_event(event_data(name="Off", day=8, proactive_mode="off"))
    today_default = await manager.async_create_event(event_data(name="Today", day=1))
    await manager.async_create_event(
        event_data(
            name="No day-of",
            day=1,
            proactive_mode="custom",
            proactive_advance_days=[],
            proactive_day_of=False,
        )
    )
    seen = []
    hass.bus.async_listen(EVENT_OCCURRENCE, lambda event: seen.append(event.data))

    coordinator = ProactiveEventCoordinator(hass, entry, manager, MemoryDeliveryStorage())
    await coordinator.async_reconcile()
    await hass.async_block_till_done()

    assert {(item["event_id"], item["trigger"], item.get("advance_days")) for item in seen} == {
        (inherited.id, "advance", 7),
        (custom.id, "advance", 3),
        (today_default.id, "today", None),
    }
