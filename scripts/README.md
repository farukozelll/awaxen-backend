# Telemetry Simulator Scripts

This folder contains reusable telemetry simulator utilities plus five ready-to-run device simulators with different publish intervals.

## Available simulators

| Script | Device | Serial | Interval |
| --- | --- | --- | --- |
| `sim_inverter_fast.py` | Solar Inverter A | `AWX-CORE-0001` | 60 s |
| `sim_ev_charger.py` | EV Charger | `AWX-CORE-0002` | 120 s |
| `sim_battery_storage.py` | Battery Rack | `AWX-CORE-0003` | 180 s |
| `sim_pv_tracker.py` | PV Tracker | `AWX-CORE-0004` | 240 s |
| `sim_grid_meter.py` | Grid Meter | `AWX-CORE-0005` | 300 s |

All scripts share the `telemetry_simulator.py` base module and expose a `create_simulator()` helper so that they can be orchestrated in tests or background workers.

## Running a single simulator

```bash
python -m scripts.sim_ev_charger
```

Each simulator accepts the standard `TELEMETRY_API_URL` environment variable; other identifiers are hard-coded for convenience but can be changed in the script if needed.

## Unified runner (tek script ile)

`start_all_simulators.py` artık hem tüm cihazları hem de seçtiğin tek cihazı başlatabiliyor:

```bash
# Varsayılan: tüm cihazlar threaded olarak başlar
python -m scripts.start_all_simulators

# Sadece EV şarj cihazını çalıştır
python -m scripts.start_all_simulators --device ev_charger

# Diğer seçenekler: inverter | battery | pv_tracker | grid_meter
```

Her mod çalışırken `CTRL+C` ile temiz biçimde durdurulur.
