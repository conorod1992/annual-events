"""Tests for WebSocket queries, mutations, validation, and permissions."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.annual_events.const import DOMAIN
from custom_components.annual_events.manager import AnnualEventsManager
from custom_components.annual_events.websocket_api import async_register_websocket_commands

from .conftest import MemoryStorage


async def setup_websocket(hass, hass_ws_client, token=None):
    manager = AnnualEventsManager(MemoryStorage(), lambda: None)
    await manager.async_load()
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.runtime_data = manager
    entry.add_to_hass(hass)
    client = await hass_ws_client(hass, token) if token is not None else await hass_ws_client(hass)
    async_register_websocket_commands(hass)
    return client, manager


async def test_websocket_crud_list_search_upcoming_between(hass, hass_ws_client):
    client, _ = await setup_websocket(hass, hass_ws_client)
    await client.send_json_auto_id(
        {
            "type": "annual_events/create",
            "name": "Mum's birthday",
            "month": 8,
            "day": 7,
            "year": 2000,
            "aliases": ["Mam"],
            "important": True,
        }
    )
    created = await client.receive_json()
    assert created["success"] is True
    event_id = created["result"]["id"]

    for request, key in (
        ({"type": "annual_events/list"}, "events"),
        ({"type": "annual_events/search", "query": "mam"}, "events"),
        ({"type": "annual_events/upcoming", "days": 366}, "occurrences"),
        (
            {"type": "annual_events/between", "start": "2026-01-01", "end": "2027-12-31"},
            "occurrences",
        ),
    ):
        await client.send_json_auto_id(request)
        response = await client.receive_json()
        assert response["success"] is True
        assert response["result"][key]

    await client.send_json_auto_id({"type": "annual_events/update", "event_id": event_id, "day": 8})
    assert (await client.receive_json())["result"]["day"] == 8
    await client.send_json_auto_id({"type": "annual_events/delete", "event_id": event_id})
    assert (await client.receive_json())["result"]["deleted"] is True


async def test_websocket_validation_unknown_and_admin_restriction(
    hass, hass_ws_client, hass_read_only_access_token
):
    client, _ = await setup_websocket(hass, hass_ws_client)
    await client.send_json_auto_id(
        {"type": "annual_events/create", "name": "Bad", "month": 2, "day": 30}
    )
    invalid = await client.receive_json()
    assert invalid["success"] is False
    assert invalid["error"]["code"] == "invalid_format"
    await client.send_json_auto_id(
        {"type": "annual_events/get", "event_id": "00000000-0000-0000-0000-000000000000"}
    )
    missing = await client.receive_json()
    assert missing["error"]["code"] == "not_found"

    read_only = await hass_ws_client(hass, hass_read_only_access_token)
    await read_only.send_json_auto_id(
        {"type": "annual_events/create", "name": "No", "month": 1, "day": 1}
    )
    denied = await read_only.receive_json()
    assert denied["success"] is False
    assert denied["error"]["code"] == "unauthorized"
