"""Unified CLI runner for telemetry simulators (single or multi device)."""
from __future__ import annotations

import argparse
import threading
import time
from collections.abc import Callable, Iterable

try:  # pragma: no cover - runtime import convenience
    from .sim_battery_storage import create_simulator as create_battery_sim
    from .sim_ev_charger import create_simulator as create_ev_charger_sim
    from .sim_grid_meter import create_simulator as create_grid_meter_sim
    from .sim_inverter_fast import create_simulator as create_fast_inverter_sim
    from .sim_pv_tracker import create_simulator as create_tracker_sim
    from .telemetry_simulator import TelemetrySimulator
except ImportError:  # pragma: no cover
    from sim_battery_storage import create_simulator as create_battery_sim  # type: ignore
    from sim_ev_charger import create_simulator as create_ev_charger_sim  # type: ignore
    from sim_grid_meter import create_simulator as create_grid_meter_sim  # type: ignore
    from sim_inverter_fast import create_simulator as create_fast_inverter_sim  # type: ignore
    from sim_pv_tracker import create_simulator as create_tracker_sim  # type: ignore
    from telemetry_simulator import TelemetrySimulator  # type: ignore

SimulatorFactory = Callable[[], TelemetrySimulator]

SIMULATORS: dict[str, tuple[str, SimulatorFactory]] = {
    "inverter": ("Solar Inverter A (60s)", create_fast_inverter_sim),
    "ev_charger": ("EV Charger (120s)", create_ev_charger_sim),
    "battery": ("Battery Rack (180s)", create_battery_sim),
    "pv_tracker": ("PV Tracker (240s)", create_tracker_sim),
    "grid_meter": ("Grid Meter (300s)", create_grid_meter_sim),
}


def _run_all(selected: Iterable[tuple[str, SimulatorFactory]]) -> None:
    stop_event = threading.Event()
    threads: list[threading.Thread] = []

    for label, factory in selected:
        simulator = factory()
        thread = threading.Thread(
            target=simulator.run_forever,
            kwargs={"stop_event": stop_event},
            name=f"sim-{label}",
            daemon=True,
        )
        thread.start()
        threads.append(thread)
        print(f"Started {label}")

    print("All simulator threads are now running. Press CTRL+C to stop.")

    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStop signal received. Waiting for simulators to exit...")
        stop_event.set()
        for thread in threads:
            thread.join(timeout=5)

    print("Telemetry simulators stopped.")


def _run_single(label: str, factory: SimulatorFactory) -> None:
    print(f"Starting {label}. Press CTRL+C to stop.")
    simulator = factory()
    try:
        simulator.run_forever()
    except KeyboardInterrupt:
        print("\nSimulator stopped by user.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run telemetry simulators. By default all devices run in parallel; "
            "use --device to run only one."
        )
    )
    parser.add_argument(
        "-d",
        "--device",
        choices=tuple(SIMULATORS.keys()) + ("all",),
        default="all",
        help="Device key to run (default: all).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.device == "all":
        _run_all(SIMULATORS.values())
        return

    label, factory = SIMULATORS[args.device]
    _run_single(label, factory)


if __name__ == "__main__":
    main()
