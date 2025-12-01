"""Telemetry simulator for an EV charger controller."""
from __future__ import annotations

try:  # pragma: no cover - runtime import convenience
    from .telemetry_simulator import (
        MeasurementSpec,
        SimulatorConfig,
        TelemetrySimulator,
        build_payload_from_specs,
    )
except ImportError:  # pragma: no cover
    from telemetry_simulator import (  # type: ignore
        MeasurementSpec,
        SimulatorConfig,
        TelemetrySimulator,
        build_payload_from_specs,
    )


EV_CHARGER_MEASUREMENTS: tuple[MeasurementSpec, ...] = (
    MeasurementSpec(
        name="phase_current_a",
        min_value=12,
        max_value=32,
        precision=1,
        unit="A",
        description="Average current per phase",
    ),
    MeasurementSpec(
        name="line_voltage_v",
        min_value=375,
        max_value=405,
        precision=0,
        unit="V",
        description="Line-to-line RMS voltage",
    ),
    MeasurementSpec(
        name="session_energy_kwh",
        min_value=8,
        max_value=22,
        precision=2,
        unit="kWh",
        description="Energy delivered in current session",
    ),
    MeasurementSpec(
        name="connector_temp_c",
        min_value=26,
        max_value=55,
        precision=1,
        unit="°C",
        description="Connector temperature for thermal monitoring",
    ),
)


def build_ev_charger_payload() -> dict[str, float]:
    return build_payload_from_specs(EV_CHARGER_MEASUREMENTS)


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
