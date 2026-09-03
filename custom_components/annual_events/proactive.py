"""Restart-safe proactive occurrence event delivery."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
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
    MAX_PROACTIVE_CATCHUP_DAYS,
    PROACTIVE_MODE_CUSTOM,
    PROACTIVE_MODE_OFF,
    SIGNAL_UPDATED,
)
from .helpers import get_advance_notice_days, get_policy
from .manager import AnnualEventsManager
from .models import AnnualEvent, EventOccurrence

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DeliveryState:
    """Persisted proactive delivery state."""

    deliveries: dict[str, str]
    last_reconciled_date: date | None = None
    pending: dict[str, dict[str, Any]] = field(default_factory=dict)


class DeliveryStorageProtocol(Protocol):
    """Small persistence interface used by the coordinator and tests."""

    async def async_load(self) -> DeliveryState: ...

    async def async_save(self, state: DeliveryState) -> None: ...


class DeliveryStorage:
    """Persist logical delivery IDs separately from event records."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store = Store[dict[str, Any]](
            hass,
            DELIVERY_STORAGE_VERSION,
            f"{DELIVERY_STORAGE_KEY}.{entry_id}",
        )

    @staticmethod
    def _validate_pending_row(key: Any, row: Any) -> tuple[str, dict[str, Any]]:
        """Validate one persisted pending delivery before it can be replayed."""
        if not isinstance(key, str) or not isinstance(row, dict):
            raise ValueError("Annual Events delivery storage contains an invalid pending row")
        delivered_on = row.get("delivered_on")
        payload = row.get("payload")
        if not isinstance(delivered_on, str) or not isinstance(payload, dict):
            raise ValueError("Annual Events delivery storage contains an invalid pending row")
        try:
            date.fromisoformat(delivered_on)
        except ValueError as err:
            raise ValueError(
                "Annual Events delivery storage contains an invalid pending date"
            ) from err

        required_strings = ("event_id", "name", "occurrence_date", "trigger")
        if any(not isinstance(payload.get(field_name), str) for field_name in required_strings):
            raise ValueError("Annual Events delivery storage contains an invalid pending payload")
        try:
            date.fromisoformat(payload["occurrence_date"])
        except ValueError as err:
            raise ValueError(
                "Annual Events delivery storage contains an invalid pending occurrence date"
            ) from err
        if payload["trigger"] not in {"advance", "today"}:
            raise ValueError("Annual Events delivery storage contains an invalid pending trigger")
        if payload.get("category") is not None and not isinstance(payload.get("category"), str):
            raise ValueError("Annual Events delivery storage contains an invalid pending category")
        occurrence_number = payload.get("occurrence_number")
        if occurrence_number is not None and (
            isinstance(occurrence_number, bool) or not isinstance(occurrence_number, int)
        ):
            raise ValueError(
                "Annual Events delivery storage contains an invalid pending occurrence number"
            )
        if not isinstance(payload.get("important"), bool):
            raise ValueError(
                "Annual Events delivery storage contains an invalid pending importance"
            )
        days_until = payload.get("days_until")
        if isinstance(days_until, bool) or not isinstance(days_until, int):
            raise ValueError("Annual Events delivery storage contains invalid pending days_until")
        advance_days = payload.get("advance_days")
        if advance_days is not None and (
            isinstance(advance_days, bool) or not isinstance(advance_days, int)
        ):
            raise ValueError("Annual Events delivery storage contains invalid pending advance_days")
        return key, {"delivered_on": delivered_on, "payload": dict(payload)}

    async def async_load(self) -> DeliveryState:
        """Load the ledger, pending outbox, and optional restart catch-up checkpoint."""
        data = await self._store.async_load()
        if data is None:
            return DeliveryState({})
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

        raw_pending = data.get("pending", {})
        if not isinstance(raw_pending, dict):
            raise ValueError("Annual Events delivery storage contains an invalid pending outbox")
        pending = dict(self._validate_pending_row(key, row) for key, row in raw_pending.items())

        last_reconciled_date: date | None = None
        raw_last_reconciled = data.get("last_reconciled_date")
        if raw_last_reconciled is not None:
            if not isinstance(raw_last_reconciled, str):
                raise ValueError("Annual Events delivery storage contains an invalid checkpoint")
            try:
                last_reconciled_date = date.fromisoformat(raw_last_reconciled)
            except ValueError as err:
                raise ValueError(
                    "Annual Events delivery storage contains an invalid checkpoint date"
                ) from err
        return DeliveryState(deliveries, last_reconciled_date, pending)

    async def async_save(self, state: DeliveryState) -> None:
        """Atomically persist a deterministic bounded ledger, outbox and checkpoint."""
        payload: dict[str, Any] = {
            "deliveries": dict(sorted(state.deliveries.items())),
            "pending": {key: state.pending[key] for key in sorted(state.pending)},
        }
        if state.last_reconciled_date is not None:
            payload["last_reconciled_date"] = state.last_reconciled_date.isoformat()
        await self._store.async_save(payload)


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
        self._pending: dict[str, dict[str, Any]] = {}
        self._last_reconciled_date: date | None = None
        self._lock = asyncio.Lock()
        self._unsubscribers: list[Callable[[], None]] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._started = False
        self._stopped = False

    @property
    def trigger_time(self) -> time:
        """Return the configured local daily trigger time."""
        value = self._entry.options.get(CONF_TRIGGER_TIME, DEFAULT_TRIGGER_TIME)
        if isinstance(value, time):
            return value
        return time.fromisoformat(cast(str, value))

    async def async_start(self) -> None:
        """Load delivery state, attach listeners, replay pending work, and catch up."""
        if self._started:
            return
        self._started = True
        self._stopped = False
        try:
            try:
                state = await self._storage.async_load()
            except ValueError as err:
                _LOGGER.error(
                    "Annual Events proactive delivery storage is malformed and will be reset; "
                    "previously delivered reminders may be repeated: %s",
                    err,
                )
                state = DeliveryState({})
                await self._storage.async_save(state)
            self._deliveries = state.deliveries
            self._pending = state.pending
            self._last_reconciled_date = state.last_reconciled_date
            trigger = self.trigger_time
            self._unsubscribers.append(
                async_track_time_change(
                    self._hass,
                    self._time_changed,
                    hour=trigger.hour,
                    minute=trigger.minute,
                    second=trigger.second,
                )
            )
            self._unsubscribers.append(
                async_dispatcher_connect(self._hass, SIGNAL_UPDATED, self._events_updated)
            )
            await self._async_replay_pending()
            now = dt_util.now()
            await self._async_prune(now.date())
            await self._async_startup_reconcile(now)
        except Exception:
            self.async_stop()
            raise

    @callback
    def async_stop(self) -> None:
        """Detach listeners and cancel coordinator-owned reconciliation work."""
        self._started = False
        self._stopped = True
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        for task in tuple(self._tasks):
            task.cancel()
        self._tasks.clear()

    @callback
    def _schedule_reconcile(self, target_date: date) -> None:
        """Schedule one coordinator-owned reconciliation task."""
        if self._stopped or not self._started:
            return
        task = self._hass.async_create_task(
            self.async_reconcile(target_date), "annual_events_reconcile_deliveries"
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @callback
    def _events_updated(self) -> None:
        """Catch up a newly relevant edited occurrence after trigger time."""
        now = dt_util.now()
        if now.time() >= self.trigger_time:
            self._schedule_reconcile(now.date())

    @callback
    def _time_changed(self, now: datetime) -> None:
        """Schedule the daily local-date reconciliation."""
        self._schedule_reconcile(dt_util.as_local(now).date())

    async def _async_startup_reconcile(self, now: datetime) -> None:
        """Catch up completed trigger dates without replaying unbounded history."""
        today = now.date()
        after_trigger = now.time() >= self.trigger_time
        due_through = today if after_trigger else today - timedelta(days=1)

        if self._last_reconciled_date is None:
            if after_trigger:
                await self.async_reconcile(today)
            else:
                self._last_reconciled_date = due_through
                try:
                    await self._async_save_state()
                except Exception:
                    self._last_reconciled_date = None
                    raise
            return

        reconciled_today = False
        start = self._last_reconciled_date + timedelta(days=1)
        if start <= due_through:
            earliest = due_through - timedelta(days=MAX_PROACTIVE_CATCHUP_DAYS - 1)
            if start < earliest:
                _LOGGER.warning(
                    "Annual Events proactive catch-up is limited to %d days; dates before %s "
                    "will not be replayed",
                    MAX_PROACTIVE_CATCHUP_DAYS,
                    earliest.isoformat(),
                )
                start = earliest
            target = start
            while target <= due_through:
                await self.async_reconcile(target)
                reconciled_today = reconciled_today or target == today
                target += timedelta(days=1)

        # Re-run today's due set after a restart/reload even if it was already checkpointed.
        # The delivery ledger makes this idempotent and it closes the race where an event edit
        # was queued immediately before the previous coordinator stopped.
        if after_trigger and not reconciled_today:
            await self.async_reconcile(today)

    async def _async_save_state(self) -> None:
        """Persist the current delivery ledger, outbox and reconciliation checkpoint."""
        await self._storage.async_save(
            DeliveryState(
                dict(self._deliveries),
                self._last_reconciled_date,
                {key: dict(value) for key, value in self._pending.items()},
            )
        )

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
            await self._async_save_state()

    async def _async_fire_pending(self, key: str) -> None:
        """Fire one persisted outbox item and then mark it delivered."""
        pending = self._pending[key]
        payload = dict(cast(dict[str, Any], pending["payload"]))
        delivered_on = cast(str, pending["delivered_on"])
        self._hass.bus.async_fire(EVENT_OCCURRENCE, payload)

        self._pending.pop(key)
        self._deliveries[key] = delivered_on
        try:
            await self._async_save_state()
        except Exception:
            self._deliveries.pop(key, None)
            self._pending[key] = pending
            raise

    async def _async_replay_pending(self) -> None:
        """Replay persisted deliveries whose final delivered marker was never saved."""
        for key in sorted(tuple(self._pending)):
            if key in self._deliveries:
                self._pending.pop(key, None)
                await self._async_save_state()
                continue
            await self._async_fire_pending(key)

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
        if key not in self._pending:
            payload = occurrence.to_dict(relative_to=today)
            payload["trigger"] = trigger
            if advance_days is not None:
                payload["advance_days"] = advance_days
            self._pending[key] = {
                "delivered_on": today.isoformat(),
                "payload": payload,
            }
            try:
                await self._async_save_state()
            except Exception:
                self._pending.pop(key, None)
                raise
        await self._async_fire_pending(key)

    async def _async_mark_reconciled(self, target_date: date) -> None:
        """Advance the checkpoint only after the full date reconciles successfully."""
        if self._last_reconciled_date is not None and target_date <= self._last_reconciled_date:
            return
        previous = self._last_reconciled_date
        self._last_reconciled_date = target_date
        try:
            await self._async_save_state()
        except Exception:
            self._last_reconciled_date = previous
            raise

    async def async_reconcile(self, today: date | None = None) -> None:
        """Emit all logical notifications due for one local calendar date."""
        today = today or dt_util.now().date()
        if self._stopped:
            return
        async with self._lock:
            if self._stopped:
                return
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

            await self._async_mark_reconciled(today)
