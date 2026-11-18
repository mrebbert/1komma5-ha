"""Tier-2 failure-path tests (H4 hardening).

The happy path is well covered elsewhere; these prove the resilience contract:
a failing or malformed API response degrades gracefully instead of crashing —
the coordinator reports a failed update and dependent entities go unavailable,
and the next interval can recover.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from onekommafive.errors import ApiError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)
from custom_components.onekommafive.coordinator import (
    OneKomma5BaseCoordinator,
    OneKomma5LiveCoordinator,
)


async def test_api_error_marks_update_failed(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(system_id="sys-1")
    system.get_live_overview.side_effect = ApiError("service down")

    coordinator = OneKomma5LiveCoordinator(hass, system)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def test_generic_error_marks_update_failed(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(system_id="sys-1")
    system.get_live_overview.side_effect = RuntimeError("boom")

    coordinator = OneKomma5LiveCoordinator(hass, system)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def _setup(hass: HomeAssistant, system: MagicMock) -> None:
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
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_failing_price_coordinator_leaves_price_sensor_unavailable(
    hass: HomeAssistant, mock_system_factory
) -> None:
    # Price first-refresh is non-fatal (rate-limit resilience): setup must still
    # succeed on the working live coordinator, and the price sensor goes
    # unavailable rather than taking the whole entry down.
    system = mock_system_factory(system_id="sys-1")
    system.get_prices.side_effect = ApiError("prices unavailable")

    await _setup(hass, system)

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_current_electricity_price"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unavailable"


async def test_all_none_live_payload_yields_unknown_not_crash(
    hass: HomeAssistant, mock_system_factory
) -> None:
    # A malformed live overview (every field None) must not crash setup; the
    # affected sensors report `unknown`.
    live = MagicMock(
        pv_power=None,
        battery_power=None,
        battery_soc=None,
        grid_power=None,
        grid_consumption_power=None,
        grid_feed_in_power=None,
        consumption_power=None,
        household_power=None,
        ev_chargers_power=None,
        heat_pumps_power=None,
        acs_power=None,
        self_sufficiency=None,
    )
    system = mock_system_factory(system_id="sys-1", live_overview=live)

    await _setup(hass, system)

    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_pv_power"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unknown"


class _HourlyStub(OneKomma5BaseCoordinator[int]):
    _interval_seconds = 3600
    _retry_interval_seconds = 300

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(hass, MagicMock())
        self.outcomes: list[object] = []

    async def _fetch(self) -> int:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return int(outcome)  # type: ignore[call-overload]


async def test_failed_first_fetch_retries_before_regular_interval(
    hass: HomeAssistant,
) -> None:
    coordinator = _HourlyStub(hass)
    coordinator.outcomes = [ApiError("timeout"), 1, ApiError("later")]

    await coordinator.async_refresh()
    assert coordinator.data is None
    assert coordinator.update_interval == datetime.timedelta(seconds=300)

    await coordinator.async_refresh()
    assert coordinator.data == 1
    assert coordinator.update_interval == datetime.timedelta(seconds=3600)

    # A later failure keeps the stale data and the regular cadence.
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert coordinator.data == 1
    assert coordinator.update_interval == datetime.timedelta(seconds=3600)
