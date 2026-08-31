"""Read-only Annual Events tools contributed to Home Assistant LLM APIs."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import llm as llm_component
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import llm
from homeassistant.helpers.llm import LLMContext, ToolInput

from .const import MAX_BETWEEN_DAYS, MAX_SEARCH_LIMIT
from .helpers import event_with_next, get_manager, get_policy, local_today, parse_date
from .schema import coerce_integer


class SearchAnnualEventsTool(llm.Tool):
    """Find records by name, alias or category."""

    name = "search_annual_events"
    description = "Search local annual events by a person's name, event name, alias, or category and return exact dates, days remaining, and age/anniversary number when known."
    parameters = vol.Schema(
        {
            vol.Required("query"): cv.string,
            vol.Optional("limit", default=10): vol.All(
                coerce_integer, vol.Range(min=1, max=MAX_SEARCH_LIMIT)
            ),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> dict[str, Any]:
        records = get_manager(hass).async_search_events(
            tool_input.tool_args["query"], limit=tool_input.tool_args["limit"]
        )
        return {
            "events": [event_with_next(hass, event) for event in records],
            "count": len(records),
        }


class UpcomingAnnualEventsTool(llm.Tool):
    """Find upcoming concrete occurrences."""

    name = "get_upcoming_annual_events"
    description = "Get annual events occurring from today through a requested number of local calendar days. Use for birthdays or important events coming up."
    parameters = vol.Schema(
        {
            vol.Optional("days", default=31): vol.All(
                coerce_integer, vol.Range(min=0, max=MAX_BETWEEN_DAYS)
            ),
            vol.Optional("important_only", default=False): cv.boolean,
            vol.Optional("category"): cv.string,
            vol.Optional("limit", default=50): vol.All(
                coerce_integer, vol.Range(min=1, max=MAX_SEARCH_LIMIT)
            ),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> dict[str, Any]:
        today = local_today()
        args = tool_input.tool_args
        records = get_manager(hass).async_get_upcoming(
            today,
            days=args["days"],
            policy=get_policy(hass),
            limit=args["limit"],
            important_only=args["important_only"],
            category=args.get("category"),
        )
        return {
            "occurrences": [item.to_dict(relative_to=today) for item in records],
            "count": len(records),
        }


class BetweenAnnualEventsTool(llm.Tool):
    """Find annual events within an inclusive date range."""

    name = "get_annual_events_between"
    description = "Get concrete annual event occurrences in an inclusive local date range, including ranges crossing New Year. Dates must be YYYY-MM-DD."
    parameters = vol.Schema(
        {
            vol.Required("start"): cv.string,
            vol.Required("end"): cv.string,
            vol.Optional("important_only", default=False): cv.boolean,
            vol.Optional("category"): cv.string,
            vol.Optional("limit", default=100): vol.All(
                coerce_integer, vol.Range(min=1, max=MAX_SEARCH_LIMIT)
            ),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> dict[str, Any]:
        args = tool_input.tool_args
        start, end = parse_date(args["start"], "start"), parse_date(args["end"], "end")
        if end < start or end - start > timedelta(days=MAX_BETWEEN_DAYS):
            raise HomeAssistantError(
                f"Range must be ordered and no longer than {MAX_BETWEEN_DAYS} days"
            )
        records = get_manager(hass).async_get_occurrences_between(
            start,
            end,
            policy=get_policy(hass),
            limit=args["limit"],
            important_only=args["important_only"],
            category=args.get("category"),
        )
        today = local_today()
        return {
            "occurrences": [item.to_dict(relative_to=today) for item in records],
            "count": len(records),
        }


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> llm_component.LLMTools:
    """Contribute safe read-only tools to supported Home Assistant LLM APIs."""
    return llm_component.LLMTools(
        tools=[SearchAnnualEventsTool(), UpcomingAnnualEventsTool(), BetweenAnnualEventsTool()],
        prompt=(
            "Use Annual Events tools for questions about locally stored birthdays, anniversaries, memorials, holidays, and other recurring yearly dates. "
            "Never infer an age when occurrence_number is null. These tools are read-only."
        ),
    )
