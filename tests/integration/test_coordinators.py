"""Tier-2 tests for the data update coordinators.

Focus on the production bugs we shipped patches for:
- EMS DeviceGateway missing → live data still works, switch unavailable
- Price coordinator first refresh non-fatal on API rate-limit
- Optimization coordinator first refresh non-fatal
"""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _entry(hass: HomeAssistant, system_id: str = "sys-1") -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=system_id,
        data={
            CONF_USERNAME: "u@x.de",
            CONF_PASSWORD: "pw",
            CONF_SYSTEM_ID: system_id,
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_setup_succeeds_when_ems_gateway_missing(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """``get_ems_settings()`` raising must not abort live data setup."""
    from onekommafive.errors import ApiError

    system = mock_system_factory(system_id="sys-1")
    system.get_ems_settings.side_effect = ApiError("DeviceGateway not found")

    entry = _entry(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]

        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

    # Live coordinator finished with success, ems_settings is None
    live = entry.runtime_data.live_coordinator
    assert live.last_update_success is True
    assert live.data is not None
    assert live.data.ems_settings is None


async def test_setup_succeeds_when_price_first_refresh_rate_limited(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """A rate-limit on the first price fetch must not block setup."""
    from onekommafive.errors import ApiError

    system = mock_system_factory(system_id="sys-1")
    system.get_prices.side_effect = ApiError("Exceeded rate limits")

    entry = _entry(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]

        # Setup must still return True even though price fetch failed
        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

    # Live coordinator is fine; price coordinator is empty (failed first refresh)
    assert entry.runtime_data.live_coordinator.last_update_success is True
    assert entry.runtime_data.price_coordinator.last_update_success is False


async def test_setup_succeeds_when_optimization_first_refresh_fails(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """An ApiError on the first optimization fetch must not block setup."""
    from onekommafive.errors import ApiError

    system = mock_system_factory(system_id="sys-1")
    system.get_optimizations.side_effect = ApiError("transient")

    entry = _entry(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system.return_value = system
        mock_systems_cls.return_value.get_systems.return_value = [system]

        assert await hass.config_entries.async_setup(entry.entry_id) is True
        await hass.async_block_till_done()

    assert entry.runtime_data.live_coordinator.last_update_success is True
    assert entry.runtime_data.optimization_coordinator.last_update_success is False
