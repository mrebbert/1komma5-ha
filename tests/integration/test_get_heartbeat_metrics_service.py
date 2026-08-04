"""Tier-2 tests for the ``onekommafive.get_heartbeat_metrics`` service.

On-demand fetch — `system.get_heartbeat_prices()` runs in the executor, the
requested window is walked, all populated fields land in the response dict
alongside a `window` label and `available` flag.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _mock_window(**fields: object) -> MagicMock:
    """Build a mock HeartbeatPriceWindow with the given attributes plus a
    default set of the audited fields so callable-detection tests work.
    """
    defaults = {
        "pv_produced_kwh": 331.24,
        "grid_feed_in_kwh": 378.75,
        "grid_feed_in_compensation_eur": 30.41,
        "grid_consumed_kwh": 152.3,
        "grid_consumption_cost_eur": 45.20,
        "total_consumption_kwh": 195.28,
        "vat": 0.19,
    }
    return MagicMock(spec_set=list(defaults) + list(fields), **{**defaults, **fields})


@pytest.fixture
async def integration(hass: HomeAssistant, mock_system_factory):
    """Set up the integration with a heartbeat-prices mock covering all 5 windows."""
    hb = MagicMock(
        day=_mock_window(pv_produced_kwh=34.93),
        week=_mock_window(pv_produced_kwh=241.88),
        month=_mock_window(pv_produced_kwh=990.26),
        half_year=_mock_window(pv_produced_kwh=5432.10),
        year=_mock_window(pv_produced_kwh=10864.50),
    )
    system = mock_system_factory(system_id="sys-1", heartbeat_prices=hb)
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


async def test_month_window_returns_populated_dict(hass: HomeAssistant, integration) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "get_heartbeat_metrics",
        {"window": "month"},
        blocking=True,
        return_response=True,
    )
    assert response["window"] == "month"
    assert response["available"] is True
    assert response["pv_produced_kwh"] == 990.26
    assert response["grid_feed_in_compensation_eur"] == 30.41
    assert response["vat"] == 0.19


async def test_each_window_dispatches_correctly(hass: HomeAssistant, integration) -> None:
    """All 5 windows return their own PV value (proving getattr dispatch works)."""
    expected = {
        "day": 34.93,
        "week": 241.88,
        "month": 990.26,
        "half_year": 5432.10,
        "year": 10864.50,
    }
    for window, pv in expected.items():
        response = await hass.services.async_call(
            DOMAIN,
            "get_heartbeat_metrics",
            {"window": window},
            blocking=True,
            return_response=True,
        )
        assert response["available"] is True, window
        assert response["window"] == window
        assert response["pv_produced_kwh"] == pv, window


async def test_invalid_window_rejected_by_schema(hass: HomeAssistant, integration) -> None:
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "get_heartbeat_metrics",
            {"window": "decade"},
            blocking=True,
            return_response=True,
        )


async def test_absent_window_returns_available_false(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """SDK returning None for a window → `{available: false, window: ...}`."""
    hb = MagicMock(day=None, week=None, month=None, half_year=None, year=None)
    system = mock_system_factory(system_id="sys-1", heartbeat_prices=hb)
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

    response = await hass.services.async_call(
        DOMAIN,
        "get_heartbeat_metrics",
        {"window": "month"},
        blocking=True,
        return_response=True,
    )
    assert response == {"window": "month", "available": False}
