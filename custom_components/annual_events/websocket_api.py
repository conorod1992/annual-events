"""Authenticated WebSocket API for the Annual Events panel."""

# Home Assistant intentionally re-exports its documented WebSocket decorators,
# but does not include them in the module's static export list.
# mypy: disable-error-code="attr-defined,dict-item"

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback

from .const import (
    BUILT_IN_CATEGORIES,
    MAX_BETWEEN_DAYS,
    MAX_BETWEEN_RESULTS,
    MAX_LIST_LIMIT,
    MAX_SEARCH_LIMIT,
)
from .helpers import event_with_next, get_entry, get_manager, get_policy, local_today, parse_date
from .models import AnnualEvent, EventNotFoundError, EventValidationError
from .schema import CREATE_FIELDS, UPDATE_FIELDS

_UPDATE_KEYS = {str(marker.schema) for marker in UPDATE_FIELDS}


def _send_domain_error(connection: ActiveConnection, msg_id: int, err: Exception) -> None:
    if isinstance(err, EventNotFoundError):
        connection.send_error(msg_id, "not_found", f"Unknown annual event ID: {err.args[0]}")
    elif isinstance(err, EventValidationError):
        connection.send_error(msg_id, "invalid_format", str(err))
    else:
        connection.send_error(msg_id, "operation_failed", "Annual Events operation failed")


def _filter_records(hass: HomeAssistant, msg: dict[str, Any]) -> list[AnnualEvent]:
    manager = get_manager(hass)
    if query := msg.get("search"):
        records = manager.async_search_events(query, limit=MAX_LIST_LIMIT)
    else:
        records = manager.async_list_events()
    return [
        event
        for event in records
        if (msg.get("category") is None or event.category == msg["category"])
        and (msg.get("enabled") is None or event.enabled is msg["enabled"])
        and (msg.get("important") is None or event.important is msg["important"])
        and (msg.get("expose_entity") is None or event.expose_entity is msg["expose_entity"])
    ]


