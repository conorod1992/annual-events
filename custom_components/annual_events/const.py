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
CONF_ADVANCE_NOTICE_DAYS: Final = "advance_notice_days"
CONF_TRIGGER_TIME: Final = "trigger_time"
CONF_EMIT_DAY_OF: Final = "emit_day_of"

DEFAULT_LEAP_DAY_POLICY: Final = "feb_28"
DEFAULT_UPCOMING_DAYS: Final = 30
DEFAULT_SHOW_PANEL: Final = True
# Kept as a scalar for compatibility with existing options written by v1.0.
DEFAULT_ADVANCE_NOTICE_DAYS: Final = 7
DEFAULT_TRIGGER_TIME: Final = "09:00:00"
DEFAULT_EMIT_DAY_OF: Final = True
MAX_ADVANCE_NOTICE_DAYS: Final = 366

PROACTIVE_MODE_DEFAULT: Final = "default"
PROACTIVE_MODE_CUSTOM: Final = "custom"
PROACTIVE_MODE_OFF: Final = "off"
PROACTIVE_MODES: Final = (
    PROACTIVE_MODE_DEFAULT,
    PROACTIVE_MODE_CUSTOM,
    PROACTIVE_MODE_OFF,
)

EVENT_OCCURRENCE: Final = "annual_events_occurrence"
DELIVERY_STORAGE_KEY: Final = "annual_events.deliveries"
DELIVERY_STORAGE_VERSION: Final = 1
DELIVERY_RETENTION_DAYS: Final = 400
MAX_DELIVERY_LEDGER_ENTRIES: Final = 5000

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
