"""Tier-2 tests for per-asset sub-devices (via_device).

The integration splits the system device into one parent + per-asset
sub-devices (inverter / heat_pump / meter / wallbox). These tests verify:

1. With all four asset types in the SDK payload, the device_registry holds
   one parent + four sub-devices, each linked via ``via_device``.
2. Each sub-device's ``manufacturer`` / ``model`` / ``sw_version`` come from
   the matching ``Asset`` payload — PII-safe fields only.
3. Specific entities (e.g. PV power, heat pump power, wallbox connectivity)
   sit on their expected sub-device.
4. Entity ``unique_id`` values are unchanged (statistics / automation
   stability invariant — see backlog discussion).
5. With a partial asset list, only the present sub-devices are created;
   entities for missing assets fall back to the system parent.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.onekommafive.const import (
    CONF_PASSWORD,
    CONF_SYSTEM_ID,
    CONF_USERNAME,
    DOMAIN,
)


def _asset(
    asset_type: str,
    *,
    manufacturer: str,
    model: str,
    firmware: str | None,
    connection_status: str = "CONNECTED",
) -> MagicMock:
    return MagicMock(
        type=asset_type,
        connection_status=connection_status,
        manufacturer=manufacturer,
        model=model,
        firmware=firmware,
    )


def _all_assets() -> list[MagicMock]:
    return [
        _asset("HYBRID", manufacturer="Sungrow", model="SH6.0RT-V112", firmware="SAPPHIRE-001"),
        _asset("HEAT_PUMP", manufacturer="Stiebel Eltron", model="WPMsystem", firmware=None),
        _asset("METER", manufacturer="Chint", model="DTSU666", firmware=None),
        _asset("EV_CHARGER", manufacturer="go-e", model="HOMEfix 11kW", firmware="60.5"),
    ]


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


async def test_full_asset_set_yields_parent_plus_four_sub_devices(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """All four sub-devices present, each linked to the parent via via_device."""
    system = mock_system_factory(system_id="sys-1", assets=_all_assets())
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    by_identifier = {next(iter(d.identifiers))[1]: d for d in devices}

    # Parent + four asset sub-devices (EV vehicle absent since ev_chargers=[]).
    assert "sys-1" in by_identifier
    assert "sys-1_inverter" in by_identifier
    assert "sys-1_heat_pump" in by_identifier
    assert "sys-1_meter" in by_identifier
    assert "sys-1_wallbox" in by_identifier

    parent = by_identifier["sys-1"]
    for key in ("inverter", "heat_pump", "meter", "wallbox"):
        sub = by_identifier[f"sys-1_{key}"]
        assert sub.via_device_id == parent.id, f"{key} sub-device not parented under system"


async def test_sub_devices_carry_manufacturer_model_firmware(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """manufacturer / model / sw_version come straight from the Asset payload."""
    system = mock_system_factory(system_id="sys-1", assets=_all_assets())
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)

    devices = {
        next(iter(d.identifiers))[1]: d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }

    inv = devices["sys-1_inverter"]
    assert inv.manufacturer == "Sungrow"
    assert inv.model == "SH6.0RT-V112"
    assert inv.sw_version == "SAPPHIRE-001"

    hp = devices["sys-1_heat_pump"]
    assert hp.manufacturer == "Stiebel Eltron"
    assert hp.model == "WPMsystem"
    assert hp.sw_version is None  # Stiebel WPM doesn't expose firmware

    meter = devices["sys-1_meter"]
    assert meter.manufacturer == "Chint"
    assert meter.model == "DTSU666"
    assert meter.sw_version is None

    wb = devices["sys-1_wallbox"]
    assert wb.manufacturer == "go-e"
    assert wb.model == "HOMEfix 11kW"
    assert wb.sw_version == "60.5"


async def test_entities_are_parented_under_correct_sub_device(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Representative entity-to-device mappings from the spec table.

    Looks up entities by ``unique_id`` (the stable key) rather than
    ``entity_id`` (which now includes the sub-device-name prefix for
    fresh installs).
    """
    system = mock_system_factory(system_id="sys-1", assets=_all_assets())
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    sub_id = {
        key: next(
            d
            for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
            if (DOMAIN, f"sys-1_{key}") in d.identifiers
        ).id
        for key in ("inverter", "heat_pump", "meter", "wallbox")
    }
    parent_id = next(
        d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
        if (DOMAIN, "sys-1") in d.identifiers
    ).id

    by_unique_id = {
        r.unique_id: r for r in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }

    # One representative entity per sub-device + two parent-bound entities.
    expectations = {
        "sys-1_pv_power": sub_id["inverter"],
        "sys-1_heat_pumps_power": sub_id["heat_pump"],
        "sys-1_grid_power": sub_id["meter"],
        "sys-1_ev_chargers_power": sub_id["wallbox"],
        # Aggregate / system entities stay on the parent
        "sys-1_current_electricity_price": parent_id,
        "sys-1_self_sufficiency": parent_id,
    }
    for unique_id, expected_device_id in expectations.items():
        record = by_unique_id.get(unique_id)
        assert record is not None, f"entity with unique_id {unique_id!r} not registered"
        assert record.device_id == expected_device_id, (
            f"{unique_id}: device_id={record.device_id}, expected={expected_device_id}"
        )


