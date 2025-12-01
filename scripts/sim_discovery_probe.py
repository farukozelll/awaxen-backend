"""Utility script that publishes fake node payloads to trigger DiscoveryQueue entries."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import uuid
from typing import Any, Dict

import paho.mqtt.client as mqtt


def _sanitize_host(raw_url: str) -> str:
    """Strip mqtt:// style prefixes because paho expects only hostname."""
    if not raw_url:
        return ""
    lowered = raw_url.lower()
    for prefix in ("mqtt://", "mqtts://", "tcp://", "ssl://"):
        if lowered.startswith(prefix):
            return raw_url[len(prefix):].rstrip("/")
    return raw_url.rstrip("/")


def _build_payload(gateway_serial: str, protocol: str, device_type: str) -> Dict[str, Any]:
    node_identifier = uuid.uuid4().hex[:12].upper()
    measurement_value = round(random.uniform(15.0, 32.0), 2)

    return {
        "gateway_serial": gateway_serial,
        "node_id": node_identifier,
        "dev_eui": node_identifier,
        "protocol": protocol,
        "device_type": device_type,
        "sensor_type": "temperature",
        "value": measurement_value,
        "rssi": round(random.uniform(-90, -60), 1),
        "payload": {
            "humidity": round(random.uniform(40, 80), 1),
            "battery_level": round(random.uniform(30, 95), 1),
        },
    }


def _create_client(host: str, port: int, username: str | None, password: str | None) -> mqtt.Client:
    client = mqtt.Client(client_id=f"discovery-sim-{uuid.uuid4().hex[:8]}")
    if username:
        client.username_pw_set(username=username, password=password)
    client.connect(host, port, keepalive=30)
    client.loop_start()
    return client


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish random nodes to trigger discovery queue")
    parser.add_argument("--gateway", default=os.getenv("DISCOVERY_GATEWAY_SERIAL", "AWX-CORE-0001"), help="Registered gateway serial number")
    parser.add_argument("--count", type=int, default=3, help="How many fake nodes to publish")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between publishes")
    parser.add_argument("--protocol", default="LORA", help="Protocol hint in payload")
    parser.add_argument("--device-type", default="SENSOR_NODE", help="Device type hint in payload")
    parser.add_argument("--topic", default=None, help="Override MQTT topic (default awaxen/sensors/<gateway>)")
    parser.add_argument("--mqtt-url", default=os.getenv("MQTT_BROKER_URL", "mqtt://localhost"), help="MQTT broker URL")
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("MQTT_BROKER_PORT", "1883")), help="MQTT broker port")
    parser.add_argument("--mqtt-username", default=os.getenv("MQTT_USERNAME"), help="MQTT username if needed")
    parser.add_argument("--mqtt-password", default=os.getenv("MQTT_PASSWORD"), help="MQTT password if needed")
    args = parser.parse_args()

    host = _sanitize_host(args.mqtt_url)
    if not host:
        raise SystemExit("MQTT host could not be determined. Provide --mqtt-url or set MQTT_BROKER_URL")

    topic = args.topic or f"awaxen/sensors/{args.gateway}".lower()
    client = _create_client(host, args.mqtt_port, args.mqtt_username, args.mqtt_password)

    try:
        for idx in range(1, args.count + 1):
            payload = _build_payload(args.gateway, args.protocol, args.device_type)
            message = json.dumps(payload)
            info = client.publish(topic, message, qos=0, retain=False)
            info.wait_for_publish()
            print(f"[{idx}/{args.count}] Published discovery payload -> topic={topic} dev_eui={payload['dev_eui']}")
            time.sleep(args.interval)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
