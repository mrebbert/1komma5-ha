---
title: Removal
description: How to cleanly uninstall the 1KOMMA5° integration from Home Assistant.
---

# Removing the integration

Removal is a two-step process: delete the config entry inside HA, then remove
the integration code via HACS (or manually).

## 1. Delete the config entry

**Settings → Devices & Services → 1KOMMA5°**, click the three-dot menu on the
system card, then **Delete**. HA unloads the integration and removes:

- all `sensor.*`, `binary_sensor.*`, `switch.*`, `select.*`, `number.*` entities
  for this system,
- all device entries (system + per-asset sub-devices),
- the services (`onekommafive.get_cheapest_window`,
  `onekommafive.get_most_expensive_window`, `onekommafive.refresh_now`,
  `onekommafive.assign_ev_to_wallbox`),
- the registered bus-event listeners.

Long-term statistics attached to energy/cost sensors are kept in the recorder
database. Delete them via **Developer tools → Statistics** if you want them
gone as well.

## 2. Remove the integration code

**HACS → Integrations → 1KOMMA5°**, click the three-dot menu, then **Remove**.
Restart Home Assistant once removal completes.

For non-HACS installs, delete the folder `custom_components/onekommafive/`
inside your HA config directory and restart.

## 3. Residual files (optional)

The integration stores a notification de-duplication cache under
`.storage/onekommafive.notifications.<entry_id>`. HA keeps this file after
step 1 so that re-adding the integration continues to deduplicate correctly;
delete it manually if you want a fully fresh start.

Nothing else is written outside the standard HA config entry, entity registry
and device registry stores, all of which are cleaned up by step 1.
