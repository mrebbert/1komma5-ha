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
