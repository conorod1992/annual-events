"""Home Assistant actions for Annual Events."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, NoReturn

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from .const import DOMAIN, MAX_BETWEEN_DAYS, MAX_BETWEEN_RESULTS, MAX_SEARCH_LIMIT
from .helpers import event_with_next, get_manager, get_policy, local_today, parse_date
from .models import EventNotFoundError, EventValidationError
from .schema import CREATE_FIELDS, UPDATE_FIELDS, coerce_integer

SERVICE_CREATE = "create_event"
SERVICE_UPDATE = "update_event"
SERVICE_DELETE = "delete_event"
SERVICE_SEARCH = "search"
SERVICE_UPCOMING = "get_upcoming"
SERVICE_BETWEEN = "get_between"
SERVICE_NEXT = "get_next"
SERVICE_FOR_DATE = "get_for_date"

_UPDATE_KEYS = {str(marker.schema) for marker in UPDATE_FIELDS}


def _raise_action_error(err: Exception) -> NoReturn:
    if isinstance(err, EventNotFoundError):
        raise HomeAssistantError(f"Unknown annual event ID: {err.args[0]}") from err
    raise HomeAssistantError(str(err)) from err


async def async_register_services(hass: HomeAssistant) -> None:
    """Register mutation and response-data query actions once."""
    if hass.services.has_service(DOMAIN, SERVICE_CREATE):
        return

    async def create(call: ServiceCall) -> dict[str, Any]:
        try:
            event = await get_manager(hass).async_create_event(dict(call.data))
            return {"event": event_with_next(hass, event)}
        except EventValidationError as err:
            _raise_action_error(err)

    async def update(call: ServiceCall) -> dict[str, Any]:
        try:
            changes = {key: value for key, value in call.data.items() if key in _UPDATE_KEYS}
            event = await get_manager(hass).async_update_event(call.data["event_id"], changes)
            return {"event": event_with_next(hass, event)}
        except (EventNotFoundError, EventValidationError) as err:
            _raise_action_error(err)

    async def delete(call: ServiceCall) -> dict[str, Any]:
        try:
            event = await get_manager(hass).async_delete_event(call.data["event_id"])
            return {"deleted": True, "event_id": event.id}
        except EventNotFoundError as err:
            _raise_action_error(err)

    async def search(call: ServiceCall) -> dict[str, Any]:
        records = get_manager(hass).async_search_events(
            call.data["query"],
            limit=call.data["limit"],
            category=call.data.get("category"),
            enabled=call.data.get("enabled"),
        )
        return {
            "events": [event_with_next(hass, event) for event in records],
            "count": len(records),
        }

    async def upcoming(call: ServiceCall) -> dict[str, Any]:
        today = local_today()
        records = get_manager(hass).async_get_upcoming(
            today,
            days=call.data["days"],
            limit=call.data["limit"],
            policy=get_policy(hass),
            category=call.data.get("category"),
            important_only=call.data["important_only"],
            enabled_only=True,
        )
        return {
            "occurrences": [item.to_dict(relative_to=today) for item in records],
            "count": len(records),
        }

    async def between(call: ServiceCall) -> dict[str, Any]:
        start, end = parse_date(call.data["start"], "start"), parse_date(call.data["end"], "end")
        if end < start or end - start > timedelta(days=MAX_BETWEEN_DAYS):
            raise HomeAssistantError(
                f"Range must be ordered and no longer than {MAX_BETWEEN_DAYS} days"
            )
        records = get_manager(hass).async_get_occurrences_between(
            start,
            end,
            limit=call.data["limit"],
            policy=get_policy(hass),
            category=call.data.get("category"),
            important_only=call.data["important_only"],
            enabled_only=True,
        )
        today = local_today()
        return {
            "occurrences": [item.to_dict(relative_to=today) for item in records],
            "count": len(records),
        }

    async def get_next(call: ServiceCall) -> dict[str, Any]:
        today = local_today()
        occurrence = get_manager(hass).async_get_next(
            today,
            policy=get_policy(hass),
            category=call.data.get("category"),
            important_only=call.data["important_only"],
        )
        return {
            "event": occurrence.to_dict(relative_to=today) if occurrence else None,
        }

    async def get_for_date(call: ServiceCall) -> dict[str, Any]:
        target = parse_date(call.data["date"], "date")
        records = get_manager(hass).async_get_occurrences_between(
            target,
            target,
            policy=get_policy(hass),
            category=call.data.get("category"),
            important_only=call.data["important_only"],
            enabled_only=True,
        )
        today = local_today()
        return {
            "count": len(records),
            "occurrences": [item.to_dict(relative_to=today) for item in records],
        }

    update_service_schema: dict[Any, Any] = {vol.Required("event_id"): cv.string}
    update_service_schema.update(UPDATE_FIELDS)

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CREATE,
        create,
        schema=vol.Schema(CREATE_FIELDS),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_UPDATE,
        update,
        schema=vol.Schema(update_service_schema),
        supports_response=SupportsResponse.OPTIONAL,
    )
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_DELETE,
        delete,
        schema=vol.Schema({vol.Required("event_id"): cv.string}),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        search,
        schema=vol.Schema(
            {
                vol.Required("query"): cv.string,
                vol.Optional("category"): cv.string,
                vol.Optional("enabled"): cv.boolean,
                vol.Optional("limit", default=25): vol.All(
                    coerce_integer, vol.Range(min=1, max=MAX_SEARCH_LIMIT)
                ),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPCOMING,
        upcoming,
        schema=vol.Schema(
            {
                vol.Optional("days", default=30): vol.All(
                    coerce_integer, vol.Range(min=0, max=MAX_BETWEEN_DAYS)
                ),
                vol.Optional("limit", default=100): vol.All(
                    coerce_integer, vol.Range(min=1, max=MAX_SEARCH_LIMIT)
                ),
                vol.Optional("category"): cv.string,
                vol.Optional("important_only", default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BETWEEN,
        between,
        schema=vol.Schema(
            {
                vol.Required("start"): cv.string,
                vol.Required("end"): cv.string,
                vol.Optional("limit", default=500): vol.All(
                    coerce_integer, vol.Range(min=1, max=MAX_BETWEEN_RESULTS)
                ),
                vol.Optional("category"): cv.string,
                vol.Optional("important_only", default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_NEXT,
        get_next,
        schema=vol.Schema(
            {
                vol.Optional("category"): cv.string,
                vol.Optional("important_only", default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_FOR_DATE,
        get_for_date,
        schema=vol.Schema(
            {
                vol.Required("date"): cv.string,
                vol.Optional("category"): cv.string,
                vol.Optional("important_only", default=False): cv.boolean,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove integration actions."""
    for service in (
        SERVICE_CREATE,
        SERVICE_UPDATE,
        SERVICE_DELETE,
        SERVICE_SEARCH,
        SERVICE_UPCOMING,
        SERVICE_BETWEEN,
        SERVICE_NEXT,
        SERVICE_FOR_DATE,
    ):
        hass.services.async_remove(DOMAIN, service)
