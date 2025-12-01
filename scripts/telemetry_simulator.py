"""Reusable telemetry simulator primitives and default runnable script."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
import random
import threading
import time
from typing import Any, Callable, Dict, Optional, Sequence

import requests


PayloadBuilder = Callable[[], Dict[str, Any]]


@dataclass(frozen=True, slots=True)
class MeasurementSpec:
    """Definition of a single inventory signal in telemetry payload."""

    name: str
    min_value: float
    max_value: float
    precision: int = 2
    unit: str | None = None
    description: str | None = None

    def sample(self) -> float:
        value = random.uniform(self.min_value, self.max_value)
        return round(value, self.precision)


def build_payload_from_specs(specs: Sequence[MeasurementSpec]) -> Dict[str, float]:
    """Generate a payload dict using the provided measurement specs."""

    return {spec.name: spec.sample() for spec in specs}


def _default_api_url() -> str:
    return os.getenv("TELEMETRY_API_URL", "http://localhost:5000/api/telemetry")


@dataclass(slots=True)
class SimulatorConfig:
    """Configuration for a single simulated core device."""

    serial_number: str
    node_name: str
    interval_seconds: int = 300
    api_url: str = field(default_factory=_default_api_url)


class TelemetrySimulator:
    """Continuously sends randomized telemetry payloads for a device."""

    def __init__(self, config: SimulatorConfig, payload_builder: PayloadBuilder) -> None:
        self.config = config
        self._payload_builder = payload_builder

    def build_payload(self) -> Dict[str, Any]:
        payload = {
            "serial_number": self.config.serial_number,
            "node_name": self.config.node_name,
            "data": self._payload_builder(),
        }
        return payload

    def send_payload(self, payload: Dict[str, Any]) -> None:
        response = requests.post(self.config.api_url, json=payload, timeout=10)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Backend responded {response.status_code}: {response.text}"
            )

        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {self.config.serial_number} -> "
            + " ".join(f"{k}={v}" for k, v in payload["data"].items())
        )

    def run_forever(self, stop_event: Optional[threading.Event] = None) -> None:
        """Send payloads indefinitely until interrupted or stop_event is set."""

        print(
            "Telemetry simulator started. Press CTRL+C to stop.\n"
            f"API_URL={self.config.api_url}\n"
            f"SERIAL_NUMBER={self.config.serial_number}\n"
            f"NODE_NAME={self.config.node_name}\n"
            f"INTERVAL={self.config.interval_seconds}s"
        )

        while True:
            if stop_event and stop_event.is_set():
                break

            payload = self.build_payload()
            try:
                self.send_payload(payload)
            except Exception as exc:  # noqa: BLE001 - just log and continue
                print(f"Error sending telemetry for {self.config.serial_number}: {exc}")

            if stop_event:
                if stop_event.wait(self.config.interval_seconds):
                    break
            else:
                time.sleep(self.config.interval_seconds)


def default_payload_builder() -> Dict[str, Any]:
    """Create a payload with slightly randomized inverter values."""

    power = random.uniform(3800, 4500)
    voltage = random.uniform(780, 830)
    return {"power": round(power, 2), "voltage": round(voltage, 2)}


def main() -> None:
    config = SimulatorConfig(
        serial_number=os.getenv("TELEMETRY_SERIAL", "AWX-CORE-0001"),
        node_name=os.getenv("TELEMETRY_NODE", "Solar Inverter"),
        interval_seconds=int(os.getenv("TELEMETRY_INTERVAL_SECONDS", "300")),
    )
    simulator = TelemetrySimulator(config, default_payload_builder)
    simulator.run_forever()


if __name__ == "__main__":
    main()
