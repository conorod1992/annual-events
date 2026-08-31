"""Shared Home Assistant adapter helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .calculations import LeapDayPolicy
from .const import (
    CONF_ADVANCE_NOTICE_DAYS,
    CONF_LEAP_DAY_POLICY,
    DEFAULT_ADVANCE_NOTICE_DAYS,
    DEFAULT_LEAP_DAY_POLICY,
    DOMAIN,
    MAX_ADVANCE_NOTICE_DAYS,
)
from .manager import AnnualEventsManager
from .models import AnnualEvent, EventNotFoundError, EventValidationError


def get_entry(hass: HomeAssistant) -> ConfigEntry[AnnualEventsManager]:
    """Return the configured entry or raise a user-facing error."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries or not hasattr(entries[0], "runtime_data"):
        raise HomeAssistantError("Annual Events is not configured")
    return entries[0]


def get_manager(hass: HomeAssistant) -> AnnualEventsManager:
    """Return the loaded collection manager."""
    return get_entry(hass).runtime_data


def get_policy(hass: HomeAssistant) -> LeapDayPolicy:
    """Return configured leap-day handling."""
    return LeapDayPolicy(get_entry(hass).options.get(CONF_LEAP_DAY_POLICY, DEFAULT_LEAP_DAY_POLICY))


def local_today() -> date:
    """Return today in Home Assistant's configured timezone."""
    return dt_util.now().date()


def parse_date(value: str, field: str) -> date:
    """Parse a strict ISO local date."""
    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise HomeAssistantError(f"{field} must be an ISO date (YYYY-MM-DD)") from err


def normalize_advance_notice_days(value: Any) -> tuple[int, ...]:
    """Normalize legacy scalar, text, or list advance offsets."""
    if value is None:
        return ()
    if isinstance(value, bool):
        raise ValueError("advance notice days must be integers")
    if isinstance(value, int):
        raw: list[Any] = [value]
    elif isinstance(value, str):
        if not value.strip():
            return ()
        raw = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raise ValueError("advance notice days must be a number or list")
    days: set[int] = set()
    for item in raw:
        if isinstance(item, bool):
            raise ValueError("advance notice days must be integers")
        if isinstance(item, int):
            day = item
        elif isinstance(item, str):
            try:
                day = int(item.strip())
            except ValueError as err:
                raise ValueError("advance notice days must be integers") from err
        else:
            raise ValueError("advance notice days must be integers")
        if not 1 <= day <= MAX_ADVANCE_NOTICE_DAYS:
            raise ValueError(f"advance notice days must be from 1 to {MAX_ADVANCE_NOTICE_DAYS}")
        days.add(day)
    return tuple(sorted(days, reverse=True))


def get_advance_notice_days(entry: ConfigEntry[AnnualEventsManager]) -> tuple[int, ...]:
    """Return configured global offsets while accepting the old scalar option."""
    value = entry.options.get(CONF_ADVANCE_NOTICE_DAYS, DEFAULT_ADVANCE_NOTICE_DAYS)
    return normalize_advance_notice_days(value)


def translate_domain_error(err: Exception) -> HomeAssistantError:
    """Convert domain errors without exposing storage details."""
    if isinstance(err, EventNotFoundError):
        return HomeAssistantError(f"Unknown annual event ID: {err.args[0]}")
    if isinstance(err, EventValidationError):
        return HomeAssistantError(str(err))
    return HomeAssistantError("Annual Events operation failed")


def event_with_next(hass: HomeAssistant, event: AnnualEvent) -> dict[str, Any]:
    """Serialize an event and its next calculated occurrence."""
    today = local_today()
    occurrence = get_manager(hass).next_for_event(event, today, get_policy(hass))
    return {
        **event.to_dict(),
        "next_occurrence": occurrence.occurrence_date.isoformat(),
        "days_until": (occurrence.occurrence_date - today).days,
        "occurrence_number": occurrence.occurrence_number,
    }
