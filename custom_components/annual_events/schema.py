"""Voluptuous schemas shared by WebSocket commands and actions."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import BUILT_IN_CATEGORIES, MAX_ADVANCE_NOTICE_DAYS, PROACTIVE_MODES


def coerce_integer(value: Any) -> int:
    """Accept integer values and integer strings without truncating fractions."""
    if isinstance(value, bool):
        raise vol.Invalid("expected integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError as err:
            raise vol.Invalid("expected integer") from err
    raise vol.Invalid("expected integer")


_PROACTIVE_DAYS = vol.All(
    cv.ensure_list,
    [vol.All(coerce_integer, vol.Range(min=1, max=MAX_ADVANCE_NOTICE_DAYS))],
)

CREATE_FIELDS = {
    vol.Required("name"): cv.string,
    vol.Required("month"): vol.All(coerce_integer, vol.Range(min=1, max=12)),
    vol.Required("day"): vol.All(coerce_integer, vol.Range(min=1, max=31)),
    vol.Optional("year"): vol.Any(None, vol.All(coerce_integer, vol.Range(min=1, max=9999))),
    vol.Optional("category"): vol.Any(None, cv.string),
    vol.Optional("aliases", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("icon"): vol.Any(None, cv.icon),
    vol.Optional("notes"): vol.Any(None, cv.string),
    vol.Optional("important", default=False): cv.boolean,
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("expose_entity", default=False): cv.boolean,
    vol.Optional("proactive_mode", default="default"): vol.In(PROACTIVE_MODES),
    vol.Optional("proactive_advance_days", default=[]): _PROACTIVE_DAYS,
    vol.Optional("proactive_day_of", default=True): cv.boolean,
}

UPDATE_FIELDS = {
    vol.Optional("name"): cv.string,
    vol.Optional("month"): vol.All(coerce_integer, vol.Range(min=1, max=12)),
    vol.Optional("day"): vol.All(coerce_integer, vol.Range(min=1, max=31)),
    vol.Optional("year"): vol.Any(None, vol.All(coerce_integer, vol.Range(min=1, max=9999))),
    vol.Optional("category"): vol.Any(None, cv.string),
    vol.Optional("aliases"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("icon"): vol.Any(None, cv.icon),
    vol.Optional("notes"): vol.Any(None, cv.string),
    vol.Optional("important"): cv.boolean,
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("expose_entity"): cv.boolean,
    vol.Optional("proactive_mode"): vol.In(PROACTIVE_MODES),
    vol.Optional("proactive_advance_days"): _PROACTIVE_DAYS,
    vol.Optional("proactive_day_of"): cv.boolean,
}

KNOWN_CATEGORIES = list(BUILT_IN_CATEGORIES)