async def test_unique_ids_unchanged_after_sub_device_split(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Entity unique_ids must NOT include the sub-device key — long-term
    statistics are keyed on entity_id (which HA preserves from the registry
    across reloads, but only as long as unique_id stays the same)."""
    system = mock_system_factory(system_id="sys-1", assets=_all_assets())
    entry = await _setup(hass, system)
    entity_reg = er.async_get(hass)

    unique_ids = {
        r.unique_id for r in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }

    # Spot-check a few of the entities that moved to sub-devices —
    # their unique_ids must still be the bare system_id + key form.
    for expected in (
        "sys-1_pv_power",
        "sys-1_pv_power_energy",
        "sys-1_heat_pumps_power",
        "sys-1_ev_chargers_power_energy",
        "sys-1_feed_in_revenue",
        "sys-1_ev_charger_cost",
        "sys-1_heat_pump_cost",
    ):
        assert expected in unique_ids, (
            f"unique_id {expected!r} missing — sub-device move must not have rewritten it"
        )


async def test_fresh_install_entity_ids_start_with_system_slug(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Issue #8: fresh-install entity_ids must be ``<platform>.<system>_<suffix>``.

    Without the ``apply_stable_entity_ids`` shim, HA composes entity_ids as
    ``<device_slug>_<entity_slug>`` for ``has_entity_name=True`` entities on
    sub-devices, so a fresh install lands on e.g.
    ``binary_sensor.wechselrichter_...`` (DE) / ``binary_sensor.inverter_...``
    (EN) — breaking the ``dashboard/dashboard.yaml`` ``SYSTEM_NAME``
    placeholder and creating i18n divergence.
    """
    system = mock_system_factory(system_id="sys-1", name="Test Home", assets=_all_assets())
    entry = await _setup(hass, system)
    entity_reg = er.async_get(hass)
    by_unique_id = {
        r.unique_id: r for r in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }

    # Sub-device sensors that HA would otherwise prefix with the translated
    # sub-device name. All must start with the system slug ("test_home").
    for unique_id, expected_entity_id in (
        ("sys-1_pv_power", "sensor.test_home_pv_power"),
        ("sys-1_heat_pumps_power", "sensor.test_home_heat_pumps_power"),
        ("sys-1_grid_power", "sensor.test_home_grid_power"),
        ("sys-1_ev_chargers_power", "sensor.test_home_ev_chargers_power"),
        ("sys-1_heat_pump_cost", "sensor.test_home_heat_pump_cost"),
        ("sys-1_ev_charger_cost", "sensor.test_home_ev_charger_cost"),
        ("sys-1_feed_in_revenue", "sensor.test_home_feed_in_revenue"),
        # System-parent entities were already correctly-prefixed pre-fix,
        # but the shim also applies to them — confirm no regression.
        ("sys-1_current_electricity_price", "sensor.test_home_current_electricity_price"),
        ("sys-1_self_sufficiency", "sensor.test_home_self_sufficiency"),
    ):
        record = by_unique_id.get(unique_id)
        assert record is not None, f"unique_id {unique_id!r} not registered"
        assert record.entity_id == expected_entity_id, (
            f"{unique_id}: got {record.entity_id!r}, expected {expected_entity_id!r}"
        )


async def test_system_name_with_umlauts_slugifies_cleanly(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Umlauts / dashes in the system name must produce ASCII-safe entity_ids.

    HA's ``slugify`` transliterates umlauts (ö → o, ü → u, ä → a) and
    normalises punctuation. Users with names like ``Höst-System Süd`` still
    get valid, predictable entity_ids across all sub-device entities.
    """
    system = mock_system_factory(system_id="sys-1", name="Höst-System Süd", assets=_all_assets())
    entry = await _setup(hass, system)
    entity_reg = er.async_get(hass)
    by_unique_id = {
        r.unique_id: r for r in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
    }
    record = by_unique_id["sys-1_pv_power"]
    assert record.entity_id == "sensor.host_system_sud_pv_power"


async def test_existing_registry_entity_ids_are_preserved(
    hass: HomeAssistant, mock_system_factory
) -> None:
    """Pre-fix installs already have entity_ids in the registry (possibly
    with translated slugs from before the fix). The apply_stable_entity_ids
    shim must NOT rewrite them — registry lookup by unique_id wins.
    """
    entity_reg = er.async_get(hass)
    # Simulate a pre-fix install: user-renamed entity_id already in registry.
    entity_reg.async_get_or_create(
        "sensor",
        DOMAIN,
        "sys-1_pv_power",
        suggested_object_id="wechselrichter_pv_leistung",  # old DE fresh-install id
    )

    system = mock_system_factory(system_id="sys-1", name="Test Home", assets=_all_assets())
    await _setup(hass, system)

    record = entity_reg.async_get_entity_id("sensor", DOMAIN, "sys-1_pv_power")
    assert record == "sensor.wechselrichter_pv_leistung", (
        "existing registry entity_id was overwritten — this breaks long-term "
        "statistics and user automations"
    )


async def test_missing_asset_falls_back_to_parent(hass: HomeAssistant, mock_system_factory) -> None:
    """When an asset type is missing, no sub-device exists; orphaned entities
    fall back to the system parent."""
    # Only inverter + meter present; heat pump and wallbox missing.
    partial = [
        _asset("HYBRID", manufacturer="Sungrow", model="SH6.0RT-V112", firmware="x"),
        _asset("METER", manufacturer="Chint", model="DTSU666", firmware=None),
    ]
    system = mock_system_factory(system_id="sys-1", assets=partial)
    entry = await _setup(hass, system)
    device_reg = dr.async_get(hass)
    entity_reg = er.async_get(hass)

    identifiers = {
        next(iter(d.identifiers))[1]
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
    }
    assert "sys-1_inverter" in identifiers
    assert "sys-1_meter" in identifiers
    assert "sys-1_heat_pump" not in identifiers
    assert "sys-1_wallbox" not in identifiers

    parent_id = next(
        d
        for d in dr.async_entries_for_config_entry(device_reg, entry.entry_id)
        if (DOMAIN, "sys-1") in d.identifiers
    ).id

    # Heat-pump-tagged entities fall back to the parent when the asset isn't
    # in the cloud's status_and_assets response (no firmware/manufacturer/
    # model to populate, so the sub-device is omitted entirely).
    hp_record = next(
        r
        for r in er.async_entries_for_config_entry(entity_reg, entry.entry_id)
        if r.unique_id == "sys-1_heat_pumps_power"
    )
    assert hp_record.device_id == parent_id
