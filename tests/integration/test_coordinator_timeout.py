"""Tier-2 test for the base coordinator's fetch timeout (H2 hardening).

All SDK calls are synchronous HTTP run in the executor. DataUpdateCoordinator
imposes no timeout of its own, so a hung request would pin the coordinator
indefinitely. The base wraps the executor job in `asyncio.timeout(...)` and
surfaces a timeout as a normal failed update (last_update_success = False),
so the entity goes unavailable and the next interval retries.
"""

from __future__ import annotations

import time

from homeassistant.core import HomeAssistant

from custom_components.onekommafive.coordinator import OneKomma5LiveCoordinator


async def test_fetch_timeout_marks_update_failed(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(system_id="sys-1")
    # Make the first blocking SDK call outlast the (shrunk) timeout. It runs in
    # the executor, so the sleep does not block the event loop.
    system.get_live_overview.side_effect = lambda: time.sleep(0.3)

    coordinator = OneKomma5LiveCoordinator(hass, system)
    coordinator._fetch_timeout_seconds = 0.05

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False


async def test_normal_fetch_succeeds_within_timeout(
    hass: HomeAssistant, mock_system_factory
) -> None:
    # Regression guard: the timeout wrapper must not break the happy path.
    system = mock_system_factory(system_id="sys-1")

    coordinator = OneKomma5LiveCoordinator(hass, system)
    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data is not None
