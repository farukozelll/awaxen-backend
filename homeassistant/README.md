# Home Assistant Integration for Awaxen

Bu klasör, Home Assistant'ın Awaxen Backend ile entegrasyonu için gerekli yapılandırma dosyalarını içerir.

## Neden Home Assistant?

Home Assistant, Awaxen için bir **"Universal IoT Adapter"** görevi görür:

- **1000+ Entegrasyon**: Shelly, Tapo, Tuya, Philips Hue, Samsung SmartThings, Zigbee, Z-Wave ve daha fazlası
- **Standart Veri Formatı**: Farklı markaların verileri standart formatta Awaxen'e aktarılır
- **Yerel Kontrol**: Bulut bağımlılığı olmadan yerel ağda cihaz kontrolü
- **Otomasyon Desteği**: Home Assistant otomasyonları Awaxen ile senkronize çalışır

## Kurulum Adımları

### 1. Home Assistant'ı Başlat

```bash
# Sadece Home Assistant profili ile
docker-compose --profile homeassistant up -d homeassistant

# Veya tüm sistem ile birlikte
docker-compose --profile homeassistant up -d
```

### 2. Home Assistant'a Giriş Yap

1. Tarayıcıda `http://localhost:8123` adresine git
2. İlk kurulumda hesap oluştur
3. Onboarding adımlarını tamamla

### 3. MQTT Entegrasyonunu Ekle

1. **Settings** → **Devices & Services** → **Add Integration**
2. **MQTT** ara ve seç
3. Broker bilgilerini gir:
   - **Broker**: `mqtt` (Docker network içinde) veya `localhost`
   - **Port**: `1883`
   - **Username**: `.env` dosyasındaki `MQTT_USERNAME`
   - **Password**: `.env` dosyasındaki `MQTT_PASSWORD`

### 4. MQTT Statestream Yapılandır

Home Assistant'ın `configuration.yaml` dosyasına aşağıdaki ayarları ekle:

```yaml
# Awaxen'e veri gönderimi
mqtt_statestream:
  base_topic: awaxen
  publish_attributes: true
  publish_timestamps: true
  include:
    domains:
      - sensor
      - switch
      - light
      - climate
      - binary_sensor
```

### 5. Cihazları Ekle

Home Assistant'a cihazlarını ekle:
- **Shelly**: Shelly entegrasyonu
- **Tapo**: TP-Link Tapo entegrasyonu
- **Tuya**: Tuya/Smart Life entegrasyonu
- **Zigbee**: ZHA veya Zigbee2MQTT

## Veri Akışı

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────┐     ┌─────────────┐
│  IoT Cihaz  │────▶│ Home Assistant  │────▶│ MQTT Broker │────▶│   Awaxen    │
│ (Tapo, vb.) │     │   (Adapter)     │     │ (Mosquitto) │     │  Backend    │
└─────────────┘     └─────────────────┘     └─────────────┘     └─────────────┘
```

## Webhook Endpoints

Awaxen, Home Assistant'tan gelen verileri işlemek için webhook endpoint'leri sağlar:

### Device State Update
```
POST /webhooks/homeassistant/device
```

### Telemetry Data
```
POST /webhooks/homeassistant/telemetry
```

### Device Discovery
```
POST /webhooks/homeassistant/discovery
```

## Örnek Otomasyon

Home Assistant'ta cihaz durumu değiştiğinde Awaxen'e bildirim gönderen otomasyon:

```yaml
automation:
  - alias: "Awaxen - Device State Notification"
    trigger:
      - platform: state
        entity_id:
          - switch.tapo_plug_1
    action:
      - service: mqtt.publish
        data:
          topic: "awaxen/device_events"
          payload_template: >
            {
              "entity_id": "{{ trigger.entity_id }}",
              "from_state": "{{ trigger.from_state.state }}",
              "to_state": "{{ trigger.to_state.state }}",
              "timestamp": "{{ now().isoformat() }}"
            }
```

## Sorun Giderme

### MQTT Bağlantı Hatası
- Broker adresinin doğru olduğundan emin ol
- Docker network içindeysen `mqtt`, dışındaysan `localhost` kullan
- Kullanıcı adı ve şifrenin doğru olduğunu kontrol et

### Cihazlar Görünmüyor
- Home Assistant'ta cihazın düzgün eklendiğinden emin ol
- MQTT Statestream'in aktif olduğunu kontrol et
- Awaxen'de cihazın `external_id` alanının HA entity_id ile eşleştiğini doğrula

### Veri Gelmiyor
- MQTT broker loglarını kontrol et: `docker logs awaxen_mqtt`
- Home Assistant loglarını kontrol et: `docker logs awaxen_homeassistant`
