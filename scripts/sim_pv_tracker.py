"""Telemetry simulator for a PV tracker controller."""
from __future__ import annotations

import random

try:  # pragma: no cover - runtime import convenience
    from .telemetry_simulator import SimulatorConfig, TelemetrySimulator
except ImportError:  # pragma: no cover
    from telemetry_simulator import SimulatorConfig, TelemetrySimulator


def build_tracker_payload() -> dict[str, float]:
    tilt_deg = round(random.uniform(5, 35), 1)
    azimuth_deg = round(random.uniform(120, 240), 1)
    wind_speed_mps = round(random.uniform(0, 15), 1)

    return {
        "tilt_deg": tilt_deg,
        "azimuth_deg": azimuth_deg,
        "wind_speed_mps": wind_speed_mps,
    }


def create_simulator() -> TelemetrySimulator:
    config = SimulatorConfig(
        serial_number="AWX-CORE-0004",
        node_name="PV Tracker",
        interval_seconds=240,
    )
    return TelemetrySimulator(config, build_tracker_payload)


def main() -> None:
    create_simulator().run_forever()


if __name__ == "__main__":
    main()
