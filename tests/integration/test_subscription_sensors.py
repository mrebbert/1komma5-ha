"""Tier-2 tests for the three contract-overview sensors added in v0.1.68.

Covers:
- Happy-path for ``active_subscriptions``, ``subscription_eligibility`` and
  ``emp_backend``.
- Edge-case: failed setup fetch skips the first two sensors; ``emp_backend``
  always registers and falls back to ``UNKNOWN``.
- PII guardrail: subscription raw-blob fields never leak into the entity's
  attribute dict (``customer_id``, ``site_id``, ``electricity_contract_number``,
  ``market_location_id``, ``terms_and_conditions_url``, ``raw``).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
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
        mock_systems_cls.return_value.get_system = AsyncMock(return_value=system)
        mock_systems_cls.return_value.get_systems = AsyncMock(return_value=[system])
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str) -> object:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "onekommafive", f"sys-1_{key}")
    assert entity_id is not None, f"{key} sensor not registered"
    state = hass.states.get(entity_id)
    assert state is not None
    return state


def _entity_category(hass: HomeAssistant, key: str) -> EntityCategory | None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", "onekommafive", f"sys-1_{key}")
    assert entity_id is not None
    entry = registry.async_get(entity_id)
    assert entry is not None
    return entry.entity_category


def _subscription(
    *, status: str = "ACTIVE", type_: str = "DYNAMIC_PULSE", **overrides: object
) -> MagicMock:
    base = {
        "id": "sub-uuid-1",
        "type": type_,
        "status": status,
        "site_id": "site-uuid",
        "customer_id": "cust-uuid",
        "price_eur": 0.0,
        "currency": "EURO",
        "billing_frequency": "MONTHLY",
        "start_date": "2026-01-01",
        "end_date": None,
        "signed_date": "2025-12-01",
        "created_at": None,
        "updated_at": None,
        "notice_period_interval": "MONTHS",
        "notice_period_number": 1,
        "renewal": "AUTOMATIC",
        "payment_method": "DIRECT_DEBIT",
        "country_code": "DE",
        "electricity_contract_number": "EC-123456",
        "market_location_id": "MALO-987654",
        "price_guarantee_value": None,
        "price_guarantee_unit": None,
        "price_guarantee_version": None,
        "terms_and_conditions_url": "https://example/terms",
        "raw": {"paymentIban": "DE89...", "statusHistory": []},
    }
    base.update(overrides)
    return MagicMock(**base)


def _eligibility(type_: str, eligible: bool, reason: str | None = None) -> MagicMock:
    return MagicMock(type=type_, eligible=eligible, reason=reason)


async def test_active_subscriptions_state_and_attributes(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """State counts ACTIVE contracts; attribute lists all contracts PII-redacted."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-1", emp_type="1K5"),
        subscriptions=[
            _subscription(status="ACTIVE", type_="DYNAMIC_PULSE"),
            _subscription(status="ACTIVE", type_="HEARTBEAT", price_eur=0.0),
            _subscription(status="CANCELLED", type_="ENERGY_TRADER"),
        ],
    )
    await _setup(hass, system)
    state = _state(hass, "active_subscriptions")

    assert state.state == "2"
    contracts = state.attributes["contracts"]
    assert len(contracts) == 3
    assert {c["type"] for c in contracts} == {
        "DYNAMIC_PULSE",
        "HEARTBEAT",
        "ENERGY_TRADER",
    }
    assert _entity_category(hass, "active_subscriptions") == EntityCategory.DIAGNOSTIC


async def test_subscription_eligibility_state_and_attributes(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """State counts eligible add-ons; attribute splits eligible/ineligible."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-1", emp_type="1K5"),
        subscription_eligibility=[
            _eligibility("PV_SERVICE", True),
            _eligibility(
                "MAINTENANCE_HEAT_PUMP",
                False,
                reason="Heat pump not on the service list",
            ),
        ],
    )
    await _setup(hass, system)
    state = _state(hass, "subscription_eligibility")

    assert state.state == "1"
    assert state.attributes["eligible"] == ["PV_SERVICE"]
    assert state.attributes["ineligible"] == [
        {"type": "MAINTENANCE_HEAT_PUMP", "reason": "Heat pump not on the service list"}
    ]
    assert (
        _entity_category(hass, "subscription_eligibility") == EntityCategory.DIAGNOSTIC
    )


async def test_emp_backend_enum_state(hass: HomeAssistant, mock_system_factory) -> None:
    """ENUM sensor exposes the account's EMP backend; options list is pinned."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-1", emp_type="1K5"),
    )
    await _setup(hass, system)
    state = _state(hass, "emp_backend")

    assert state.state == "1K5"
    assert state.attributes["device_class"] == SensorDeviceClass.ENUM.value
    assert set(state.attributes["options"]) == {"GRIDX", "1K5", "UNKNOWN"}
    assert _entity_category(hass, "emp_backend") == EntityCategory.DIAGNOSTIC


async def test_emp_backend_falls_back_to_unknown(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Missing/unexpected emp_type falls back to the UNKNOWN enum member."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-1", emp_type=None),
    )
    await _setup(hass, system)

    assert _state(hass, "emp_backend").state == "UNKNOWN"


async def test_failed_subscriptions_fetch_skips_sensor(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When ``get_subscriptions`` raises, the active_subscriptions sensor is skipped."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-1", emp_type="GRIDX"),
    )
    system.get_subscriptions.side_effect = RuntimeError("boom")
    await _setup(hass, system)

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", "onekommafive", "sys-1_active_subscriptions"
        )
        is None
    )
    # emp_backend still registers.
    assert _state(hass, "emp_backend").state == "GRIDX"


async def test_failed_eligibility_fetch_skips_sensor(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """When eligibility fetch fails, the eligibility sensor is skipped; others not."""
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-1", emp_type="1K5"),
    )
    system.get_subscription_eligibility.side_effect = RuntimeError("boom")
    await _setup(hass, system)

    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", "onekommafive", "sys-1_subscription_eligibility"
        )
        is None
    )


async def test_active_subscriptions_attribute_dict_excludes_pii(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """PII guardrail: raw blob and identity fields never land in the attributes.

    Mirrors ``test_diagnostics_system_block_excludes_pii_and_secrets`` for the
    system-level diagnostic dump — same philosophy, enforced per entity.
    """
    system = mock_system_factory(
        system_id="sys-1",
        details=MagicMock(customer_id="cust-leak", emp_type="1K5"),
        subscriptions=[
            _subscription(
                status="ACTIVE",
                type_="DYNAMIC_PULSE",
                customer_id="cust-leak",
                site_id="site-leak",
                electricity_contract_number="EC-LEAK-42",
                market_location_id="MALO-LEAK-99",
                terms_and_conditions_url="https://leak/terms",
                raw={"paymentIban": "DE89-LEAK-IBAN", "metadata": {"leak": "yes"}},
            )
        ],
    )
    await _setup(hass, system)
    state = _state(hass, "active_subscriptions")

    serialised = json.dumps(state.attributes["contracts"])
    for leak in (
        "cust-leak",
        "site-leak",
        "EC-LEAK-42",
        "MALO-LEAK-99",
        "https://leak/terms",
        "DE89-LEAK-IBAN",
        "metadata",
    ):
        assert leak not in serialised, f"PII leaked into contracts attr: {leak!r}"
