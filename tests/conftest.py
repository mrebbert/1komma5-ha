"""Pytest configuration: load helpers.py without triggering the package init.

Tier 1 tests target pure helper functions only. We avoid loading
``custom_components/onekommafive/__init__.py`` (which imports Home Assistant
and other heavy runtime dependencies) by loading ``helpers.py`` directly
via ``importlib`` and exposing it as the top-level module ``helpers``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HELPERS_PATH = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "onekommafive"
    / "helpers.py"
)

_spec = importlib.util.spec_from_file_location("helpers", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["helpers"] = _helpers
_spec.loader.exec_module(_helpers)
