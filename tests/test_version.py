"""Tests for release metadata consistency."""

import json
import tomllib
from pathlib import Path

from custom_components.annual_events.const import VERSION

_ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_are_consistent():
    """Keep package, manifest, diagnostics, and frontend cache versions aligned."""
    manifest = json.loads(
        (_ROOT / "custom_components" / "annual_events" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert manifest["version"] == VERSION == pyproject["project"]["version"]
