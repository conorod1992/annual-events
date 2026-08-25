"""UI configuration flow for Annual Events."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .calculations import LeapDayPolicy
from .const import (
    CONF_ADVANCE_NOTICE_DAYS,
    CONF_EMIT_DAY_OF,
    CONF_LEAP_DAY_POLICY,
    CONF_SHOW_PANEL,
    CONF_TRIGGER_TIME,
    CONF_UPCOMING_DAYS,
    DEFAULT_ADVANCE_NOTICE_DAYS,
    DEFAULT_EMIT_DAY_OF,
    DEFAULT_LEAP_DAY_POLICY,
    DEFAULT_SHOW_PANEL,
    DEFAULT_TRIGGER_TIME,
    DEFAULT_UPCOMING_DAYS,
    DOMAIN,
    NAME,
)


class AnnualEventsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single collection-level entry."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Create a credential-free entry after explicit confirmation."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> AnnualEventsOptionsFlow:
        """Return the options flow."""
        return AnnualEventsOptionsFlow()


class AnnualEventsOptionsFlow(config_entries.OptionsFlow):
    """Configure collection-wide recurrence and UI behaviour."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_LEAP_DAY_POLICY,
                        default=options.get(CONF_LEAP_DAY_POLICY, DEFAULT_LEAP_DAY_POLICY),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[policy.value for policy in LeapDayPolicy],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="leap_day_policy",
                        )
                    ),
                    vol.Required(
                        CONF_UPCOMING_DAYS,
                        default=options.get(CONF_UPCOMING_DAYS, DEFAULT_UPCOMING_DAYS),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=3660)),
                    vol.Required(
                        CONF_SHOW_PANEL,
                        default=options.get(CONF_SHOW_PANEL, DEFAULT_SHOW_PANEL),
                    ): bool,
                    vol.Required(
                        CONF_ADVANCE_NOTICE_DAYS,
                        default=options.get(CONF_ADVANCE_NOTICE_DAYS, DEFAULT_ADVANCE_NOTICE_DAYS),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=366,
                            step=1,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                    vol.Required(
                        CONF_TRIGGER_TIME,
                        default=options.get(CONF_TRIGGER_TIME, DEFAULT_TRIGGER_TIME),
                    ): selector.TimeSelector(),
                    vol.Required(
                        CONF_EMIT_DAY_OF,
                        default=options.get(CONF_EMIT_DAY_OF, DEFAULT_EMIT_DAY_OF),
                    ): selector.BooleanSelector(),
                }
            ),
        )