@websocket_api.websocket_command(
    {
        "type": "annual_events/list",
        vol.Optional("search"): str,
        vol.Optional("category"): str,
        vol.Optional("enabled"): bool,
        vol.Optional("important"): bool,
        vol.Optional("expose_entity"): bool,
        vol.Optional("sort", default="next_occurrence"): vol.In(["name", "next_occurrence"]),
        vol.Optional("direction", default="asc"): vol.In(["asc", "desc"]),
        vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
        vol.Optional("limit", default=100): vol.All(int, vol.Range(min=1, max=MAX_LIST_LIMIT)),
    }
)
@callback
def websocket_list(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """List, filter, sort and paginate records."""
    decorated = [event_with_next(hass, event) for event in _filter_records(hass, msg)]
    key = (
        (lambda row: (row["name"].casefold(), row["id"]))
        if msg["sort"] == "name"
        else (lambda row: (row["next_occurrence"], row["name"].casefold(), row["id"]))
    )
    decorated.sort(key=key, reverse=msg["direction"] == "desc")
    offset, limit = msg["offset"], msg["limit"]
    connection.send_result(
        msg["id"],
        {
            "events": decorated[offset : offset + limit],
            "pagination": {
                "offset": offset,
                "limit": limit,
                "total": len(decorated),
                "has_more": offset + limit < len(decorated),
            },
        },
    )


@websocket_api.websocket_command({"type": "annual_events/get", vol.Required("event_id"): str})
@callback
def websocket_get(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Get an exact event ID."""
    try:
        connection.send_result(
            msg["id"], event_with_next(hass, get_manager(hass).async_get_event(msg["event_id"]))
        )
    except EventNotFoundError as err:
        _send_domain_error(connection, msg["id"], err)


@websocket_api.websocket_command({"type": "annual_events/create", **CREATE_FIELDS})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_create(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Create a record; administrators only."""
    try:
        data = {key: value for key, value in msg.items() if key not in {"id", "type"}}
        event = await get_manager(hass).async_create_event(data)
        connection.send_result(msg["id"], event_with_next(hass, event))
    except (EventValidationError, EventNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)


@websocket_api.websocket_command(
    {"type": "annual_events/update", vol.Required("event_id"): str, **UPDATE_FIELDS}
)
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_update(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Apply explicit fields to a record; administrators only."""
    try:
        changes = {key: value for key, value in msg.items() if key in _UPDATE_KEYS}
        event = await get_manager(hass).async_update_event(msg["event_id"], changes)
        connection.send_result(msg["id"], event_with_next(hass, event))
    except (EventValidationError, EventNotFoundError) as err:
        _send_domain_error(connection, msg["id"], err)


@websocket_api.websocket_command({"type": "annual_events/delete", vol.Required("event_id"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_delete(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Delete an exact event ID; administrators only."""
    try:
        deleted = await get_manager(hass).async_delete_event(msg["event_id"])
        connection.send_result(msg["id"], {"deleted": True, "event_id": deleted.id})
    except EventNotFoundError as err:
        _send_domain_error(connection, msg["id"], err)


@websocket_api.websocket_command(
    {
        "type": "annual_events/search",
        vol.Required("query"): str,
        vol.Optional("category"): str,
        vol.Optional("enabled"): bool,
        vol.Optional("limit", default=25): vol.All(int, vol.Range(min=1, max=MAX_SEARCH_LIMIT)),
    }
)
@callback
def websocket_search(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return ranked search matches."""
    records = get_manager(hass).async_search_events(
        msg["query"], limit=msg["limit"], category=msg.get("category"), enabled=msg.get("enabled")
    )
    connection.send_result(
        msg["id"], {"events": [event_with_next(hass, event) for event in records]}
    )


@websocket_api.websocket_command(
    {
        "type": "annual_events/upcoming",
        vol.Optional("days", default=30): vol.All(int, vol.Range(min=0, max=MAX_BETWEEN_DAYS)),
        vol.Optional("limit", default=100): vol.All(int, vol.Range(min=1, max=MAX_SEARCH_LIMIT)),
        vol.Optional("category"): str,
        vol.Optional("important_only", default=False): bool,
        vol.Optional("enabled_only", default=True): bool,
    }
)
@callback
def websocket_upcoming(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return concrete upcoming occurrences."""
    today = local_today()
    occurrences = get_manager(hass).async_get_upcoming(
        today,
        days=msg["days"],
        policy=get_policy(hass),
        limit=msg["limit"],
        category=msg.get("category"),
        important_only=msg["important_only"],
        enabled_only=msg["enabled_only"],
    )
    connection.send_result(
        msg["id"], {"occurrences": [item.to_dict(relative_to=today) for item in occurrences]}
    )


@websocket_api.websocket_command(
    {
        "type": "annual_events/between",
        vol.Required("start"): str,
        vol.Required("end"): str,
        vol.Optional("limit", default=500): vol.All(int, vol.Range(min=1, max=MAX_BETWEEN_RESULTS)),
        vol.Optional("category"): str,
        vol.Optional("important_only", default=False): bool,
        vol.Optional("enabled_only", default=True): bool,
    }
)
@callback
def websocket_between(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return concrete occurrences in an inclusive local-date range."""
    try:
        start, end = parse_date(msg["start"], "start"), parse_date(msg["end"], "end")
        if end < start:
            raise EventValidationError("end date must not be before start date")
        if end - start > timedelta(days=MAX_BETWEEN_DAYS):
            raise EventValidationError(f"date range cannot exceed {MAX_BETWEEN_DAYS} days")
        occurrences = get_manager(hass).async_get_occurrences_between(
            start,
            end,
            policy=get_policy(hass),
            limit=msg["limit"],
            category=msg.get("category"),
            important_only=msg["important_only"],
            enabled_only=msg["enabled_only"],
        )
        connection.send_result(
            msg["id"],
            {"occurrences": [item.to_dict(relative_to=local_today()) for item in occurrences]},
        )
    except (EventValidationError, ValueError) as err:
        _send_domain_error(connection, msg["id"], err)


@websocket_api.websocket_command({"type": "annual_events/settings"})
@callback
def websocket_settings(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return non-sensitive integration settings and capabilities."""
    entry = get_entry(hass)
    connection.send_result(
        msg["id"],
        {
            "categories": list(BUILT_IN_CATEGORIES),
            "options": dict(entry.options),
            "is_admin": bool(connection.user and connection.user.is_admin),
            "capabilities": {"llm_read": True, "llm_mutation": False},
        },
    )


def async_register_websocket_commands(hass: HomeAssistant) -> None:
    """Register all integration-specific commands."""
    for command in (
        websocket_list,
        websocket_get,
        websocket_create,
        websocket_update,
        websocket_delete,
        websocket_search,
        websocket_upcoming,
        websocket_between,
        websocket_settings,
    ):
        websocket_api.async_register_command(hass, command)
