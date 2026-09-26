"""Direct unit-style tests for the setup-time extractors in ``__init__.py``.

``_extract_co2_saved`` and ``_extract_price_guarantee`` are called once at
setup and cached into ``OneKomma5Data``; the sensors that read them stay
tested through their normal integration paths. This module exercises the
extractors themselves so their failure branches (missing endpoint, malformed
payload, unit conversion) don't have to be rediscovered through the sensor
layer.

Both extractors are ``async def`` since the SDK v1.0.1 migration, so the SDK
methods are stubbed with ``AsyncMock`` and the tests themselves are async.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from custom_components.onekommafive import (
    PriceGuarantee,
    _extract_co2_saved,
    _extract_price_guarantee,
)


class TestExtractCo2Saved:
    async def test_returns_float_when_impact_populated(self) -> None:
        system = MagicMock()
        system.get_impact_overview = AsyncMock(
            return_value=MagicMock(co2_savings_kg=1234.5)
        )
        assert await _extract_co2_saved(system) == 1234.5

    async def test_returns_none_when_impact_fetch_raises(self) -> None:
        system = MagicMock()
        system.get_impact_overview = AsyncMock(side_effect=RuntimeError("api down"))
        assert await _extract_co2_saved(system) is None

    async def test_returns_none_when_field_missing(self) -> None:
        system = MagicMock()
        system.get_impact_overview = AsyncMock(return_value=MagicMock(spec=[]))
        assert await _extract_co2_saved(system) is None

    async def test_returns_none_when_field_uncastable(self) -> None:
        system = MagicMock()
        system.get_impact_overview = AsyncMock(
            return_value=MagicMock(co2_savings_kg="not-a-number")
        )
        assert await _extract_co2_saved(system) is None


class TestExtractPriceGuarantee:
    async def test_returns_none_when_customer_id_missing(self) -> None:
        system = MagicMock()
        assert await _extract_price_guarantee(system, None) is None
        system.get_price_guarantee.assert_not_called()

    async def test_ct_per_kwh_converts_to_eur(self) -> None:
        system = MagicMock()
        system.get_price_guarantee = AsyncMock(
            return_value=MagicMock(value=8.03, unit="ct/kWh", version="v2")
        )
        result = await _extract_price_guarantee(system, "cust-1")
        assert result == PriceGuarantee(value_eur_per_kwh=0.0803, version="v2")

    async def test_eur_unit_keeps_value_as_is(self) -> None:
        system = MagicMock()
        system.get_price_guarantee = AsyncMock(
            return_value=MagicMock(value=0.09, unit="EUR/kWh", version=None)
        )
        result = await _extract_price_guarantee(system, "cust-1")
        assert result == PriceGuarantee(value_eur_per_kwh=0.09, version=None)

    async def test_returns_none_when_value_missing(self) -> None:
        system = MagicMock()
        system.get_price_guarantee = AsyncMock(
            return_value=MagicMock(value=None, unit="ct/kWh", version="v1")
        )
        assert await _extract_price_guarantee(system, "cust-1") is None

    async def test_returns_none_when_fetch_raises(self) -> None:
        system = MagicMock()
        system.get_price_guarantee = AsyncMock(side_effect=RuntimeError("api down"))
        assert await _extract_price_guarantee(system, "cust-1") is None
