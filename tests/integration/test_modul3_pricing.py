"""Tier-2 tests for the Modul-3 price pipeline.

Exercises the end-to-end path on a MarketPrices mock that carries a filled
``enwg14a_grid_fee`` dict. The SDK's own ``prices_with_grid_costs_and_vat``
is the vendor-billed all-in number — ``enwg14a_grid_fee`` is a Modul-3
forecast the backend publishes but does not yet bill, so the current-price
sensor must read the SDK dict and the breakdown's ``dynamic_markup`` must
stay on the billed scalar. The grid-fee sensor exposes the preview series
on its own entity, including the 30 h forecast list.
"""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)

# All constants are net (ex-VAT) EUR/kWh unless suffixed _WITH_VAT.
VAT = 0.19
SPOT_HT = 0.30  # net
SPOT_NT = 0.20  # net
FEE_HT = 0.08  # net Modul-3 HT fee
FEE_NT = 0.03  # net Modul-3 NT fee
ENERGY_TAX = 0.0205
PURCHASING = 0.0150
FIXED_TARIFF = 0.0712
FEED_IN_ADJ = 0.0001
# Dynamic-markup scalar is the Modul-1 flat value — overridden per slot on
# Modul-3 sites but still carried in the MarketPrices payload.
DYNAMIC_SCALAR = 0.065

FIXED_NET = ENERGY_TAX + PURCHASING + FIXED_TARIFF + FEED_IN_ADJ


def _at(hour: int) -> str:
    """Produce an ISO-END timestamp on 2026-06-15 at the given UTC hour."""
    return (
        datetime.datetime(2026, 6, 15, hour, 0, tzinfo=datetime.UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _modul3_market_prices() -> MagicMock:
    """MarketPrices mock with a two-slot HT/NT Modul-3 payload.

    Slot ending 10:00 = HT (daytime), slot ending 22:00 = NT (night).
    """
    slot_ht = _at(10)
    slot_nt = _at(22)
    return MagicMock(
        prices={slot_ht: SPOT_HT, slot_nt: SPOT_NT},
        prices_with_vat={
            slot_ht: round(SPOT_HT * (1 + VAT), 7),
            slot_nt: round(SPOT_NT * (1 + VAT), 7),
        },
        prices_with_grid_costs={
            slot_ht: round(SPOT_HT + FIXED_NET + DYNAMIC_SCALAR, 7),
            slot_nt: round(SPOT_NT + FIXED_NET + DYNAMIC_SCALAR, 7),
        },
        prices_with_grid_costs_and_vat={
            slot_ht: round((SPOT_HT + FIXED_NET + DYNAMIC_SCALAR) * (1 + VAT), 7),
            slot_nt: round((SPOT_NT + FIXED_NET + DYNAMIC_SCALAR) * (1 + VAT), 7),
        },
        enwg14a_grid_fee={slot_ht: FEE_HT, slot_nt: FEE_NT},
        enwg14a_grid_fee_with_vat={
            slot_ht: round(FEE_HT * (1 + VAT), 7),
            slot_nt: round(FEE_NT * (1 + VAT), 7),
        },
        vat=VAT,
        grid_cost_energy_tax=ENERGY_TAX,
        grid_cost_purchasing=PURCHASING,
        grid_cost_fixed_tariff=FIXED_TARIFF,
        grid_cost_dynamic_markup=DYNAMIC_SCALAR,
        grid_cost_feed_in_remuneration_adj=FEED_IN_ADJ,
        average_price_all_in=None,
        lowest_price_all_in=None,
        highest_price_all_in=None,
        uses_fallback_grid_costs=False,
    )


async def _setup(hass: HomeAssistant, mock_system_factory) -> None:
    system = mock_system_factory(system_id="sys-1", prices=_modul3_market_prices())
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


def _current_price_attrs(hass: HomeAssistant) -> dict:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_current_electricity_price"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return dict(state.attributes)


def _grid_fee_state(hass: HomeAssistant):
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_enwg14a_grid_fee_current"
    )
    assert entity_id is not None
    return hass.states.get(entity_id)


@freeze_time("2026-06-15T09:30:00+00:00")  # inside the HT slot ending 10:00
async def test_breakdown_dynamic_markup_stays_on_billed_scalar_ht(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Even in the HT preview slot the breakdown reports the billed scalar.

    ``enwg14a_grid_fee`` is a Modul-3 forecast, not yet billed; the vendor
    bills ``grid_cost_dynamic_markup``, so the breakdown must mirror that.
    """
    await _setup(hass, mock_system_factory)
    attrs = _current_price_attrs(hass)
    assert attrs["grid_cost_components"]["dynamic_markup"] == DYNAMIC_SCALAR
    # grid_costs = fixed components + scalar dynamic_markup (NO slot fee).
    assert attrs["grid_costs"] == round(FIXED_NET + DYNAMIC_SCALAR, 6)


@freeze_time("2026-06-15T21:30:00+00:00")  # inside the NT slot ending 22:00
async def test_breakdown_dynamic_markup_stays_on_billed_scalar_nt(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Same invariant at the NT slot — scalar wins over the preview."""
    await _setup(hass, mock_system_factory)
    attrs = _current_price_attrs(hass)
    assert attrs["grid_cost_components"]["dynamic_markup"] == DYNAMIC_SCALAR
    assert attrs["grid_costs"] == round(FIXED_NET + DYNAMIC_SCALAR, 6)


@freeze_time("2026-06-15T09:30:00+00:00")
async def test_grid_fee_current_sensor_exposes_forecast(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Modul-3 site → the live grid-fee sensor publishes a forecast list."""
    await _setup(hass, mock_system_factory)
    state = _grid_fee_state(hass)
    assert state is not None
    # HT slot is still ahead of 09:30 (ends 10:00).
    forecast = state.attributes.get("forecast")
    assert forecast is not None
    assert len(forecast) >= 1
    entry0 = forecast[0]
    assert entry0["end"].startswith("2026-06-15T10:00:00")
    assert entry0["price"] == FEE_HT
    assert entry0["price_with_vat"] == round(FEE_HT * (1 + VAT), 7)


@freeze_time("2026-06-15T09:30:00+00:00")
async def test_current_price_state_reads_sdk_dict_not_preview(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """The visible all-in state follows ``prices_with_grid_costs_and_vat``.

    The SDK dict excludes ``enwg14a_grid_fee`` (preview-only, not billed),
    so the sensor must land on the billed-scalar composition and ignore
    the Modul-3 forecast delta.
    """
    await _setup(hass, mock_system_factory)
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_current_electricity_price"
    )
    state = hass.states.get(entity_id)
    expected_all_in = (SPOT_HT + FIXED_NET + DYNAMIC_SCALAR) * (1 + VAT)
    assert float(state.state) == round(expected_all_in, 7)
