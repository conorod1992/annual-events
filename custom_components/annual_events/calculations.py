"""Pure annual-date and search calculations."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from enum import StrEnum

from .models import AnnualEvent, EventOccurrence, EventValidationError


class LeapDayPolicy(StrEnum):
    """How 29 February is observed in non-leap years."""

    FEB_28 = "feb_28"
    MAR_1 = "mar_1"
    LEAP_ONLY = "leap_only"


def is_leap_year(year: int) -> bool:
    """Return whether a Gregorian year is a leap year."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def occurrence_date(event: AnnualEvent, year: int, policy: LeapDayPolicy) -> date | None:
    """Resolve an event into a concrete date for a year."""
    if event.month != 2 or event.day != 29 or is_leap_year(year):
        return date(year, event.month, event.day)
    if policy is LeapDayPolicy.FEB_28:
        return date(year, 2, 28)
    if policy is LeapDayPolicy.MAR_1:
        return date(year, 3, 1)
    return None


def occurrence_number(event: AnnualEvent, occurrence: date) -> int | None:
    """Return anniversary number; the original date is occurrence zero."""
    if event.year is None:
        return None
    return occurrence.year - event.year


def next_occurrence(event: AnnualEvent, today: date, policy: LeapDayPolicy) -> EventOccurrence:
    """Return the first occurrence on or after today."""
    first_year = max(today.year, event.year) if event.year is not None else today.year
    for year in range(first_year, 10000):
        candidate = occurrence_date(event, year, policy)
        if candidate is not None and candidate >= today:
            return EventOccurrence(
                event_id=event.id,
                name=event.name,
                category=event.category,
                occurrence_date=candidate,
                occurrence_number=occurrence_number(event, candidate),
                important=event.important,
            )
    raise EventValidationError("no representable future occurrence")


def days_until(event: AnnualEvent, today: date, policy: LeapDayPolicy) -> int:
    """Return whole local calendar days until the next occurrence."""
    return (next_occurrence(event, today, policy).occurrence_date - today).days


def occurrences_between(
    events: list[AnnualEvent] | tuple[AnnualEvent, ...],
    start: date,
    end: date,
    policy: LeapDayPolicy,
) -> list[EventOccurrence]:
    """Expand enabled records into inclusive concrete occurrences."""
    if end < start:
        raise EventValidationError("end date must not be before start date")
    result: list[EventOccurrence] = []
    for event in events:
        if not event.enabled:
            continue
        for year in range(start.year, end.year + 1):
            if event.year is not None and year < event.year:
                continue
            concrete = occurrence_date(event, year, policy)
            if concrete is not None and start <= concrete <= end:
                result.append(
                    EventOccurrence(
                        event_id=event.id,
                        name=event.name,
                        category=event.category,
                        occurrence_date=concrete,
                        occurrence_number=occurrence_number(event, concrete),
                        important=event.important,
                    )
                )
    return sorted(
        result,
        key=lambda item: (item.occurrence_date, normalize_text(item.name), item.event_id),
    )


def upcoming_occurrences(
    events: list[AnnualEvent] | tuple[AnnualEvent, ...],
    today: date,
    days: int,
    policy: LeapDayPolicy,
) -> list[EventOccurrence]:
    """Return occurrences from today through the inclusive horizon."""
    if days < 0:
        raise EventValidationError("days must be zero or greater")
    return occurrences_between(events, today, today + timedelta(days=days), policy)


_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_text(value: str) -> str:
    """Normalize Unicode, punctuation, case and whitespace for search."""
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(_NON_WORD.sub(" ", value).split())


def search_rank(event: AnnualEvent, query: str) -> tuple[int, str, str] | None:
    """Return a deterministic search rank, or None when unmatched."""
    needle = normalize_text(query)
    if not needle:
        return (0, normalize_text(event.name), event.id)
    name = normalize_text(event.name)
    aliases = [normalize_text(alias) for alias in event.aliases]
    category = normalize_text(event.category or "")
    notes = normalize_text(event.notes or "")
    if name == needle:
        score = 0
    elif needle in aliases:
        score = 1
    elif name.startswith(needle):
        score = 2
    elif any(alias.startswith(needle) for alias in aliases):
        score = 3
    elif needle in name:
        score = 4
    elif any(needle in alias for alias in aliases):
        score = 5
    elif needle in category:
        score = 6
    elif needle in notes:
        score = 7
    else:
        return None
    return (score, name, event.id)


def search_events(events: list[AnnualEvent], query: str, limit: int) -> list[AnnualEvent]:
    """Search records with exact, alias, prefix and substring ranking."""
    ranked = [(rank, event) for event in events if (rank := search_rank(event, query))]
    ranked.sort(key=lambda item: item[0])
    return [event for _, event in ranked[:limit]]
