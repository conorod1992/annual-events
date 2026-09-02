"""Tests for Annual Events icon validation."""

import pytest

from custom_components.annual_events.models import AnnualEvent, EventValidationError

from .conftest import event_data


def test_accepts_material_design_icon():
    event = AnnualEvent.create(event_data(icon="mdi:calendar-heart"))
    assert event.icon == "mdi:calendar-heart"


def test_accepts_home_assistant_custom_icon_namespace():
    event = AnnualEvent.create(event_data(icon="custom_icons:birthday-cake"))
    assert event.icon == "custom_icons:birthday-cake"


@pytest.mark.parametrize(
    "icon",
    (
        "calendar-heart",
        "mdi:",
        ":calendar",
        "mdi:calendar heart",
        "MDI:calendar",
    ),
)
def test_rejects_invalid_icon_ids(icon):
    with pytest.raises(EventValidationError, match="Home Assistant icon ID"):
        AnnualEvent.create(event_data(icon=icon))
