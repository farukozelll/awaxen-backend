"""Telemetry simulator for the battery energy storage system."""
from __future__ import annotations

import random

try:  # pragma: no cover - runtime import convenience
    from .telemetry_simulator import SimulatorConfig, TelemetrySimulator
except ImportError:  # pragma: no cover
    from telemetry_simulator import SimulatorConfig, TelemetrySimulator


def build_battery_payload() -> dict[str, float]:
    soc_percent = round(random.uniform(40, 95), 1)
    cabinet_temp_c = round(random.uniform(22, 34), 1)
    charge_power_kw = round(random.uniform(-20, 20), 2)  # negative = discharge

    return {
        "state_of_charge_pct": soc_percent,
        "cabinet_temp_c": cabinet_temp_c,
        "charge_power_kw": charge_power_kw,
    }


def create_simulator() -> TelemetrySimulator:
    config = SimulatorConfig(
        serial_number="AWX-CORE-0003",
        node_name="Battery Rack",
        interval_seconds=180,
    )
    return TelemetrySimulator(config, build_battery_payload)


def main() -> None:
    create_simulator().run_forever()


if __name__ == "__main__":
    main()
