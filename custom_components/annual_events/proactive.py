"""Restart-safe proactive occurrence event delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol, cast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EMIT_DAY_OF,
    CONF_TRIGGER_TIME,
    DEFAULT_EMIT_DAY_OF,
    DEFAULT_TRIGGER_TIME,
    DELIVERY_RETENTION_DAYS,
    DELIVERY_STORAGE_KEY,
    DELIVERY_STORAGE_VERSION,
    EVENT_OCCURRENCE,
    MAX_DELIVERY_LEDGER_ENTRIES,
    PROACTIVE_MODE_CUSTOM,
    PROACTIVE_MODE_OFF,
    SIGNAL_UPDATED,
)
from .helpers import get_advance_notice_days, get_policy
from .manager import AnnualEventsManager
from .models import AnnualEvent, EventOccurrence


class DeliveryStorageProtocol(Protocol):
    """Small persistence interface used by the coordinator and tests."""

    async def async_load(self) -> dict[str, str]: ...

    async def async_save(self, deliveries: dict[str, str]) -> None: ...


class DeliveryStorage:
    """Persist logical delivery IDs separately from event records."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](
            hass,
            DELIVERY_STORAGE_VERSION,
            f"{DELIVERY_STORAGE_KEY}.{entry_id}",
        )

    async def async_load(self) -> dict[str, str]:
        """Load the ledger without silently discarding deduplication state."""
        data = await self._store.async_load()
        if data is None:
            return {}
        if not isinstance(data, dict) or not isinstance(data.get("deliveries"), dict):
            raise ValueError("Annual Events delivery storage is invalid")
        deliveries: dict[str, str] = {}
        for key, delivered_on in data["deliveries"].items():
            if not isinstance(key, str) or not isinstance(delivered_on, str):
                raise ValueError("Annual Events delivery storage contains an invalid row")
            try:
                date.fromisoformat(delivered_on)
            except ValueError as err:
                raise ValueError("Annual Events delivery storage contains an invalid date") from err
            deliveries[key] = delivered_on
        return deliveries

    async def async_save(self, deliveries: dict[str, str]) -> None:
        """Atomically persist a deterministic bounded ledger."""
        await self._store.async_save({"deliveries": dict(sorted(deliveries.items()))})


