"""Telemetry simulator for the fastest-reporting solar inverter."""
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


INVERTER_MEASUREMENTS: tuple[MeasurementSpec, ...] = (
    MeasurementSpec(
        name="production_kw",
        min_value=3.5,
        max_value=5.5,
        precision=2,
        unit="kW",
        description="Real-time AC output power",
    ),
    MeasurementSpec(
        name="dc_bus_voltage_v",
        min_value=760,
        max_value=840,
        precision=1,
        unit="V",
        description="DC bus voltage",
    ),
    MeasurementSpec(
        name="dc_bus_current_a",
        min_value=4.5,
        max_value=7.0,
        precision=2,
        unit="A",
        description="DC bus current",
    ),
    MeasurementSpec(
        name="ac_frequency_hz",
        min_value=49.9,
        max_value=50.1,
        precision=2,
        unit="Hz",
        description="Inverter AC frequency",
    ),
)


def build_inverter_payload() -> dict[str, float]:
    return build_payload_from_specs(INVERTER_MEASUREMENTS)


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
