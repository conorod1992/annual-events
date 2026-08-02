"""Tests for pure annual-date calculations."""

from datetime import date

import pytest

from custom_components.annual_events.calculations import (
    LeapDayPolicy,
    days_until,
    next_occurrence,
    occurrence_date,
    occurrences_between,
)
from custom_components.annual_events.models import AnnualEvent


def make_event(**changes) -> AnnualEvent:
    return AnnualEvent.create({"name": "Event", "month": 8, "day": 7, **changes})


@pytest.mark.parametrize(
    ("today", "expected", "days"),
    [
        (date(2026, 1, 1), date(2026, 8, 7), 218),
        (date(2026, 9, 1), date(2027, 8, 7), 340),
        (date(2026, 8, 7), date(2026, 8, 7), 0),
        (date(2026, 12, 31), date(2027, 8, 7), 219),
    ],
)
def test_next_occurrence(today, expected, days):
    event = make_event()
    result = next_occurrence(event, today, LeapDayPolicy.FEB_28)
    assert result.occurrence_date == expected
    assert days_until(event, today, LeapDayPolicy.FEB_28) == days
    assert result.occurrence_number is None


def test_original_date_is_occurrence_zero():
    event = make_event(year=2000)
    assert next_occurrence(event, date(2000, 8, 7), LeapDayPolicy.FEB_28).occurrence_number == 0
    assert next_occurrence(event, date(2026, 1, 1), LeapDayPolicy.FEB_28).occurrence_number == 26


def test_known_future_original_year_never_returns_negative_occurrence():
    event = make_event(year=2030)
    result = next_occurrence(event, date(2026, 1, 1), LeapDayPolicy.FEB_28)
    assert result.occurrence_date == date(2030, 8, 7)
    assert result.occurrence_number == 0
    assert (
        occurrences_between([event], date(2026, 1, 1), date(2029, 12, 31), LeapDayPolicy.FEB_28)
        == []
    )


@pytest.mark.parametrize(
    ("policy", "year", "expected"),
    [
        (LeapDayPolicy.FEB_28, 2025, date(2025, 2, 28)),
        (LeapDayPolicy.MAR_1, 2025, date(2025, 3, 1)),
        (LeapDayPolicy.LEAP_ONLY, 2025, None),
        (LeapDayPolicy.FEB_28, 2024, date(2024, 2, 29)),
        (LeapDayPolicy.MAR_1, 2000, date(2000, 2, 29)),
        (LeapDayPolicy.LEAP_ONLY, 2100, None),
    ],
)
def test_leap_day_policies(policy, year, expected):
    assert occurrence_date(make_event(month=2, day=29), year, policy) == expected


def test_leap_only_skips_to_next_leap_year():
    result = next_occurrence(make_event(month=2, day=29), date(2025, 1, 1), LeapDayPolicy.LEAP_ONLY)
    assert result.occurrence_date == date(2028, 2, 29)


def test_range_crosses_new_year_and_sort_is_stable():
    jan = make_event(name="Zulu", month=1, day=2)
    dec_b = make_event(name="Beta", month=12, day=30)
    dec_a = make_event(name="Alpha", month=12, day=30)
    result = occurrences_between(
        [jan, dec_b, dec_a], date(2026, 12, 29), date(2027, 1, 3), LeapDayPolicy.FEB_28
    )
    assert [(item.occurrence_date, item.name) for item in result] == [
        (date(2026, 12, 30), "Alpha"),
        (date(2026, 12, 30), "Beta"),
        (date(2027, 1, 2), "Zulu"),
    ]


def test_multi_year_range_repeats_same_event_and_is_inclusive():
    event = make_event(month=1, day=1, year=2020)
    result = occurrences_between([event], date(2025, 1, 1), date(2027, 1, 1), LeapDayPolicy.FEB_28)
    assert [item.occurrence_date for item in result] == [
        date(2025, 1, 1),
        date(2026, 1, 1),
        date(2027, 1, 1),
    ]
    assert [item.occurrence_number for item in result] == [5, 6, 7]


def test_disabled_events_are_omitted():
    assert (
        occurrences_between(
            [make_event(enabled=False)], date(2026, 1, 1), date(2026, 12, 31), LeapDayPolicy.FEB_28
        )
        == []
    )
