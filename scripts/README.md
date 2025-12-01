# Telemetry Simulator Scripts

This folder contains reusable telemetry simulator utilities plus five ready-to-run device simulators with different publish intervals.

## Available simulators

| Script | Device | Serial | Interval |
| --- | --- | --- | --- |
| `sim_inverter_fast.py` | Solar Inverter A | `AWX-CORE-0001` | 60 s |
| `sim_ev_charger.py` | EV Charger | `AWX-CORE-0002` | 120 s |
| `sim_battery_storage.py` | Battery Rack | `AWX-CORE-0003` | 180 s |
| `sim_pv_tracker.py` | PV Tracker | `AWX-CORE-0004` | 240 s |
| `sim_grid_meter.py` | Grid Meter | `AWX-CORE-0005` | 300 s |

All scripts share the `telemetry_simulator.py` base module and expose a `create_simulator()` helper so that they can be orchestrated in tests or background workers.

## MeasurementSpec (Inventory Alignment)

Her simulator artık `MeasurementSpec` dataclass'ı ile tanımlanmış ölçüm spesifikasyonları kullanıyor:

```python
from telemetry_simulator import MeasurementSpec, build_payload_from_specs

BATTERY_MEASUREMENTS = (
    MeasurementSpec(
        name="state_of_charge_pct",
        min_value=35,
        max_value=97,
        precision=1,
        unit="%",
        description="Battery rack state of charge",
    ),
    # ... diğer ölçümler
)

def build_battery_payload() -> dict[str, float]:
    return build_payload_from_specs(BATTERY_MEASUREMENTS)
```

Bu yapı sayesinde:
- Her ölçümün `name`, `unit`, `min/max_value` ve `description` bilgisi merkezi olarak tanımlanır
- Inventory (Asset) tablosuyla birebir eşleşir
- Frontend'de otomatik form/validasyon oluşturulabilir

## Running a single simulator

```bash
python -m scripts.sim_ev_charger
```

Each simulator accepts the standard `TELEMETRY_API_URL` environment variable; other identifiers are hard-coded for convenience but can be changed in the script if needed.

## Unified runner (tek script ile)

`start_all_simulators.py` artık hem tüm cihazları hem de seçtiğin tek cihazı başlatabiliyor:

```bash
# Varsayılan: tüm cihazlar threaded olarak başlar
python -m scripts.start_all_simulators

# Sadece EV şarj cihazını çalıştır
python -m scripts.start_all_simulators --device ev_charger

# Diğer seçenekler: inverter | battery | pv_tracker | grid_meter
```

Her mod çalışırken `CTRL+C` ile temiz biçimde durdurulur.

---

# Auto-Discovery (Otomatik Keşif) Sistemi

## Genel Bakış

Awaxen backend artık "Zero-Touch Provisioning" destekliyor. Gateway (Core cihaz) bilinmeyen bir sensör/inverter'dan sinyal aldığında:

1. **DiscoveryQueue** tablosuna kaydeder
2. **Socket.IO** ile frontend'e anlık bildirim gönderir
3. Kullanıcı panelden cihazı **onaylar** veya **yoksayar**

## Akış

```
[Sensör] --LoRa/Modbus--> [Gateway] --MQTT--> [Backend]
                                                  |
                                                  v
                                    Node kayıtlı mı? ──Yes──> Telemetry kaydet
                                                  |
                                                 No
                                                  |
                                                  v
                                    DiscoveryQueue'ya ekle
                                                  |
                                                  v
                                    Socket.IO: "device_discovered"
                                                  |
                                                  v
                                    [Frontend] 🔔 Yeni cihaz bulundu!
```

## API Endpoints

| Method | Endpoint | Açıklama |
| --- | --- | --- |
| GET | `/api/discovery/pending` | Bekleyen keşifleri listele |
| POST | `/api/discovery/claim` | Cihazı sahiplen (Node'a terfi) |
| POST | `/api/discovery/{id}/ignore` | Cihazı yoksay |
| DELETE | `/api/discovery/{id}` | Keşif kaydını sil |
| GET | `/api/discovery/stats` | Keşif istatistikleri |

## Claim (Sahiplenme) Örneği

```bash
curl -X POST http://localhost:5000/api/discovery/claim \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "discovery_id": 5,
    "name": "Sıra 3 Domates Sensörü",
    "node_type": "SENSOR_NODE"
  }'
```

## Socket.IO Event

Frontend'de `device_discovered` eventini dinleyin:

```javascript
socket.on("device_discovered", (data) => {
  // data: { discovery_id, device_identifier, protocol, guessed_type, gateway_name, site_name }
  showNotification(`🔔 Yeni cihaz bulundu: ${data.device_identifier}`);
});
```

## MQTT Payload Formatı

Gateway'in gönderdiği payload'da şu alanlar aranır:

```json
{
  "gateway_serial": "AWX-CORE-0001",
  "node_id": "LORA_A1B2C3D4",
  "dev_eui": "A1B2C3D4E5F6",
  "protocol": "LORA",
  "device_type": "SENSOR_NODE",
  "value": 24.5,
  "sensor_type": "temperature"
}
```

- `gateway_serial` veya `serial_number`: Gateway kimliği (zorunlu)
- `node_id`, `dev_eui`, `node_address`: Uç cihaz kimliği (keşif için gerekli)
- `protocol`: Haberleşme protokolü (LORA, MODBUS, ZIGBEE)
- `device_type`: Cihaz tipi tahmini
