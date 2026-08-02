"""Shared Home Assistant adapter helpers."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .calculations import LeapDayPolicy
from .const import CONF_LEAP_DAY_POLICY, DEFAULT_LEAP_DAY_POLICY, DOMAIN
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


def translate_domain_error(err: Exception) -> HomeAssistantError:
    """Convert domain errors without exposing storage details."""
    if isinstance(err, EventNotFoundError):
        return HomeAssistantError(f"Unknown annual event ID: {err.args[0]}")
    if isinstance(err, EventValidationError):
        return HomeAssistantError(str(err))
    return HomeAssistantError("Annual Events operation failed")


def event_with_next(hass: HomeAssistant, event: AnnualEvent) -> dict[str, Any]:
    """Serialize an event and its next calculated occurrence."""
    occurrence = get_manager(hass).next_for_event(event, local_today(), get_policy(hass))
    return {
        **event.to_dict(),
        "next_occurrence": occurrence.occurrence_date.isoformat(),
        "days_until": (occurrence.occurrence_date - local_today()).days,
        "occurrence_number": occurrence.occurrence_number,
    }
