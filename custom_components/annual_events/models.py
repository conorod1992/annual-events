"""Typed data model and validation for Annual Events."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID, uuid4

from .const import (
    MAX_ADVANCE_NOTICE_DAYS,
    PROACTIVE_MODE_DEFAULT,
    PROACTIVE_MODES,
)

_CATEGORY_RE = re.compile(r"^[\w][\w -]{0,63}$", re.UNICODE)
_ICON_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*:[a-z0-9][a-z0-9_-]*$")


class EventValidationError(ValueError):
    """Raised when an annual event is invalid."""


class EventNotFoundError(KeyError):
    """Raised when an event ID is unknown."""


class DuplicateEventIdError(EventValidationError):
    """Raised when an event ID already exists."""


def utc_now_iso() -> str:
    """Return a stable UTC timestamp."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _clean_text(value: Any, field: str, *, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise EventValidationError(f"{field} is required")
        return None
    if not isinstance(value, str):
        raise EventValidationError(f"{field} must be a string")
    result = " ".join(value.split())
    if required and not result:
        raise EventValidationError(f"{field} must not be empty")
    return result or None


def _clean_aliases(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or isinstance(value, str):
        raise EventValidationError("aliases must be a list of strings")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        alias = _clean_text(item, "alias", required=True)
        assert alias is not None
        key = alias.casefold()
        if key not in seen:
            seen.add(key)
            result.append(alias)
    return tuple(result)


def _clean_advance_days(value: Any) -> tuple[int, ...]:
    """Validate and normalize persisted per-event advance offsets."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)) or isinstance(value, str):
        raise EventValidationError("proactive_advance_days must be a list of day offsets")
    result: set[int] = set()
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise EventValidationError("proactive advance days must be integers")
        if not 1 <= item <= MAX_ADVANCE_NOTICE_DAYS:
            raise EventValidationError(
                f"proactive advance days must be from 1 to {MAX_ADVANCE_NOTICE_DAYS}"
            )
        result.add(item)
    return tuple(sorted(result, reverse=True))


def _validate_components(month: Any, day: Any, year: Any) -> tuple[int, int, int | None]:
    if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
        raise EventValidationError("month must be an integer from 1 to 12")
    if isinstance(day, bool) or not isinstance(day, int):
        raise EventValidationError("day must be an integer")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999
    ):
        raise EventValidationError("year must be an integer from 1 to 9999")
    try:
        validation_year = year if year is not None else (2000 if month == 2 and day == 29 else 2001)
        date(validation_year, month, day)
    except ValueError as err:
        raise EventValidationError("day is not valid for the selected month") from err
    return month, day, year


@dataclass(frozen=True, slots=True)
class AnnualEvent:
    """A single annual event record."""

    id: str
    name: str
    month: int
    day: int
    year: int | None = None
    category: str | None = None
    aliases: tuple[str, ...] = ()
    icon: str | None = None
    notes: str | None = None
    important: bool = False
    enabled: bool = True
    expose_entity: bool = False
    proactive_mode: str = PROACTIVE_MODE_DEFAULT
    proactive_advance_days: tuple[int, ...] = ()
    proactive_day_of: bool = True
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def create(cls, data: Mapping[str, Any]) -> AnnualEvent:
        """Validate input and create a new record."""
        now = utc_now_iso()
        payload = dict(data)
        payload.setdefault("id", str(uuid4()))
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AnnualEvent:
        """Deserialize and validate a stored record."""
        event_id = _clean_text(data.get("id"), "id", required=True)
        name = _clean_text(data.get("name"), "name", required=True)
        assert event_id is not None and name is not None
        try:
            parsed_id = str(UUID(event_id))
        except (ValueError, AttributeError) as err:
            raise EventValidationError("id must be a valid UUID") from err
        month, day, year = _validate_components(
            data.get("month"), data.get("day"), data.get("year")
        )
        category = _clean_text(data.get("category"), "category")
        if category is not None and not _CATEGORY_RE.fullmatch(category):
            raise EventValidationError("category contains unsupported characters")
        icon = _clean_text(data.get("icon"), "icon")
        if icon is not None and not _ICON_RE.fullmatch(icon):
            raise EventValidationError("icon must be a Home Assistant icon ID such as mdi:calendar")
        notes = _clean_text(data.get("notes"), "notes")
        created_at = _clean_text(data.get("created_at"), "created_at", required=True)
        updated_at = _clean_text(data.get("updated_at"), "updated_at", required=True)
        assert created_at is not None and updated_at is not None
        for timestamp, field in ((created_at, "created_at"), (updated_at, "updated_at")):
            try:
                datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError as err:
                raise EventValidationError(f"{field} must be an ISO timestamp") from err
        bool_fields: dict[str, bool] = {}
        for field, default in (
            ("important", False),
            ("enabled", True),
            ("expose_entity", False),
            ("proactive_day_of", True),
        ):
            value = data.get(field, default)
            if not isinstance(value, bool):
                raise EventValidationError(f"{field} must be a boolean")
            bool_fields[field] = value
        proactive_mode = data.get("proactive_mode", PROACTIVE_MODE_DEFAULT)
        if not isinstance(proactive_mode, str) or proactive_mode not in PROACTIVE_MODES:
            raise EventValidationError(
                f"proactive_mode must be one of: {', '.join(PROACTIVE_MODES)}"
            )
        return cls(
            id=parsed_id,
            name=name,
            month=month,
            day=day,
            year=year,
            category=category,
            aliases=_clean_aliases(data.get("aliases")),
            icon=icon,
            notes=notes,
            proactive_mode=proactive_mode,
            proactive_advance_days=_clean_advance_days(data.get("proactive_advance_days")),
            created_at=created_at,
            updated_at=updated_at,
            **bool_fields,
        )

    def updated(self, changes: Mapping[str, Any]) -> AnnualEvent:
        """Return a validated copy with explicit changes applied."""
        forbidden = {"id", "created_at", "updated_at"} & changes.keys()
        if forbidden:
            raise EventValidationError(f"fields cannot be updated: {', '.join(sorted(forbidden))}")
        payload = self.to_dict()
        payload.update(changes)
        payload["updated_at"] = utc_now_iso()
        return self.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        result = asdict(self)
        result["aliases"] = list(self.aliases)
        result["proactive_advance_days"] = list(self.proactive_advance_days)
        return result

    def with_timestamps(self, *, created_at: str, updated_at: str) -> AnnualEvent:
        """Replace timestamps, primarily for deterministic tests."""
        return replace(self, created_at=created_at, updated_at=updated_at)


@dataclass(frozen=True, slots=True)
class EventOccurrence:
    """A concrete occurrence of an annual record."""

    event_id: str
    name: str
    category: str | None
    occurrence_date: date
    occurrence_number: int | None
    important: bool

    def to_dict(self, *, relative_to: date | None = None) -> dict[str, Any]:
        """Serialize this occurrence."""
        result: dict[str, Any] = {
            "event_id": self.event_id,
            "name": self.name,
            "category": self.category,
            "occurrence_date": self.occurrence_date.isoformat(),
            "occurrence_number": self.occurrence_number,
            "important": self.important,
        }
        if relative_to is not None:
            result["days_until"] = (self.occurrence_date - relative_to).days
        return result
