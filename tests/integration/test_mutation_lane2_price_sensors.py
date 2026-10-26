"""Adversarial assertions targeting mutmut survivors in the price-sensor pair.

Lane-2 of the mutation-score push: targets `OneKomma5PriceSensor._price_breakdown`
(21 survivors) and `OneKomma5StablePriceSensor.async_added_to_hass` (15
survivors) as recorded on commit `e388cbf`. Each test is annotated with the
specific mutmut mutation number(s) it kills.
"""

from __future__ import annotations

import datetime
import logging
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)

# ----------------------------------------------------------------------------
# Shared setup
# ----------------------------------------------------------------------------


def _slot() -> str:
    """ISO slot that is one hour in the future (so it counts as current/next)."""
    return (
        (datetime.datetime.now(tz=datetime.UTC) + datetime.timedelta(hours=1))
        .isoformat()
        .replace("+00:00", "Z")
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


def _current_price_attrs(hass: HomeAssistant) -> dict:
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", "onekommafive", "sys-1_current_electricity_price"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    return dict(state.attributes)


# ----------------------------------------------------------------------------
# OneKomma5PriceSensor._price_breakdown
# ----------------------------------------------------------------------------


def _market_prices_full(
    *,
    spot: float = 0.126,
    energy_tax: float = 0.137,
    purchasing: float = 0.025,
    fixed_tariff: float = 0.015,
    dynamic_markup: float = 0.005,
    feed_in_remuneration_adj: float = 0.003,
    vat: float = 0.19,
    uses_fallback: bool = False,
) -> MagicMock:
    """Build a MarketPrices mock with every component populated to a distinct
    non-zero value — gives downstream tests a specific sum to assert on."""
    slot = _slot()
    all_in = round(
        (
            spot
            + energy_tax
            + purchasing
            + fixed_tariff
            + dynamic_markup
            + feed_in_remuneration_adj
        )
        * (1 + vat),
        7,
    )
    spot_with_vat = round(spot * (1 + vat), 7)
    return MagicMock(
        prices={slot: spot},
        prices_with_vat={slot: spot_with_vat},
        prices_with_grid_costs={
            slot: round(
                spot
                + energy_tax
                + purchasing
                + fixed_tariff
                + dynamic_markup
                + feed_in_remuneration_adj,
                7,
            )
        },
        prices_with_grid_costs_and_vat={slot: all_in},
        enwg14a_grid_fee={},
        enwg14a_grid_fee_with_vat={},
        average_price_all_in=all_in,
        lowest_price_all_in=all_in,
        highest_price_all_in=all_in,
        grid_cost_energy_tax=energy_tax,
        grid_cost_purchasing=purchasing,
        grid_cost_fixed_tariff=fixed_tariff,
        grid_cost_dynamic_markup=dynamic_markup,
        grid_cost_feed_in_remuneration_adj=feed_in_remuneration_adj,
        vat=vat,
        uses_fallback_grid_costs=uses_fallback,
    )


def _market_prices_components_absent() -> MagicMock:
    """Build a MarketPrices mock where every grid-cost component attribute is
    explicitly ``None`` — exercises the ``if present else None`` branch."""
    slot = _slot()
    return MagicMock(
        prices={slot: 0.126},
        prices_with_vat={slot: round(0.126 * 1.19, 7)},
        prices_with_grid_costs={slot: 0.126},
        prices_with_grid_costs_and_vat={slot: round(0.126 * 1.19, 7)},
        enwg14a_grid_fee={},
        enwg14a_grid_fee_with_vat={},
        average_price_all_in=0.15,
        lowest_price_all_in=0.15,
        highest_price_all_in=0.15,
        grid_cost_energy_tax=None,
        grid_cost_purchasing=None,
        grid_cost_fixed_tariff=None,
        grid_cost_dynamic_markup=None,
        grid_cost_feed_in_remuneration_adj=None,
        vat=0.19,
        uses_fallback_grid_costs=False,
    )


class TestPriceBreakdownComponentKeys:
    """Dict keys must be the exact lowercase/underscore identifiers (kills
    mut_30/31/39/40/57/58: XXkeyXX / UPPERCASE renames)."""

    async def test_all_component_keys_present_literal(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        system = mock_system_factory(system_id="sys-1", prices=_market_prices_full())
        await _setup(hass, system)
        components = _current_price_attrs(hass)["grid_cost_components"]
        assert set(components) == {
            "energy_tax",
            "purchasing",
            "fixed_tariff",
            "dynamic_markup",
            "feed_in_remuneration_adjustment",
        }


class TestPriceBreakdownComponentValues:
    """getattr(mp, "grid_cost_*", None) → values flow through unchanged
    (kills mut_32/41/59: getattr(None, …))."""

    async def test_each_component_value_round_trips(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        system = mock_system_factory(
            system_id="sys-1",
            prices=_market_prices_full(
                energy_tax=0.111,
                purchasing=0.222,
                fixed_tariff=0.333,
                dynamic_markup=0.044,
                feed_in_remuneration_adj=0.055,
            ),
        )
        await _setup(hass, system)
        components = _current_price_attrs(hass)["grid_cost_components"]
        assert components["energy_tax"] == 0.111
        assert components["purchasing"] == 0.222
        assert components["fixed_tariff"] == 0.333
        assert components["dynamic_markup"] == 0.044
        assert components["feed_in_remuneration_adjustment"] == 0.055


class TestPriceBreakdownGridCostsSum:
    """``grid_costs`` is sum of the five net components, rounded to 6 decimals.

    Kills mut_87 (6→7 round), mut_81 (``present else None`` → ``present or True``
    which would sum an empty list to 0 instead of returning None)."""

    async def test_grid_costs_equals_rounded_sum(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        # Pick values whose sum has a 7th decimal that must round down.
        system = mock_system_factory(
            system_id="sys-1",
            prices=_market_prices_full(
                energy_tax=0.1234561,
                purchasing=0.0,
                fixed_tariff=0.0,
                dynamic_markup=0.0,
                feed_in_remuneration_adj=0.0,
            ),
        )
        await _setup(hass, system)
        attrs = _current_price_attrs(hass)
        assert attrs["grid_costs"] == 0.123456  # not 0.1234561

    async def test_grid_costs_is_none_when_all_components_absent(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        system = mock_system_factory(
            system_id="sys-1", prices=_market_prices_components_absent()
        )
        await _setup(hass, system)
        attrs = _current_price_attrs(hass)
        assert attrs["grid_costs"] is None
        assert attrs["grid_cost_components"] == {}


class TestPriceBreakdownSpotPrice:
    """``spot_price`` is current price, rounded to 6 decimals (kills mut_76)."""

    async def test_spot_price_rounded_to_six_decimals(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        system = mock_system_factory(
            system_id="sys-1", prices=_market_prices_full(spot=0.1234567)
        )
        await _setup(hass, system)
        attrs = _current_price_attrs(hass)
        assert attrs["spot_price"] == 0.123457  # 7th decimal rounds up


# ----------------------------------------------------------------------------
# OneKomma5StablePriceSensor.async_added_to_hass — restore path
# ----------------------------------------------------------------------------


def _market_prices_empty() -> MagicMock:
    """Empty-slot MarketPrices — the stable sensor has nothing live to use so
    the restore path is forced on first boot."""
    return MagicMock(
        prices={},
        prices_with_vat={},
        prices_with_grid_costs={},
        prices_with_grid_costs_and_vat={},
        enwg14a_grid_fee={},
        enwg14a_grid_fee_with_vat={},
        average_price_all_in=None,
        lowest_price_all_in=None,
        highest_price_all_in=None,
        grid_cost_energy_tax=None,
        grid_cost_purchasing=None,
        grid_cost_fixed_tariff=None,
        grid_cost_dynamic_markup=None,
        grid_cost_feed_in_remuneration_adj=None,
        vat=0.0,
        uses_fallback_grid_costs=False,
    )


def _market_prices_live(price: float = 0.30) -> MagicMock:
    slot = _slot()
    return MagicMock(
        prices={slot: price},
        prices_with_vat={slot: price},
        prices_with_grid_costs={slot: price},
        prices_with_grid_costs_and_vat={slot: price},
        enwg14a_grid_fee={},
        enwg14a_grid_fee_with_vat={},
        average_price_all_in=price,
        lowest_price_all_in=price,
        highest_price_all_in=price,
        grid_cost_energy_tax=None,
        grid_cost_purchasing=None,
        grid_cost_fixed_tariff=None,
        grid_cost_dynamic_markup=None,
        grid_cost_feed_in_remuneration_adj=None,
        vat=0.0,
        uses_fallback_grid_costs=False,
    )


def _stable_price_state(hass: HomeAssistant) -> State:
    for state in hass.states.async_all("sensor"):
        if state.entity_id.endswith("_stable_electricity_price"):
            return state
    raise AssertionError("stable price sensor not registered")


class TestStablePriceRestorePath:
    """`async_added_to_hass` restore flow (mut_1/5/6: restore source + target)."""

    async def test_restores_price_from_last_state_when_no_live_data(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        """mut_1 (restored=None), mut_5 (`restored is None`), mut_6 (`stable_price =
        None`): any of these would make the restore a no-op and leave the sensor
        at ``unknown`` even though a valid last state was cached."""
        mock_restore_cache_with_extra_data(
            hass,
            [
                (
                    State("sensor.test_home_stable_electricity_price", "0.1875"),
                    {
                        "native_value": 0.1875,
                        "native_unit_of_measurement": "EUR/kWh",
                    },
                ),
            ],
        )
        system = mock_system_factory(system_id="sys-1", prices=_market_prices_empty())
        await _setup(hass, system)

        state = _stable_price_state(hass)
        assert state.state == "0.1875"

    async def test_live_price_takes_precedence_over_restored(
        self, hass: HomeAssistant, mock_system_factory
    ) -> None:
        """mut_3 (`is None` → `is None or restored is not None`): with the
        mutation, a sensor that already has a live price would still read the
        restored value and overwrite the correct one."""
        mock_restore_cache_with_extra_data(
            hass,
            [
                (
                    State("sensor.test_home_stable_electricity_price", "0.9999"),
                    {
                        "native_value": 0.9999,
                        "native_unit_of_measurement": "EUR/kWh",
                    },
                ),
            ],
        )
        system = mock_system_factory(
            system_id="sys-1", prices=_market_prices_live(0.30)
        )
        await _setup(hass, system)

        state = _stable_price_state(hass)
        # Live price wins, restored value never applied.
        assert state.state == "0.3"

    async def test_unparseable_restored_value_logs_and_keeps_sensor_unknown(
        self, hass: HomeAssistant, mock_system_factory, caplog
    ) -> None:
        """mut_7 (`float(restored.native_value)` → `float(None)` would raise
        TypeError and ALSO reach the except branch — same observable result on
        this test, but the caplog assertion kills mut_14/15/16 (log string
        case changes) by anchoring on the actual rendered text."""
        mock_restore_cache_with_extra_data(
            hass,
            [
                (
                    State("sensor.test_home_stable_electricity_price", "not-a-number"),
                    {
                        "native_value": "not-a-number",
                        "native_unit_of_measurement": "EUR/kWh",
                    },
                ),
            ],
        )
        caplog.set_level(
            logging.DEBUG, logger="custom_components.onekommafive.sensor_entities"
        )
        system = mock_system_factory(system_id="sys-1", prices=_market_prices_empty())
        await _setup(hass, system)

        state = _stable_price_state(hass)
        # No live price, unparseable restored → sensor state unknown.
        assert state.state == "unknown"
        assert any(
            "Could not parse restored stable price" in rec.message
            for rec in caplog.records
        )
