"""Tier-2 tests for ``onekommafive.refresh_now``.

The service forces an immediate refresh of one (or all) coordinators —
useful after a power outage, for debugging, and as a reset hook in
automations. Returns ``{"refreshed": [...], "failed": [...]}`` so callers
can gate on per-coordinator success.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


@pytest.fixture
async def integration(hass: HomeAssistant, mock_system_factory):
    """Set up the integration with the default mock system and return the entry."""
    system = mock_system_factory(system_id="sys-1")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="sys-1",
        data={CONF_USERNAME: "u@x.de", CONF_PASSWORD: "pw", CONF_SYSTEM_ID: "sys-1"},
    )
    entry.add_to_hass(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_default_refreshes_live_coordinator(hass: HomeAssistant, integration) -> None:
    """Omitting the `coordinator` field defaults to refreshing 'live'."""
    live = integration.runtime_data.live_coordinator
    price = integration.runtime_data.price_coordinator
    with (
        patch.object(live, "async_refresh", AsyncMock()) as live_refresh,
        patch.object(price, "async_refresh", AsyncMock()) as price_refresh,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            "refresh_now",
            {},
            blocking=True,
            return_response=True,
        )
    live_refresh.assert_awaited_once()
    price_refresh.assert_not_awaited()
    assert response == {"refreshed": ["live"], "failed": []}


async def test_explicit_coordinator(hass: HomeAssistant, integration) -> None:
    """A specific coordinator name refreshes only that one."""
    weather = integration.runtime_data.weather_coordinator
    live = integration.runtime_data.live_coordinator
    with (
        patch.object(weather, "async_refresh", AsyncMock()) as weather_refresh,
        patch.object(live, "async_refresh", AsyncMock()) as live_refresh,
    ):
        response = await hass.services.async_call(
            DOMAIN,
            "refresh_now",
            {"coordinator": "weather"},
            blocking=True,
            return_response=True,
        )
    weather_refresh.assert_awaited_once()
    live_refresh.assert_not_awaited()
    assert response["refreshed"] == ["weather"]


async def test_all_refreshes_every_coordinator(hass: HomeAssistant, integration) -> None:
    """`coordinator: all` refreshes every coordinator."""
    rd = integration.runtime_data
    all_coords = {
        "live": rd.live_coordinator,
        "price": rd.price_coordinator,
        "optimization": rd.optimization_coordinator,
        "weather": rd.weather_coordinator,
        "system_status": rd.system_status_coordinator,
    }
    mocks = {name: AsyncMock() for name in all_coords}
    for name, coord in all_coords.items():
        coord.async_refresh = mocks[name]
    response = await hass.services.async_call(
        DOMAIN,
        "refresh_now",
        {"coordinator": "all"},
        blocking=True,
        return_response=True,
    )
    for mock in mocks.values():
        mock.assert_awaited_once()
    assert sorted(response["refreshed"]) == sorted(all_coords)
    assert response["failed"] == []


async def test_failed_refresh_is_reported(hass: HomeAssistant, integration) -> None:
    """When a coordinator's refresh leaves `last_update_success=False`, it lands in 'failed'."""
    live = integration.runtime_data.live_coordinator

    async def _fail() -> None:
        live.last_update_success = False

    with patch.object(live, "async_refresh", side_effect=_fail):
        response = await hass.services.async_call(
            DOMAIN,
            "refresh_now",
            {"coordinator": "live"},
            blocking=True,
            return_response=True,
        )
    assert response == {"refreshed": [], "failed": ["live"]}


async def test_no_entries_raises(hass: HomeAssistant) -> None:
    """Calling the service with no entries configured surfaces a user-facing error."""
    # No integration setup — but services live on the bus once any setup has run.
    # Register the service handler manually for this test.
    from custom_components.onekommafive.services import async_setup_services

    async_setup_services(hass)
    with pytest.raises(HomeAssistantError, match="No 1KOMMA5° integration configured"):
        await hass.services.async_call(
            DOMAIN,
            "refresh_now",
            {},
            blocking=True,
            return_response=True,
        )


async def test_unknown_coordinator_value_rejected_by_schema(
    hass: HomeAssistant, integration
) -> None:
    """Schema rejects a coordinator value outside the allowed set."""
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "refresh_now",
            {"coordinator": "nonsense"},
            blocking=True,
            return_response=True,
        )
