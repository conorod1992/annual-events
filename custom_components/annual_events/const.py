"""Constants for Annual Events."""

from typing import Final

DOMAIN: Final = "annual_events"
NAME: Final = "Annual Events"
VERSION: Final = "1.0.0"

PLATFORMS: Final = ["sensor", "calendar"]
STORAGE_KEY: Final = "annual_events.events"
STORAGE_VERSION: Final = 1
STORAGE_MINOR_VERSION: Final = 1
SIGNAL_UPDATED: Final = "annual_events_updated"

CONF_LEAP_DAY_POLICY: Final = "leap_day_policy"
CONF_UPCOMING_DAYS: Final = "upcoming_days"
CONF_SHOW_PANEL: Final = "show_panel"

DEFAULT_LEAP_DAY_POLICY: Final = "feb_28"
DEFAULT_UPCOMING_DAYS: Final = 30
DEFAULT_SHOW_PANEL: Final = True

PANEL_URL: Final = "annual-events"
PANEL_ELEMENT: Final = "annual-events-panel"
PANEL_STATIC_URL: Final = "/annual_events_static"

MAX_LIST_LIMIT: Final = 500
MAX_SEARCH_LIMIT: Final = 100
MAX_BETWEEN_DAYS: Final = 3660
MAX_BETWEEN_RESULTS: Final = 5000

BUILT_IN_CATEGORIES: Final = (
    "birthday",
    "anniversary",
    "pet",
    "memorial",
    "holiday",
    "work",
    "name_day",
    "custom",
)
