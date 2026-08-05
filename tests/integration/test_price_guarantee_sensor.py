"""Tier-2 tests for the Dynamic-Pulse price-guarantee sensor.

Sensor is instantiated only when the account has a DYNAMIC_PULSE subscription
with a populated ``price_guarantee_value``. Value is normalized to EUR/kWh
regardless of the SDK's returned unit (``ct/kWh`` is divided by 100).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.components.sensor import SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _dp_sub(
    value: float | int | None = 12,
    unit: str | None = "ct/kWh",
    version: str | None = "DE_PRICE_GUARANTEE_V2",
) -> MagicMock:
    """Build a mock DYNAMIC_PULSE Subscription with price-guarantee fields."""
    return MagicMock(
        type="DYNAMIC_PULSE",
        status="ACTIVE",
        price_eur=0,
        price_guarantee_value=value,
        price_guarantee_unit=unit,
        price_guarantee_version=version,
    )


async def _setup(hass: HomeAssistant, system: MagicMock) -> MockConfigEntry:
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


def _sensor_entity_id(hass: HomeAssistant) -> str | None:
    return er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_dynamic_pulse_price_guarantee"
    )


async def test_dp_subscription_with_ct_kwh_converts_to_eur_kwh(
    hass: HomeAssistant, mock_system_factory
) -> None:
    system = mock_system_factory(
        system_id="sys-1",
        subscriptions=[_dp_sub(value=12, unit="ct/kWh")],
    )
    await _setup(hass, system)

    entity_id = _sensor_entity_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    # 12 ct/kWh → 0.12 EUR/kWh
    assert float(state.state) == 0.12
    assert state.attributes["unit_of_measurement"] == "EUR/kWh"
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT
    # device_class deliberately omitted (monetary + measurement is HA-invalid)
    assert "device_class" not in state.attributes
    assert state.attributes["version"] == "DE_PRICE_GUARANTEE_V2"


async def test_dp_subscription_with_eur_kwh_passthrough(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Defensive: if SDK ever returns EUR/kWh directly, no ÷100 applied."""
    system = mock_system_factory(
        system_id="sys-1",
        subscriptions=[_dp_sub(value=0.12, unit="EUR/kWh")],
    )
    await _setup(hass, system)

    entity_id = _sensor_entity_id(hass)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert float(state.state) == 0.12


async def test_no_dp_subscription_no_sensor(hass: HomeAssistant, mock_system_factory) -> None:
    """Account with no DYNAMIC_PULSE contract → sensor not registered."""
    system = mock_system_factory(
        system_id="sys-1",
        subscriptions=[
            MagicMock(type="SMART_METER", status="ACTIVE"),
            MagicMock(type="ENERGY_TRADER", status="ACTIVE"),
        ],
    )
    await _setup(hass, system)
    assert _sensor_entity_id(hass) is None


async def test_dp_subscription_with_none_value_no_sensor(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """DP subscription present but empty guarantee → sensor not registered."""
    system = mock_system_factory(
        system_id="sys-1",
        subscriptions=[_dp_sub(value=None)],
    )
    await _setup(hass, system)
    assert _sensor_entity_id(hass) is None


async def test_missing_customer_id_no_sensor(hass: HomeAssistant, mock_system_factory) -> None:
    """No customer_id on details → subscriptions fetch skipped → no sensor."""
    details = MagicMock(
        customer_id=None,
        emp_type=None,
        status=None,
        dynamic_pulse_compatible=False,
        energy_trader_active=False,
        electricity_contract_active=False,
        has_third_party_smart_meter=None,
        earliest_measurement="2024-01-15",
        created_at=None,
        updated_at=None,
        device_gateways=[],
    )
    system = mock_system_factory(
        system_id="sys-1",
        details=details,
        subscriptions=[_dp_sub()],  # even if returned, extraction skips w/o customer_id
    )
    await _setup(hass, system)
    assert _sensor_entity_id(hass) is None


async def test_subscriptions_endpoint_failure_no_sensor(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Subscriptions endpoint raising is non-fatal — sensor not created."""
    system = mock_system_factory(system_id="sys-1")
    system.get_subscriptions.side_effect = RuntimeError("boom")
    await _setup(hass, system)
    assert _sensor_entity_id(hass) is None
