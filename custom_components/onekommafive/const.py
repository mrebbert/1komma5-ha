"""Constants for the 1KOMMA5° integration."""

DOMAIN = "onekommafive"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SYSTEM_ID = "system_id"

LIVE_UPDATE_INTERVAL_SECONDS = 30
PRICE_UPDATE_INTERVAL_SECONDS = 3600  # 1 hour
OPTIMIZATION_UPDATE_INTERVAL_SECONDS = 900  # 15 minutes
WEATHER_UPDATE_INTERVAL_SECONDS = 3600  # 1 hour
SYSTEM_STATUS_UPDATE_INTERVAL_SECONDS = 300  # 5 minutes
ENERGY_UPDATE_INTERVAL_SECONDS = 900  # 15 minutes (API updates ~hourly)

ATTR_SYSTEM_ID = "system_id"
ATTR_SYSTEM_NAME = "system_name"

CONF_FEED_IN_TARIFF = "feed_in_tariff"
DEFAULT_FEED_IN_TARIFF = 0.0803

CONF_CHARGING_WINDOW_DURATION_MINUTES = "charging_window_duration_minutes"
DEFAULT_CHARGING_WINDOW_DURATION_MINUTES = 60

# Bus event fired whenever a new optimization decision is observed.
EVENT_OPTIMIZATION_DECISION = "onekommafive_optimization_decision"

# Bus events fired on edge transitions of the active electricity price.
# `_started`  → previous active slot had price > 0, new slot has price ≤ 0.
# `_ended`    → previous active slot had price ≤ 0, new slot has price > 0.
EVENT_NEGATIVE_PRICE_STARTED = "onekommafive_negative_price_started"
EVENT_NEGATIVE_PRICE_ENDED = "onekommafive_negative_price_ended"
