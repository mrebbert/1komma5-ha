"""Tests verifying translation files stay in sync with strings.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "onekommafive"
_STRINGS = _ROOT / "strings.json"
_TRANSLATIONS = _ROOT / "translations"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _flatten_keys(obj: dict, prefix: str = "") -> set[str]:
    """Collect all leaf and intermediate paths in a nested dict."""
    keys: set[str] = set()
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        keys.add(path)
        if isinstance(value, dict):
            keys |= _flatten_keys(value, path)
    return keys


@pytest.mark.parametrize(
    "locale_path", sorted(_TRANSLATIONS.glob("*.json")), ids=lambda p: p.stem
)
def test_translation_keys_match_strings(locale_path: Path) -> None:
    """Every key in strings.json must exist in each translation locale, and vice versa."""
    strings = _flatten_keys(_load(_STRINGS))
    locale = _flatten_keys(_load(locale_path))

    missing_in_locale = strings - locale
    extra_in_locale = locale - strings

    assert not missing_in_locale, (
        f"Keys present in strings.json but missing in {locale_path.name}: "
        f"{sorted(missing_in_locale)}"
    )
    assert not extra_in_locale, (
        f"Keys present in {locale_path.name} but missing in strings.json: {sorted(extra_in_locale)}"
    )


def test_strings_json_is_valid_json() -> None:
    """Sanity check — strings.json must be parseable JSON."""
    _load(_STRINGS)


@pytest.mark.parametrize(
    "locale_path", sorted(_TRANSLATIONS.glob("*.json")), ids=lambda p: p.stem
)
def test_translation_locale_is_valid_json(locale_path: Path) -> None:
    """Sanity check — every translation locale must be parseable JSON."""
    _load(locale_path)


def test_icons_json_keys_match_binary_sensor_translations() -> None:
    """Every translation_key in icons.json must have a matching entity name."""
    icons = _load(_ROOT / "icons.json")
    strings = _load(_STRINGS)

    icon_keys = set(icons["entity"]["binary_sensor"].keys())
    binary_sensor_names = set(strings["entity"]["binary_sensor"].keys())

    missing = icon_keys - binary_sensor_names
    assert not missing, (
        f"icons.json refers to unknown binary_sensor keys: {sorted(missing)}"
    )


def test_exception_translation_keys_are_referenced_from_services() -> None:
    """Every exceptions.* key in strings.json must appear in services.py."""
    exception_keys = set(_load(_STRINGS)["exceptions"].keys())
    services_source = (_ROOT / "services.py").read_text(encoding="utf-8")

    for key in exception_keys:
        assert key in services_source, (
            f"exceptions.{key} declared in strings.json but not raised in services.py"
        )
