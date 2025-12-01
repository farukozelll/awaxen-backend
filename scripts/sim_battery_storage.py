"""Telemetry simulator for the battery energy storage system."""
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


BATTERY_MEASUREMENTS: tuple[MeasurementSpec, ...] = (
    MeasurementSpec(
        name="state_of_charge_pct",
        min_value=35,
        max_value=97,
        precision=1,
        unit="%",
        description="Battery rack state of charge",
    ),
    MeasurementSpec(
        name="cabinet_temp_c",
        min_value=20,
        max_value=38,
        precision=1,
        unit="°C",
        description="Battery cabinet internal temperature",
    ),
    MeasurementSpec(
        name="charge_power_kw",
        min_value=-25,
        max_value=25,
        precision=2,
        unit="kW",
        description="Positive=charging, Negative=discharging",
    ),
)


def build_battery_payload() -> dict[str, float]:
    return build_payload_from_specs(BATTERY_MEASUREMENTS)


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
