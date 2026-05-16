"""Constants for the 1KOMMA5° integration."""

DOMAIN = "onekommafive"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SYSTEM_ID = "system_id"

LIVE_UPDATE_INTERVAL_SECONDS = 30
PRICE_UPDATE_INTERVAL_SECONDS = 3600  # 1 hour
OPTIMIZATION_UPDATE_INTERVAL_SECONDS = 900  # 15 minutes
WEATHER_UPDATE_INTERVAL_SECONDS = 3600  # 1 hour

ATTR_SYSTEM_ID = "system_id"
ATTR_SYSTEM_NAME = "system_name"

CONF_FEED_IN_TARIFF = "feed_in_tariff"
DEFAULT_FEED_IN_TARIFF = 0.0803

# Bus event fired whenever a new optimization decision is observed.
EVENT_OPTIMIZATION_DECISION = "onekommafive_optimization_decision"

# Historical-backfill walk-back configuration.
EMPTY_DAY_LIMIT = 7
HARD_CEILING_DAYS = 3650
BACKFILL_THROTTLE_SECONDS = 0.5

# Maps `EnergySlot` attribute names to our sensor translation_keys for
# the kWh, total_increasing class of energy sensors.
ENERGY_HISTORY_FIELD_MAP: dict[str, str] = {
    "production": "pv_power_energy",
    "grid_supply": "grid_consumption_power_energy",
    "grid_feed_in": "grid_feed_in_power_energy",
    "consumption_household_total": "household_power_energy",
    "consumption_heat_pump_total": "heat_pumps_power_energy",
    "consumption_ev_total": "ev_chargers_power_energy",
    "consumption_ac_total": "acs_power_energy",
    "battery_charge": "battery_charge_power_energy",
    "battery_discharge": "battery_discharge_power_energy",
}

# Derived field — sum of the per-consumer totals; matches the live
# `consumption_power_energy` sensor.
CONSUMPTION_TOTAL_KEY = "consumption_power_energy"

# Measurement (mean/min/max) sensor backfilled from the API.
SOC_STATISTIC_KEY = "battery_soc"

# Frozenset of every statistic_id key the integration owns. Used by the
# clear_history service to bulk-remove all our stats for a config entry.
# Commit 2 will extend this with the monetary keys.
ALL_STATISTIC_KEYS: frozenset[str] = frozenset(
    {*ENERGY_HISTORY_FIELD_MAP.values(), CONSUMPTION_TOTAL_KEY, SOC_STATISTIC_KEY}
)
