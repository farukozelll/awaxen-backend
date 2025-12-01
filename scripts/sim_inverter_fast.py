"""Telemetry simulator for the fastest-reporting solar inverter."""
from __future__ import annotations

import random

try:  # pragma: no cover - runtime import convenience
    from .telemetry_simulator import SimulatorConfig, TelemetrySimulator
except ImportError:  # pragma: no cover
    from telemetry_simulator import SimulatorConfig, TelemetrySimulator


def build_inverter_payload() -> dict[str, float]:
    production_kw = round(random.uniform(4.5, 5.2), 2)
    dc_voltage = round(random.uniform(780, 820), 1)
    ac_frequency = round(random.uniform(49.9, 50.1), 2)

    return {
        "production_kw": production_kw,
        "dc_bus_voltage_v": dc_voltage,
        "ac_frequency_hz": ac_frequency,
    }


def create_simulator() -> TelemetrySimulator:
    config = SimulatorConfig(
        serial_number="AWX-CORE-0001",
        node_name="Solar Inverter A",
        interval_seconds=60,
    )
    return TelemetrySimulator(config, build_inverter_payload)


def main() -> None:
    create_simulator().run_forever()


if __name__ == "__main__":
    main()
