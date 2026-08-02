"""Tests for deterministic search ranking."""

from custom_components.annual_events.calculations import normalize_text, search_events
from custom_components.annual_events.models import AnnualEvent


def make(name, **changes):
    return AnnualEvent.create({"name": name, "month": 1, "day": 1, **changes})


def test_case_punctuation_unicode_and_aliases():
    mum = make("Mum\u2019s birthday", aliases=["Mam"])
    assert search_events([mum], "MUM", 10) == [mum]
    assert search_events([mum], "mum", 10) == [mum]
    assert search_events([mum], "mam", 10) == [mum]
    assert normalize_text("  Mum\u2019s   Birthday ") == "mum s birthday"


def test_exact_and_alias_rank_before_prefix_and_substring():
    substring = make("My Mum event")
    prefix = make("Mum birthday")
    alias = make("Mother birthday", aliases=["Mum"])
    exact = make("Mum")
    assert search_events([substring, prefix, alias, exact], "mum", 10) == [
        exact,
        alias,
        prefix,
        substring,
    ]


def test_category_notes_and_limits_are_stable():
    alpha = make("Alpha", category="birthday")
    beta = make("Beta", notes="Birthday celebration")
    gamma = make("Gamma", category="birthday")
    assert search_events([gamma, beta, alpha], "birthday", 2) == [alpha, gamma]


def test_no_match():
    assert search_events([make("Oscar")], "mum", 10) == []
