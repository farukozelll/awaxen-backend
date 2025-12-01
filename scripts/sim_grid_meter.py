"""Telemetry simulator for the utility grid meter."""
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


GRID_METER_MEASUREMENTS: tuple[MeasurementSpec, ...] = (
    MeasurementSpec(
        name="import_power_kw",
        min_value=-12,
        max_value=35,
        precision=2,
        unit="kW",
        description="Positive=import from grid, negative=export",
    ),
    MeasurementSpec(
        name="power_factor",
        min_value=0.93,
        max_value=1.0,
        precision=3,
        description="Three-phase total power factor",
    ),
    MeasurementSpec(
        name="frequency_hz",
        min_value=49.7,
        max_value=50.3,
        precision=2,
        unit="Hz",
        description="Grid frequency",
    ),
    MeasurementSpec(
        name="voltage_ll_v",
        min_value=380,
        max_value=410,
        precision=1,
        unit="V",
        description="Line-to-line RMS voltage",
    ),
)


def build_grid_meter_payload() -> dict[str, float]:
    return build_payload_from_specs(GRID_METER_MEASUREMENTS)


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
