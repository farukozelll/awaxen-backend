"""Telemetry simulator for the utility grid meter."""
from __future__ import annotations

import random

try:  # pragma: no cover - runtime import convenience
    from .telemetry_simulator import SimulatorConfig, TelemetrySimulator
except ImportError:  # pragma: no cover
    from telemetry_simulator import SimulatorConfig, TelemetrySimulator


def build_grid_meter_payload() -> dict[str, float]:
    import_power_kw = round(random.uniform(-10, 30), 2)
    pf = round(random.uniform(0.95, 1.0), 3)
    line_frequency_hz = round(random.uniform(49.8, 50.2), 2)

    return {
        "import_power_kw": import_power_kw,
        "power_factor": pf,
        "frequency_hz": line_frequency_hz,
    }


def create_simulator() -> TelemetrySimulator:
    config = SimulatorConfig(
        serial_number="AWX-CORE-0005",
        node_name="Grid Meter",
        interval_seconds=300,
    )
    return TelemetrySimulator(config, build_grid_meter_payload)


def main() -> None:
    create_simulator().run_forever()


if __name__ == "__main__":
    main()
