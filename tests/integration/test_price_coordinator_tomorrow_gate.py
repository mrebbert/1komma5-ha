"""Tier-2 tests for the EPEX-12-UTC gate on the tomorrow-prices fetch.

The ``/charts/market-prices`` endpoint is BigQuery-backed with a shared
100-second JobService.query quota per account. Firing a tomorrow fetch
before EPEX day-ahead publication (12:00 UTC) is guaranteed to return
nothing and only chips at the quota, raising the chance of 403
"Exceeded rate limits" when the hourly refresh lines up with user
activity. The gate skips the second call before noon UTC and keeps
firing both calls afterwards.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, patch

from freezegun import freeze_time
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


async def _setup_and_refresh(hass: HomeAssistant, system) -> MockConfigEntry:
    entry = _entry(hass)
    with (
        patch("onekommafive.systems.Systems") as mock_systems_cls,
        patch("onekommafive.client.Client"),
    ):
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@freeze_time("2026-10-24 11:59:00", tz_offset=0)
async def test_tomorrow_fetch_skipped_before_12_utc(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """At 11:59 UTC, only today's price slot is fetched (EPEX gate active)."""
    system = mock_system_factory(system_id="sys-1")
    await _setup_and_refresh(hass, system)

    # Setup fires exactly one get_prices for today; tomorrow is gated.
    assert system.get_prices.await_count == 1
    today_arg_end: datetime.datetime = system.get_prices.await_args_list[0].args[1]
    assert today_arg_end.day == 24


@freeze_time("2026-10-24 12:01:00", tz_offset=0)
async def test_tomorrow_fetch_runs_after_12_utc(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """From 12:01 UTC the tomorrow call runs — EPEX has published."""
    system = mock_system_factory(system_id="sys-1")
    await _setup_and_refresh(hass, system)

    assert system.get_prices.await_count == 2
    tomorrow_arg_start: datetime.datetime = system.get_prices.await_args_list[1].args[0]
    assert tomorrow_arg_start.day == 25
