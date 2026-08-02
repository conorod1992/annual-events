"""Annual Events integration setup."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig  # type: ignore[attr-defined]
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_SHOW_PANEL,
    DEFAULT_SHOW_PANEL,
    DOMAIN,
    PANEL_ELEMENT,
    PANEL_STATIC_URL,
    PANEL_URL,
    PLATFORMS,
    SIGNAL_UPDATED,
    VERSION,
)
from .manager import AnnualEventsManager
from .services import async_register_services, async_unregister_services
from .storage import AnnualEventsStorage
from .websocket_api import async_register_websocket_commands

type AnnualEventsConfigEntry = ConfigEntry[AnnualEventsManager]

_DATA_FRONTEND_REGISTERED = f"{DOMAIN}_frontend_registered"
_DATA_WEBSOCKET_REGISTERED = f"{DOMAIN}_websocket_registered"


async def async_setup_entry(hass: HomeAssistant, entry: AnnualEventsConfigEntry) -> bool:
    """Set up Annual Events from a config entry."""
    manager = AnnualEventsManager(
        AnnualEventsStorage(hass),
        lambda: async_dispatcher_send(hass, SIGNAL_UPDATED),
    )
    try:
        await manager.async_load()
    except Exception as err:
        raise ConfigEntryError(
            "Annual Events storage could not be loaded; stored data was not changed"
        ) from err

    entry.runtime_data = manager
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    if not hass.data.get(_DATA_WEBSOCKET_REGISTERED):
        async_register_websocket_commands(hass)
        hass.data[_DATA_WEBSOCKET_REGISTERED] = True

    await async_register_services(hass)
    await _async_setup_frontend(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: AnnualEventsConfigEntry) -> bool:
    """Unload platforms and integration-owned UI/action registrations."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    remaining = [
        item
        for item in hass.config_entries.async_entries(DOMAIN)
        if item.entry_id != entry.entry_id
    ]
    if not remaining:
        async_unregister_services(hass)
    return unload_ok


async def _async_options_updated(hass: HomeAssistant, entry: AnnualEventsConfigEntry) -> None:
    """Reload after integration-wide options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_setup_frontend(hass: HomeAssistant, entry: AnnualEventsConfigEntry) -> None:
    """Serve and register the build-free management panel."""
    if not hass.data.get(_DATA_FRONTEND_REGISTERED):
        frontend_dir = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_STATIC_URL, str(frontend_dir), True)]
        )
        hass.data[_DATA_FRONTEND_REGISTERED] = True

    frontend.async_remove_panel(hass, PANEL_URL, warn_if_unknown=False)
    if entry.options.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL):
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title="Annual Events",
            sidebar_icon="mdi:calendar-heart",
            module_url=f"{PANEL_STATIC_URL}/annual-events-panel.js?v={VERSION}",
            require_admin=False,
            config_panel_domain=DOMAIN,
        )
