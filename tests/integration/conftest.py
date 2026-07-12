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

from collections.abc import Generator
from unittest.mock import MagicMock

import pytest


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

    Returns a factory so each test can shape the system the way it needs:
    the system id, the live overview, EV chargers, EMS, prices and
    optimization events are all individually overridable.
    """

    def _factory(
        *,
        system_id: str = "system-uuid-1",
        name: str = "Test Home",
        live_overview: MagicMock | None = None,
        ev_chargers: list | None = None,
        ems_settings: MagicMock | None = None,
        prices: MagicMock | None = None,
        optimizations: MagicMock | None = None,
        weather: MagicMock | None = None,
        energy: MagicMock | None = None,
        details: MagicMock | None = None,
        site_status: str | None = "CONNECTED",
        assets: list | None = None,
        active_features: list[str] | None = None,
    ) -> MagicMock:
        system = MagicMock()
        system.id.return_value = system_id

        info = MagicMock()
        info.name = name
        info.address_city = None
        system.info.return_value = info

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
        system.get_live_overview.return_value = live_overview

        system.get_ev_chargers.return_value = ev_chargers or []

        if ems_settings is None:
            ems_settings = MagicMock(auto_mode=True)
        system.get_ems_settings.return_value = ems_settings

        if prices is None:
            prices = MagicMock(
                prices_with_grid_costs_and_vat={},
                prices_with_grid_costs={},
                average_price_all_in=None,
                lowest_price_all_in=None,
                highest_price_all_in=None,
            )
        system.get_prices.return_value = prices

        if optimizations is None:
            optimizations = MagicMock(events=[])
        system.get_optimizations.return_value = optimizations

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
        system.get_weather.return_value = weather

        if energy is None:
            energy = MagicMock(
                savings_eur=0.0,
                self_sufficiency=0.0,
                updated_at=None,
            )
        system.get_energy_today.return_value = energy

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
        system.get_details.return_value = details

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
        system.get_status_and_assets.return_value = site

        system.get_active_features.return_value = list(active_features or [])

        return system

    return _factory
