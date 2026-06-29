# Home Assistant Energy Dashboard setup

All energy sensors use `state_class: total_increasing` and the cost/revenue sensors use `state_class: total` + `device_class: monetary`, so they drop straight into Home Assistant's **Energy Dashboard** with no helper sensors needed.

**Settings → Dashboards → Energy → Add Source** — pick by friendly name:

| Energy Dashboard slot | Friendly name | Underlying key |
|---|---|---|
| Grid consumption (import) | *Grid Import Energy* | `grid_consumption_power_energy` |
| Return to grid (export) | *Grid Export Energy* | `grid_feed_in_power_energy` |
| Solar production | *PV Energy* | `pv_power_energy` |
| Home battery → Energy going in | *Battery Charge Energy* | `battery_charge_power_energy` |
| Home battery → Energy coming out | *Battery Discharge Energy* | `battery_discharge_power_energy` |
| Individual device → Heat pump | *Heat Pump Energy* | `heat_pumps_power_energy` |
| Individual device → EV charger | *EV Charging Energy* | `ev_chargers_power_energy` |
| Individual device → AC | *AC Energy* | `acs_power_energy` |
| Individual device → Household | *Household Energy* | `household_power_energy` |

**Grid pricing:**
On the grid-import source, pick *Use a sensor tracking the total costs* and select **Electricity Cost** (`electricity_cost`). It already integrates the live dynamic price (incl. negative slots), so no static price field needed.

**Return-to-grid revenue:**
On the grid-export source, pick *Use a sensor tracking the total costs* and select **Feed-in Revenue** (`feed_in_revenue`). The underlying tariff is configurable under **Settings → Devices & Services → 1KOMMA5° → Configure**.

> The Battery Power and Grid Power sensors are bidirectional and therefore not Energy-Dashboard-compatible. Use the dedicated charge/discharge and import/export pairs above instead.
