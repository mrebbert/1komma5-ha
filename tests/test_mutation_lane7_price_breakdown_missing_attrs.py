"""Adversarial assertions targeting `_price_breakdown` getattr-default survivors.

Lane-7 of the mutation-score push: targets the 9 remaining mutmut survivors
in `sensor_entities.OneKomma5PriceSensor._price_breakdown` on commit after
Lane-6, all of them "getattr default-value dropped" mutations
(`getattr(obj, "x", None)` → `getattr(obj, "x", )`).

The strategy here is to call the pure method directly (it never touches
`self`) with `SimpleNamespace` stubs where specific attributes are *missing*
— MagicMock would hand back a mock on every attribute lookup and so the
dropped-default mutations never trip. With a stub that genuinely lacks the
attribute, the original returns the default `None`; the mutation raises
`AttributeError`.
"""

from __future__ import annotations

from types import SimpleNamespace

from custom_components.onekommafive.sensor_entities import OneKomma5PriceSensor


def _price_breakdown(data) -> dict:
    """Pass-through to the plain function; `self` is unused by the method."""
    return OneKomma5PriceSensor._price_breakdown(None, data)


def _mp(**attrs) -> SimpleNamespace:
    """MarketPrices-like stub carrying only the attributes supplied."""
    return SimpleNamespace(**attrs)


def _data(**attrs) -> SimpleNamespace:
    return SimpleNamespace(**attrs)


class TestMarketPricesMissingAttribute:
    """`getattr(data, "market_prices", None)` default — mut_6."""

    def test_data_without_market_prices_returns_empty_dict(self) -> None:
        """Original returns {} via the ``if mp is None`` guard; the mutation
        drops the default and raises AttributeError on the missing attr."""
        data = SimpleNamespace()  # no `.market_prices`
        assert _price_breakdown(data) == {}


class TestMpWithoutPrices:
    """`getattr(mp, "prices", None) or {}` — mut_17."""

    def test_mp_without_prices_still_produces_breakdown(self) -> None:
        """Without `.prices`, original flows to `None or {} = {}` and spot
        becomes None via empty-dict current-price lookup; mutation raises."""
        data = _data(market_prices=_mp(vat=0.19))
        result = _price_breakdown(data)
        # spot_price is None because there's no current slot in {} forecast
        assert result["spot_price"] is None
        assert result["vat_rate"] == 0.19


class TestMpWithoutComponentAttributes:
    """The five `getattr(mp, "grid_cost_*", None)` components —
    mut_27 (energy_tax), mut_36 (purchasing), mut_45 (fixed_tariff),
    mut_54 (dynamic_markup), mut_63 (feed_in_remuneration_adj).

    Each mutation drops the per-attribute default; a MP stub that lacks the
    attribute causes AttributeError under the mutation and None in the
    original. The resulting ``components`` dict drops the missing keys."""

    def test_mp_without_energy_tax(self) -> None:
        data = _data(market_prices=_mp(prices={}, vat=0.19))
        result = _price_breakdown(data)
        assert "energy_tax" not in result["grid_cost_components"]

    def test_mp_without_purchasing(self) -> None:
        data = _data(market_prices=_mp(prices={}, vat=0.19))
        result = _price_breakdown(data)
        assert "purchasing" not in result["grid_cost_components"]

    def test_mp_without_fixed_tariff(self) -> None:
        data = _data(market_prices=_mp(prices={}, vat=0.19))
        result = _price_breakdown(data)
        assert "fixed_tariff" not in result["grid_cost_components"]

    def test_mp_without_dynamic_markup(self) -> None:
        data = _data(market_prices=_mp(prices={}, vat=0.19))
        result = _price_breakdown(data)
        assert "dynamic_markup" not in result["grid_cost_components"]

    def test_mp_without_feed_in_remuneration_adj(self) -> None:
        data = _data(market_prices=_mp(prices={}, vat=0.19))
        result = _price_breakdown(data)
        assert "feed_in_remuneration_adjustment" not in result["grid_cost_components"]


class TestMpWithoutVatAndFallback:
    """`getattr(mp, "vat", None)` (mut_96) and
    `getattr(mp, "uses_fallback_grid_costs", None)` (mut_105)."""

    def test_mp_without_vat_returns_none_vat_rate(self) -> None:
        data = _data(market_prices=_mp(prices={}))
        result = _price_breakdown(data)
        assert result["vat_rate"] is None

    def test_mp_without_uses_fallback_returns_none(self) -> None:
        data = _data(market_prices=_mp(prices={}))
        result = _price_breakdown(data)
        assert result["uses_fallback_grid_costs"] is None


class TestFullyPopulatedBreakdown:
    """Positive case: every attribute present. Pins the happy-path shape so
    the unbound-call helper above is proven to call the method."""

    def test_full_breakdown_round_trips(self) -> None:
        data = _data(
            market_prices=_mp(
                prices={},
                grid_cost_energy_tax=0.1,
                grid_cost_purchasing=0.05,
                grid_cost_fixed_tariff=0.02,
                grid_cost_dynamic_markup=0.03,
                grid_cost_feed_in_remuneration_adj=0.01,
                vat=0.19,
                uses_fallback_grid_costs=False,
            )
        )
        result = _price_breakdown(data)
        assert result["vat_rate"] == 0.19
        assert result["uses_fallback_grid_costs"] is False
        # 0.1 + 0.05 + 0.02 + 0.03 + 0.01 = 0.21
        assert result["grid_costs"] == 0.21
        assert set(result["grid_cost_components"]) == {
            "energy_tax",
            "purchasing",
            "fixed_tariff",
            "dynamic_markup",
            "feed_in_remuneration_adjustment",
        }
