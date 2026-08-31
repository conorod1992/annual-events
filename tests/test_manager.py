"""Tests for storage and atomic collection mutations."""

import asyncio
from uuid import uuid4

import pytest

from custom_components.annual_events.manager import AnnualEventsManager, StorageIntegrityError
from custom_components.annual_events.models import (
    AnnualEvent,
    DuplicateEventIdError,
    EventNotFoundError,
    EventValidationError,
)

from .conftest import MemoryStorage, event_data


@pytest.mark.asyncio
async def test_initial_empty_create_update_delete_and_persistence():
    storage = MemoryStorage()
    updates = 0

    def notify():
        nonlocal updates
        updates += 1

    manager = AnnualEventsManager(storage, notify)
    await manager.async_load()
    assert manager.async_list_events() == []
    created = await manager.async_create_event(event_data(year=1992))
    assert storage.save_count == 1
    updated = await manager.async_update_event(created.id, {"name": "Mum's special birthday"})
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.name.endswith("special birthday")
    deleted = await manager.async_delete_event(created.id)
    assert deleted.id == created.id
    assert manager.async_list_events() == []
    assert storage.save_count == 3
    assert updates == 3


@pytest.mark.asyncio
async def test_reload_round_trip():
    storage = MemoryStorage()
    first = AnnualEventsManager(storage, lambda: None)
    await first.async_load()
    created = await first.async_create_event(event_data())
    second = AnnualEventsManager(storage, lambda: None)
    await second.async_load()
    assert second.async_get_event(created.id).to_dict() == created.to_dict()


@pytest.mark.asyncio
async def test_duplicate_ids_are_rejected():
    storage = MemoryStorage()
    manager = AnnualEventsManager(storage, lambda: None)
    await manager.async_load()
    event_id = str(uuid4())
    await manager.async_create_event(event_data(id=event_id))
    with pytest.raises(DuplicateEventIdError):
        await manager.async_create_event(event_data(name="Other", id=event_id))


@pytest.mark.asyncio
async def test_invalid_stored_records_are_skipped_without_overwrite():
    storage = MemoryStorage([{"bad": "record"}])
    manager = AnnualEventsManager(storage, lambda: None)
    await manager.async_load()
    assert manager.async_list_events() == []
    assert storage.save_count == 0
    assert manager.diagnostics_counts()["invalid_storage_record_count"] == 1
    assert manager.diagnostics_counts()["storage_mutations_blocked"] is True


@pytest.mark.asyncio
async def test_malformed_storage_blocks_all_mutations_without_overwrite():
    valid = AnnualEvent.create(event_data(name="Valid event")).to_dict()
    malformed = {"bad": "record"}
    original_records = [valid, malformed]
    storage = MemoryStorage(original_records)
    manager = AnnualEventsManager(storage, lambda: None)
    await manager.async_load()

    event_id = valid["id"]
    assert manager.async_get_event(event_id).name == "Valid event"

    with pytest.raises(StorageIntegrityError, match="disabled to prevent data loss"):
        await manager.async_create_event(event_data(name="New event"))
    with pytest.raises(StorageIntegrityError, match="disabled to prevent data loss"):
        await manager.async_update_event(event_id, {"name": "Changed event"})
    with pytest.raises(StorageIntegrityError, match="disabled to prevent data loss"):
        await manager.async_delete_event(event_id)

    assert manager.async_get_event(event_id).name == "Valid event"
    assert storage.records == original_records
    assert storage.save_count == 0


@pytest.mark.asyncio
async def test_duplicate_stored_ids_also_block_mutations():
    first = AnnualEvent.create(event_data(name="First event")).to_dict()
    duplicate = {**first, "name": "Duplicate row"}
    original_records = [first, duplicate]
    storage = MemoryStorage(original_records)
    manager = AnnualEventsManager(storage, lambda: None)
    await manager.async_load()

    assert [event.name for event in manager.async_list_events()] == ["First event"]
    assert manager.diagnostics_counts()["invalid_storage_record_count"] == 1
    with pytest.raises(StorageIntegrityError):
        await manager.async_delete_event(first["id"])
    assert storage.records == original_records
    assert storage.save_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid_change",
    ({"id": "generate"}, {"proactive_advance_days": [7.9]}),
)
async def test_unsafe_stored_value_coercions_are_treated_as_corruption(invalid_change):
    valid = AnnualEvent.create(event_data(name="Valid event")).to_dict()
    malformed = AnnualEvent.create(event_data(name="Malformed event")).to_dict()
    malformed.update(invalid_change)
    original_records = [valid, malformed]
    storage = MemoryStorage(original_records)
    manager = AnnualEventsManager(storage, lambda: None)

    await manager.async_load()

    assert [event.name for event in manager.async_list_events()] == ["Valid event"]
    assert manager.diagnostics_counts()["invalid_storage_record_count"] == 1
    assert manager.diagnostics_counts()["storage_mutations_blocked"] is True
    with pytest.raises(StorageIntegrityError):
        await manager.async_update_event(valid["id"], {"name": "Changed"})
    assert storage.records == original_records
    assert storage.save_count == 0


@pytest.mark.asyncio
async def test_unknown_ids():
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    with pytest.raises(EventNotFoundError):
        manager.async_get_event(str(uuid4()))
    with pytest.raises(EventNotFoundError):
        await manager.async_update_event(str(uuid4()), {"name": "No"})
    with pytest.raises(EventNotFoundError):
        await manager.async_delete_event(str(uuid4()))


@pytest.mark.asyncio
async def test_concurrent_creates_are_serialized():
    storage = MemoryStorage()
    manager = AnnualEventsManager(storage, lambda: None)
    await manager.async_load()
    await asyncio.gather(
        *(manager.async_create_event(event_data(name=f"Event {index}")) for index in range(20))
    )
    assert len(manager.async_list_events()) == 20
    assert storage.save_count == 20


@pytest.mark.asyncio
async def test_failed_persistence_rolls_back():
    class FailingStorage(MemoryStorage):
        async def async_save(self, records):
            raise OSError("disk full")

    manager = AnnualEventsManager(FailingStorage(), lambda: None)
    await manager.async_load()
    with pytest.raises(OSError):
        await manager.async_create_event(event_data())
    assert manager.async_list_events() == []


@pytest.mark.asyncio
async def test_known_leap_day_requires_a_real_leap_year():
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    with pytest.raises(EventValidationError):
        await manager.async_create_event(event_data(month=2, day=29, year=2025))