class ProactiveEventCoordinator:
    """Reconcile due notifications against a persistent delivery ledger."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry[AnnualEventsManager],
        manager: AnnualEventsManager,
        storage: DeliveryStorageProtocol | None = None,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._manager = manager
        self._storage = storage or DeliveryStorage(hass, entry.entry_id)
        self._deliveries: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._unsubscribers: list[Callable[[], None]] = []

    @property
    def trigger_time(self) -> time:
        """Return the configured local daily trigger time."""
        value = self._entry.options.get(CONF_TRIGGER_TIME, DEFAULT_TRIGGER_TIME)
        if isinstance(value, time):
            return value
        return time.fromisoformat(cast(str, value))

    async def async_start(self) -> None:
        """Load delivery state, attach listeners, and catch up when due."""
        try:
            self._deliveries = await self._storage.async_load()
            trigger = self.trigger_time
            self._unsubscribers.append(
                async_track_time_change(
                    self._hass,
                    self._async_time_changed,
                    hour=trigger.hour,
                    minute=trigger.minute,
                    second=trigger.second,
                )
            )
            self._unsubscribers.append(
                async_dispatcher_connect(self._hass, SIGNAL_UPDATED, self._events_updated)
            )
            now = dt_util.now()
            await self._async_prune(now.date())
            if now.time() >= trigger:
                await self.async_reconcile(now.date())
        except Exception:
            self.async_stop()
            raise

    @callback
    def async_stop(self) -> None:
        """Detach daily and collection listeners."""
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    @callback
    def _events_updated(self) -> None:
        """Catch up a newly relevant edited occurrence after trigger time."""
        now = dt_util.now()
        if now.time() >= self.trigger_time:
            self._hass.async_create_task(
                self.async_reconcile(now.date()), "annual_events_reconcile_deliveries"
            )

    async def _async_time_changed(self, now: datetime) -> None:
        """Run the scheduled local-date reconciliation."""
        await self.async_reconcile(dt_util.as_local(now).date())

    @staticmethod
    def _delivery_key(
        occurrence: EventOccurrence, trigger: str, advance_days: int | None = None
    ) -> str:
        suffix = str(advance_days) if advance_days is not None else "-"
        return f"{occurrence.event_id}|{occurrence.occurrence_date.isoformat()}|{trigger}|{suffix}"

    def _effective_settings(
        self, event: AnnualEvent, global_days: tuple[int, ...], global_day_of: bool
    ) -> tuple[tuple[int, ...], bool]:
        if event.proactive_mode == PROACTIVE_MODE_OFF:
            return (), False
        if event.proactive_mode == PROACTIVE_MODE_CUSTOM:
            return event.proactive_advance_days, event.proactive_day_of
        return global_days, global_day_of

    async def _async_prune(self, today: date) -> None:
        cutoff = today - timedelta(days=DELIVERY_RETENTION_DAYS)
        pruned = {
            key: delivered_on
            for key, delivered_on in self._deliveries.items()
            if date.fromisoformat(delivered_on) >= cutoff
        }
        if len(pruned) > MAX_DELIVERY_LEDGER_ENTRIES:
            newest = sorted(pruned.items(), key=lambda item: (item[1], item[0]))[
                -MAX_DELIVERY_LEDGER_ENTRIES:
            ]
            pruned = dict(newest)
        if pruned != self._deliveries:
            self._deliveries = pruned
            await self._storage.async_save(self._deliveries)

    async def _async_emit_once(
        self,
        occurrence: EventOccurrence,
        *,
        today: date,
        trigger: str,
        advance_days: int | None = None,
    ) -> None:
        key = self._delivery_key(occurrence, trigger, advance_days)
        if key in self._deliveries:
            return
        self._deliveries[key] = today.isoformat()
        try:
            await self._storage.async_save(self._deliveries)
        except Exception:
            self._deliveries.pop(key, None)
            raise
        payload = occurrence.to_dict(relative_to=today)
        payload["trigger"] = trigger
        if advance_days is not None:
            payload["advance_days"] = advance_days
        self._hass.bus.async_fire(EVENT_OCCURRENCE, payload)

    async def async_reconcile(self, today: date | None = None) -> None:
        """Emit all logical notifications due for one local calendar date."""
        today = today or dt_util.now().date()
        async with self._lock:
            await self._async_prune(today)
            policy = get_policy(self._hass)
            global_days = get_advance_notice_days(self._entry)
            global_day_of = bool(self._entry.options.get(CONF_EMIT_DAY_OF, DEFAULT_EMIT_DAY_OF))
            enabled_events = [event for event in self._manager.async_list_events() if event.enabled]
            advance_days = set(global_days)
            for event in enabled_events:
                if event.proactive_mode == PROACTIVE_MODE_CUSTOM:
                    advance_days.update(event.proactive_advance_days)

            for days in sorted(advance_days, reverse=True):
                advance_date = today + timedelta(days=days)
                occurrences = self._manager.async_get_occurrences_between(
                    advance_date,
                    advance_date,
                    policy=policy,
                    enabled_only=True,
                )
                for occurrence in occurrences:
                    event = self._manager.async_get_event(occurrence.event_id)
                    effective_days, _ = self._effective_settings(event, global_days, global_day_of)
                    if days not in effective_days:
                        continue
                    await self._async_emit_once(
                        occurrence,
                        today=today,
                        trigger="advance",
                        advance_days=days,
                    )

            current = self._manager.async_get_occurrences_between(
                today,
                today,
                policy=policy,
                enabled_only=True,
            )
            for occurrence in current:
                event = self._manager.async_get_event(occurrence.event_id)
                _, emit_day_of = self._effective_settings(event, global_days, global_day_of)
                if not emit_day_of:
                    continue
                await self._async_emit_once(
                    occurrence,
                    today=today,
                    trigger="today",
                )
