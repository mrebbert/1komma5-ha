"""Direct unit-style tests for the setup-time extractors in ``__init__.py``.

``_extract_co2_saved`` and ``_extract_price_guarantee`` are called once at
setup and cached into ``OneKomma5Data``; the sensors that read them stay
tested through their normal integration paths. This module exercises the
extractors themselves so their failure branches (missing endpoint, malformed
payload, unit conversion) don't have to be rediscovered through the sensor
layer.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.onekommafive import (
    PriceGuarantee,
    _extract_co2_saved,
    _extract_price_guarantee,
)


class TestExtractCo2Saved:
    def test_returns_float_when_impact_populated(self) -> None:
        system = MagicMock()
        system.get_impact_overview.return_value = MagicMock(co2_savings_kg=1234.5)
        assert _extract_co2_saved(system) == 1234.5

    def test_returns_none_when_impact_fetch_raises(self) -> None:
        system = MagicMock()
        system.get_impact_overview.side_effect = RuntimeError("api down")
        assert _extract_co2_saved(system) is None

    def test_returns_none_when_field_missing(self) -> None:
        system = MagicMock()
        system.get_impact_overview.return_value = MagicMock(spec=[])
        assert _extract_co2_saved(system) is None

    def test_returns_none_when_field_uncastable(self) -> None:
        system = MagicMock()
        system.get_impact_overview.return_value = MagicMock(co2_savings_kg="not-a-number")
        assert _extract_co2_saved(system) is None


class TestExtractPriceGuarantee:
    def test_returns_none_when_customer_id_missing(self) -> None:
        system = MagicMock()
        assert _extract_price_guarantee(system, None) is None
        system.get_subscriptions.assert_not_called()

    def test_ct_per_kwh_converts_to_eur(self) -> None:
        system = MagicMock()
        sub = MagicMock(
            type="DYNAMIC_PULSE",
            price_guarantee_value=8.03,
            price_guarantee_unit="ct/kWh",
            price_guarantee_version="v2",
        )
        system.get_subscriptions.return_value = MagicMock(subscriptions=[sub])
        result = _extract_price_guarantee(system, "cust-1")
        assert result == PriceGuarantee(value_eur_per_kwh=0.0803, version="v2")

    def test_eur_unit_keeps_value_as_is(self) -> None:
        system = MagicMock()
        sub = MagicMock(
            type="DYNAMIC_PULSE",
            price_guarantee_value=0.09,
            price_guarantee_unit="EUR/kWh",
            price_guarantee_version=None,
        )
        system.get_subscriptions.return_value = MagicMock(subscriptions=[sub])
        result = _extract_price_guarantee(system, "cust-1")
        assert result == PriceGuarantee(value_eur_per_kwh=0.09, version=None)

    def test_ignores_non_dynamic_pulse_subscriptions(self) -> None:
        system = MagicMock()
        sub = MagicMock(
            type="STANDARD",
            price_guarantee_value=5.0,
            price_guarantee_unit="ct/kWh",
            price_guarantee_version="v1",
        )
        system.get_subscriptions.return_value = MagicMock(subscriptions=[sub])
        assert _extract_price_guarantee(system, "cust-1") is None

    def test_returns_none_when_fetch_raises(self) -> None:
        system = MagicMock()
        system.get_subscriptions.side_effect = RuntimeError("api down")
        assert _extract_price_guarantee(system, "cust-1") is None
