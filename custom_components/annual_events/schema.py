"""Voluptuous schemas shared by WebSocket commands and actions."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

from .const import BUILT_IN_CATEGORIES

CREATE_FIELDS = {
    vol.Required("name"): cv.string,
    vol.Required("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Required("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
    vol.Optional("year"): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=1, max=9999))),
    vol.Optional("category"): vol.Any(None, cv.string),
    vol.Optional("aliases", default=[]): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("icon"): vol.Any(None, cv.icon),
    vol.Optional("notes"): vol.Any(None, cv.string),
    vol.Optional("important", default=False): cv.boolean,
    vol.Optional("enabled", default=True): cv.boolean,
    vol.Optional("expose_entity", default=False): cv.boolean,
}

UPDATE_FIELDS = {
    vol.Optional("name"): cv.string,
    vol.Optional("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("day"): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
    vol.Optional("year"): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=1, max=9999))),
    vol.Optional("category"): vol.Any(None, cv.string),
    vol.Optional("aliases"): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional("icon"): vol.Any(None, cv.icon),
    vol.Optional("notes"): vol.Any(None, cv.string),
    vol.Optional("important"): cv.boolean,
    vol.Optional("enabled"): cv.boolean,
    vol.Optional("expose_entity"): cv.boolean,
}

KNOWN_CATEGORIES = list(BUILT_IN_CATEGORIES)
