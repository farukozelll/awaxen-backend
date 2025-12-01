"""Telemetry simulator for an EV charger controller."""
from __future__ import annotations

import random

try:  # pragma: no cover - runtime import convenience
    from .telemetry_simulator import SimulatorConfig, TelemetrySimulator
except ImportError:  # pragma: no cover
    from telemetry_simulator import SimulatorConfig, TelemetrySimulator


def build_ev_charger_payload() -> dict[str, float]:
    phase_current_a = round(random.uniform(15, 32), 1)
    line_voltage_v = round(random.uniform(380, 400), 0)
    session_energy_kwh = round(random.uniform(12, 18), 2)

    return {
        "phase_current_a": phase_current_a,
        "line_voltage_v": line_voltage_v,
        "session_energy_kwh": session_energy_kwh,
    }


def create_simulator() -> TelemetrySimulator:
    config = SimulatorConfig(
        serial_number="AWX-CORE-0002",
        node_name="EV Charger",
        interval_seconds=120,
    )
    return TelemetrySimulator(config, build_ev_charger_payload)


def main() -> None:
    create_simulator().run_forever()


if __name__ == "__main__":
    main()
