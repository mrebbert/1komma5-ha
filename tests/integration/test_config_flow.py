"""Tier-2 tests for the config flow.

These tests stand up a real Home Assistant instance, mock the
``onekommafive`` library and walk through the integration's config flow
end-to-end.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.onekommafive.const import DOMAIN

# ----------------------------------------------------------------------------
# user flow — error paths (no entry is ever created, no setup_entry runs)
# ----------------------------------------------------------------------------


async def test_user_flow_invalid_credentials_shows_error(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An ``AuthenticationError`` from the library surfaces as ``invalid_auth``
    and the SDK's error detail lands in the log at WARNING level, with large
    HTML bodies collapsed to their title plus a byte count."""
    from onekommafive.errors import AuthenticationError

    html_body = (
        "<!DOCTYPE html><html><head><title>1KOMMA5° Sign-in</title></head>"
        "<body>" + "x" * 60000 + "</body></html>"
    )

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
        caplog.at_level(logging.WARNING, logger="custom_components.onekommafive"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = AuthenticationError(
            f"Login failed: {html_body}"
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "wrong"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
    assert "Login failed: 1KOMMA5° Sign-in" in caplog.text
    assert f"[HTML body suppressed, {len(html_body)} bytes]" in caplog.text
    assert "x" * 100 not in caplog.text


async def test_user_flow_cannot_connect_shows_error(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A ``RequestError`` surfaces as ``cannot_connect`` and the SDK's error
    detail lands in the log at WARNING level."""
    from onekommafive.errors import RequestError

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
        caplog.at_level(logging.WARNING, logger="custom_components.onekommafive"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = RequestError(
            "connection refused"
        )

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}
    assert "connection refused" in caplog.text


async def test_user_flow_unexpected_exception_shows_unknown_error(
    hass: HomeAssistant,
) -> None:
    """Any other exception coming out of the library surfaces as ``unknown``.

    Guards against a future SDK error class that the two named branches above
    don't cover: the config flow must still hand the user a form with a
    readable error instead of raising through to HA.
    """
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems.side_effect = RuntimeError("boom")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "unknown"}


# ----------------------------------------------------------------------------
# _summarize_sdk_error — reduce SDK error messages so the WARNING line stays
# readable even when Auth0 hands us a 68 KB <!DOCTYPE html> login page.
# ----------------------------------------------------------------------------


def test_summarize_sdk_error_passes_short_body_through() -> None:
    """Short non-HTML bodies land in the log verbatim."""
    from custom_components.onekommafive.config_flow import _summarize_sdk_error

    err = Exception("Login failed: user does not exist")
    assert _summarize_sdk_error(err) == "Login failed: user does not exist"


def test_summarize_sdk_error_passes_message_without_label() -> None:
    """Messages without the ``'<label>: <body>'`` shape are unchanged."""
    from custom_components.onekommafive.config_flow import _summarize_sdk_error

    err = Exception("timeout")
    assert _summarize_sdk_error(err) == "timeout"


def test_summarize_sdk_error_clips_long_non_html_body() -> None:
    """Non-HTML bodies above 300 chars are clipped with a length tag."""
    from custom_components.onekommafive.config_flow import _summarize_sdk_error

    body = "x" * 1000
    err = Exception(f"Login failed: {body}")
    summary = _summarize_sdk_error(err)
    assert summary.startswith("Login failed: " + "x" * 300 + "…")
    assert "[truncated, 1000 bytes total]" in summary
    assert len(summary) < 400


def test_summarize_sdk_error_extracts_html_title() -> None:
    """HTML bodies are reduced to their ``<title>`` plus a byte count."""
    from custom_components.onekommafive.config_flow import _summarize_sdk_error

    body = (
        "<!DOCTYPE html><html><head><title>1KOMMA5° Sign-in</title></head>"
        "<body>" + "x" * 20000 + "</body></html>"
    )
    err = Exception(f"Login failed: {body}")
    summary = _summarize_sdk_error(err)
    assert summary.startswith("Login failed: 1KOMMA5° Sign-in")
    assert f"[HTML body suppressed, {len(body)} bytes]" in summary
    assert "x" * 100 not in summary


def test_summarize_sdk_error_handles_html_without_title() -> None:
    """HTML bodies without a ``<title>`` fall back to a generic marker."""
    from custom_components.onekommafive.config_flow import _summarize_sdk_error

    body = "<html><body>no title here</body></html>"
    err = Exception(f"Login failed: {body}")
    summary = _summarize_sdk_error(err)
    assert summary.startswith("Login failed: (HTML page)")
    assert f"[HTML body suppressed, {len(body)} bytes]" in summary


# ----------------------------------------------------------------------------
# user flow — success paths
#
# These need the patches active throughout the test, including HA's
# follow-up `async_setup_entry` after the entry is created. Otherwise the
# coordinator's first_refresh runs against a real (un-patched) Systems/
# Client and crashes the test teardown.
# ----------------------------------------------------------------------------


async def test_user_flow_single_system_creates_entry(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A single-system account skips the picker and creates the entry directly."""
    system = mock_system_factory(system_id="sys-1", name="Home")

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )
        await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert result["data"]["system_id"] == "sys-1"
        assert result["data"]["username"] == "u@x.de"
        assert result["title"] == "Home"


async def test_user_flow_multiple_systems_shows_picker(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Accounts with several systems get a picker step before the entry is created."""
    system_a = mock_system_factory(system_id="sys-a", name="Home A")
    system_b = mock_system_factory(system_id="sys-b", name="Home B")

    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_systems = AsyncMock(
            return_value=[system_a, system_b]
        )
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system_b)

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"username": "u@x.de", "password": "pw"},
        )
        assert result["type"] == "form"
        assert result["step_id"] == "system"

        # Pick the second system
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"system_id": "sys-b"},
        )
        await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert result["data"]["system_id"] == "sys-b"
        assert result["title"] == "Home B"
