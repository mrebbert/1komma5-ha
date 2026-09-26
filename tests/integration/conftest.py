"""Pytest configuration for Tier-2 integration tests.

These tests run against a real Home Assistant instance via
``pytest-homeassistant-custom-component`` and exercise the integration's
config flow, coordinators, sensors and services end-to-end with a mocked
``onekommafive`` library.

Install the heavier dependency group first::

    .venv/bin/pip install -e ".[test-integration]"

Then run only the integration tests::

    .venv/bin/pytest tests/integration -v
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Auto-enable HA's discovery of `custom_components/` for every test.

    Without this fixture HA refuses to load the integration during tests
    (it only loads built-in components by default).
    """
    yield


@pytest.fixture
def mock_system_factory():
    """Build mock ``onekommafive.system.System`` objects.

    Every SDK method that is async in v1.0.1 is wired as an ``AsyncMock`` so
    ``await system.get_live_overview()`` yields the payload the test supplies.
    ``system.id()`` stays sync (per SDK v1.0.1). Data-container mocks (assets,
    wallboxes, EVs, market prices, ...) remain plain ``MagicMock`` because the
    integration reads them as attributes, not as awaitables.
    """

    def _factory(
        *,
        system_id: str = "system-uuid-1",
        name: str = "Test Home",
        live_overview: MagicMock | None = None,
        ev_chargers: list | None = None,
        wallboxes: list | None = None,
        device_gateways: list | None = None,
        ems_settings: MagicMock | None = None,
        prices: MagicMock | None = None,
        optimizations: MagicMock | None = None,
        weather: MagicMock | None = None,
        energy: MagicMock | None = None,
        details: MagicMock | None = None,
        site_status: str | None = "CONNECTED",
        assets: list | None = None,
        active_features: list[str] | None = None,
        notifications: list | None = None,
        subscriptions: list | None = None,
        heartbeat_prices: MagicMock | None = None,
        impact: MagicMock | None = None,
        price_guarantee: MagicMock | None = None,
    ) -> MagicMock:
        system = MagicMock()
        # ``System.id()`` is sync in the SDK; keep MagicMock semantics.
        system.id.return_value = system_id

        info = MagicMock()
        info.name = name
        info.address_city = None
        system.info = AsyncMock(return_value=info)

        # Live overview defaults to all-zero so sensor coercion doesn't trip.
        if live_overview is None:
            live_overview = MagicMock(
                pv_power=0.0,
                battery_power=0.0,
                battery_soc=0,
                grid_power=0.0,
                grid_consumption_power=0.0,
                grid_feed_in_power=0.0,
                consumption_power=0.0,
                household_power=0.0,
                ev_chargers_power=0.0,
                heat_pumps_power=0.0,
                acs_power=0.0,
                self_sufficiency=0.0,
            )
        system.get_live_overview = AsyncMock(return_value=live_overview)

        system.get_ev_chargers = AsyncMock(return_value=ev_chargers or [])
        system.get_wallboxes = AsyncMock(return_value=wallboxes or [])
        system.get_device_gateways = AsyncMock(return_value=device_gateways or [])

        if ems_settings is None:
            ems_settings = MagicMock(auto_mode=True)
        system.get_ems_settings = AsyncMock(return_value=ems_settings)
        system.set_ems_mode = AsyncMock(return_value=None)

        if prices is None:
            prices = MagicMock(
                prices_with_grid_costs_and_vat={},
                prices_with_grid_costs={},
                average_price_all_in=None,
                lowest_price_all_in=None,
                highest_price_all_in=None,
            )
        system.get_prices = AsyncMock(return_value=prices)

        if optimizations is None:
            optimizations = MagicMock(events=[])
        system.get_optimizations = AsyncMock(return_value=optimizations)

        if weather is None:
            weather = MagicMock(
                today=MagicMock(
                    temperature_celsius=None,
                    sunshine_minutes=None,
                    weather_symbol_id=None,
                ),
                tomorrow=MagicMock(
                    temperature_celsius=None,
                    sunshine_minutes=None,
                    weather_symbol_id=None,
                ),
                forecasts=[],
            )
        system.get_weather = AsyncMock(return_value=weather)

        if energy is None:
            energy = MagicMock(
                savings_eur=0.0,
                self_sufficiency=0.0,
                updated_at=None,
            )
        system.get_energy_today = AsyncMock(return_value=energy)

        if details is None:
            details = MagicMock(
                customer_id="cust-uuid-1",
                emp_type="GRIDX",
                status="ACTIVE",
                dynamic_pulse_compatible=True,
                energy_trader_active=True,
                electricity_contract_active=True,
                has_third_party_smart_meter=None,
                earliest_measurement="2024-01-15",
                created_at="2024-01-10T00:00:00Z",
                updated_at="2026-05-01T00:00:00Z",
                device_gateways=[],
            )
        system.get_details = AsyncMock(return_value=details)

        # Default to a fully-equipped install (all four asset types present)
        # so entities aren't disabled-by-default. Tests that exercise the
        # missing-asset path pass an explicit `assets=` (incl. empty list).
        if assets is None:
            assets = [
                MagicMock(
                    type=t,
                    connection_status="CONNECTED",
                    manufacturer=None,
                    model=None,
                    firmware=None,
                    serial_number=None,
                    network_address=None,
                    heat_pump_meter_type=None,
                )
                for t in ("HYBRID", "HEAT_PUMP", "METER", "EV_CHARGER")
            ]
        site = MagicMock(status=site_status, assets=assets)
        system.get_status_and_assets = AsyncMock(return_value=site)

        system.get_active_features = AsyncMock(return_value=list(active_features or []))

        # Notifications bridge (v0.1.52) — SDK returns NotificationsList with
        # a `.notifications: list[Notification]` attribute. Empty by default so
        # tests that don't care about notifications don't need to stub anything.
        system.get_notifications = AsyncMock(
            return_value=MagicMock(notifications=list(notifications or []))
        )

        # Subscriptions inventory still stubbed for backward-compat with tests
        # that address it directly; the integration no longer consumes it.
        system.get_subscriptions = AsyncMock(
            return_value=MagicMock(
                subscriptions=list(subscriptions or []),
                total_items=len(subscriptions or []),
            )
        )

        # Price-guarantee endpoint (SDK v1.0.1 first-class method). Default to
        # ``None`` value/unit/version so ``_extract_price_guarantee`` returns
        # ``None`` unless a test explicitly stubs the model.
        if price_guarantee is None:
            price_guarantee = MagicMock(value=None, unit=None, version=None)
        system.get_price_guarantee = AsyncMock(return_value=price_guarantee)

        # HeartbeatPrices (v0.1.53) — SDK returns HeartbeatPrices with 5 named
        # window attributes; default to all-None so absent windows return
        # gracefully. Tests that need populated data pass an explicit stub.
        if heartbeat_prices is None:
            heartbeat_prices = MagicMock(
                day=None, week=None, month=None, half_year=None, year=None
            )
        system.get_heartbeat_prices = AsyncMock(return_value=heartbeat_prices)

        # ImpactOverview (v0.1.53) — SDK exposes `co2_savings_kg: float | None`.
        # Default to a stub whose value is None so the attribute is absent.
        if impact is None:
            impact = MagicMock(co2_savings_kg=None)
        system.get_impact_overview = AsyncMock(return_value=impact)

        return system

    return _factory


@pytest.fixture
def setup_integration(
    hass: HomeAssistant,
) -> Callable[..., Awaitable[MockConfigEntry]]:
    """Wire a mocked System object into a MockConfigEntry and boot the integration.

    Consolidates the 29 duplicated ``_setup`` / ``_setup_entry`` helpers that
    each test module used to carry. Callers pass the system mock they built
    via ``mock_system_factory`` and get back a fully-set-up ``MockConfigEntry``
    for further assertions or state reads.
    """

    async def _setup(
        system: MagicMock,
        *,
        system_id: str = "sys-1",
        username: str = "u@x.de",
        password: str = "pw",
        unique_id: str | None = None,
    ) -> MockConfigEntry:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=unique_id or system_id,
            data={
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
                CONF_SYSTEM_ID: system_id,
            },
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
        return entry

    return _setup
