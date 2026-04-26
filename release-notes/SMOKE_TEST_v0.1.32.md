# Smoke Test Checklist — v0.1.32

Run these checks in a real Home Assistant instance before tagging the release. Tick them off as you go.

## 1. Setup
- [ ] Fresh install: HACS → Custom Repository → install `mrebbert/1komma5-ha` at HEAD of `main`
- [ ] HA restart succeeds without errors in the log
- [ ] Settings → Devices & Services → Add Integration → "1KOMMA5°" — initial credential form appears
- [ ] Login with valid credentials — system appears and entities are created
- [ ] (Optional) Login with **invalid** credentials — `invalid_auth` error shown

## 2. Live data
- [ ] PV / battery / grid / consumption sensors all show values
- [ ] Self-Sufficiency sensor between 0–100 %
- [ ] Energy sensors (kWh) start accumulating after ~1 minute
- [ ] Battery Charge / Discharge Energy split sensors present
- [ ] EMS Auto Mode switch shows the correct state and toggles successfully

## 3. Prices & forecast
- [ ] Current Electricity Price shows the active 15-min slot (compare with API)
- [ ] Average / Lowest / Highest Electricity Price values look plausible
- [ ] Negative Price Slots Today shows a count (or 0)
- [ ] Tomorrow's Average / Lowest / Highest Price — `unknown` before ~13:00 CET, then values
- [ ] `forecast` attribute on Current Electricity Price contains 15-min slots covering ~30 h
- [ ] HA History panel shows a price chart for the price sensors (Long-Term Statistics enabled)

## 4. Binary sensors
- [ ] Cheap Electricity is ON when current price < daily average, OFF otherwise
- [ ] Cheapest Hour Now is ON only during the cheapest 15-min slot in the forecast
- [ ] Both sensors update at :00 / :15 / :30 / :45 (watch for ~30 s after a quarter-hour boundary)

## 5. EV charger (if connected)
- [ ] Target SoC sensor shows current target
- [ ] Charging Mode select dropdown lists SMART_CHARGE / QUICK_CHARGE / SOLAR_CHARGE
- [ ] Switching modes via the select sends to API and the sensor reflects the new mode after ~30 s
- [ ] Vehicle SoC (Manual) number — only available when in SMART_CHARGE; setting a value succeeds
- [ ] Target SoC number — setting a value succeeds, sensor updates
- [ ] Departure Time entity shows current schedule, setting a new time succeeds

## 6. Optimizations
- [ ] Optimization Decisions Today shows a non-zero count (assuming the API has events for today)
- [ ] Last Optimization Decision shows a string like `BATTERY_CHARGE_FROM_GRID` or `HEATPUMP_AUTO`
- [ ] Cost / Energy Bought / Energy Sold sensors are `unknown` (API doesn't populate yet — expected)

## 7. Cost & Revenue
- [ ] Electricity Cost increments while the house is consuming from grid
- [ ] Feed-in Revenue increments while exporting to grid
- [ ] Both appear in the Energy Dashboard cost configuration
- [ ] (If negative price scenario): consuming during a negative-price slot **decreases** Electricity Cost

## 8. Diagnostic sensors
- [ ] In Settings → Devices → 1KOMMA5° → Diagnostic, the three timestamps tick over:
  - Last Live Update — every ~30 s
  - Last Price Update — every ~1 h
  - Last Optimization Update — every ~15 min
- [ ] All three are within the last 2 update intervals (none stuck on "never updated")

## 9. Reauth flow
- [ ] Change the 1KOMMA5° account password externally
- [ ] Wait for the next coordinator refresh — HA shows a "Re-authentication required" notification
- [ ] Click the notification → re-enter new credentials → integration reloads successfully
- [ ] All sensor history is preserved (check the History panel for any sensor)

## 10. Reconfigure flow
- [ ] Settings → Devices & Services → 1KOMMA5° → ⋮ → Reconfigure
- [ ] Username pre-filled, password empty
- [ ] Submitting valid credentials reloads the integration
- [ ] Submitting invalid credentials shows `invalid_auth` and no reload happens

## 11. Services
- [ ] Developer Tools → Services → `onekommafive.get_cheapest_window`
  - duration_minutes: 120
  - Submit → response contains `start`, `end`, `average_price`, `slot_count: 8`, `found: true`
- [ ] Same for `onekommafive.get_most_expensive_window` — returns a different, more expensive window
- [ ] With `latest_end` constraint that's earlier than the current time → response has `found: false`
- [ ] With invalid `duration_minutes` (e.g. 5 — below min 15) — service rejects with a validation error

## 12. Options flow
- [ ] Settings → Devices & Services → 1KOMMA5° → Configure → change Feed-in Tariff
- [ ] Integration reloads, Feed-in Revenue accumulates with the new rate

## 13. Logs
- [ ] No `ERROR` level log messages from `custom_components.onekommafive` or `onekommafive` in normal operation
- [ ] No HA `state_class` warnings for 1KOMMA5° entities (specifically the optimization sensors that previously had this issue)

## 14. Translations
- [ ] Switch HA UI language to German — entity names appear in German
- [ ] Switch back to English — entity names appear in English
- [ ] Service field labels are localised in the Developer Tools service form

---

When everything is ticked, tag and release:

```bash
git tag v0.1.32
git push origin v0.1.32
gh release create v0.1.32 --notes-file release-notes/v0.1.32.md --title "v0.1.32"
```
