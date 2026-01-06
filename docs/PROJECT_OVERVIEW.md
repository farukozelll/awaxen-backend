# 🌞 Awaxen Backend - Proje Özeti

**Enterprise-grade IoT & Energy Management SaaS Platform**

---

## 📋 İçindekiler

1. [Genel Bakış](#genel-bakış)
2. [Teknoloji Yığını](#teknoloji-yığını)
3. [Veritabanı Şeması](#veritabanı-şeması)
4. [Rol ve Yetki Sistemi](#rol-ve-yetki-sistemi)
5. [Modüller ve Endpoint'ler](#modüller-ve-endpointler)
6. [User Story'ler](#user-storyler)
7. [Sistem Akışı](#sistem-akışı)

---

## 🎯 Genel Bakış

Awaxen, gayrimenkul ve enerji yönetimi için geliştirilmiş bir SaaS platformudur. Temel özellikleri:

- **Multi-tenant Mimari**: Her organizasyon kendi verilerine izole erişim
- **IoT Entegrasyonu**: Gateway ve cihaz yönetimi, telemetri verisi toplama
- **Gayrimenkul Yönetimi**: Hiyerarşik varlık yapısı (Site → Block → Floor → Unit)
- **Enerji Yönetimi**: Üretim/tüketim takibi, tasarruf hesaplama
- **Bildirim Sistemi**: 3 kanallı (In-App, Push, Telegram)
- **Faturalama**: Cüzdan, işlem ve fatura yönetimi

---

## 🛠️ Teknoloji Yığını

| Katman | Teknoloji |
|--------|-----------|
| **Backend** | FastAPI (Python 3.12) |
| **Database** | PostgreSQL + TimescaleDB |
| **Cache** | Redis |
| **Message Broker** | MQTT (Mosquitto) |
| **Auth** | Auth0 (JWT RS256) |
| **Push Notifications** | Firebase Cloud Messaging (FCM) |
| **Container** | Docker + Docker Compose |
| **API Docs** | Swagger UI (OpenAPI 3.0) |

---

## 🗄️ Veritabanı Şeması

### Auth Modülü

```
┌─────────────────────────────────────────────────────────────────┐
│                           USER                                   │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ auth0_id (String, Unique) - Auth0 user ID                       │
│ email (String, Unique)                                          │
│ hashed_password (String, Nullable) - Auth0 kullanıcıları için   │
│ full_name (String)                                              │
│ phone (String)                                                  │
│ telegram_username (String)                                      │
│ telegram_chat_id (String) - Telegram bildirimleri için          │
│ is_active (Boolean)                                             │
│ is_superuser (Boolean)                                          │
│ is_verified (Boolean)                                           │
│ last_login (DateTime)                                           │
│ created_at, updated_at                                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ORGANIZATION_USER                            │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ user_id (FK → User)                                             │
│ organization_id (FK → Organization)                             │
│ role_id (FK → Role)                                             │
│ is_default (Boolean) - Varsayılan organizasyon                  │
│ joined_at (DateTime)                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│      ORGANIZATION        │    │          ROLE            │
├──────────────────────────┤    ├──────────────────────────┤
│ id (UUID, PK)            │    │ id (UUID, PK)            │
│ name (String)            │    │ name (String)            │
│ slug (String, Unique)    │    │ code (String, Unique)    │
│ description (Text)       │    │ description (Text)       │
│ email, phone, address    │    │ permissions (ARRAY)      │
│ is_active (Boolean)      │    │ is_system (Boolean)      │
│ settings (JSONB)         │    └──────────────────────────┘
└──────────────────────────┘
```

### Real Estate Modülü

```
┌─────────────────────────────────────────────────────────────────┐
│                           ASSET                                  │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ organization_id (FK → Organization) - Tenant isolation          │
│ name (String)                                                   │
│ code (String) - Unique within org (SITE-001, BLK-A, UNIT-101)   │
│ description (Text)                                              │
│ asset_type (Enum: site, block, floor, unit, common, meter)      │
│ parent_id (FK → Asset, Self-referencing) - Hiyerarşi            │
│ address, latitude, longitude                                    │
│ area_sqm (Decimal)                                              │
│ floor_number (Integer)                                          │
│ status (Enum: active, inactive, under_construction, maintenance)│
│ metadata (JSONB)                                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                           LEASE                                  │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ organization_id (FK)                                            │
│ asset_id (FK → Asset)                                           │
│ tenant_name, tenant_email, tenant_phone, tenant_id_number       │
│ contract_number (String, Unique)                                │
│ start_date, end_date (Date)                                     │
│ monthly_rent, deposit_amount (Decimal)                          │
│ currency (String, default: TRY)                                 │
│ status (Enum: draft, active, expired, terminated, pending)      │
│ signed_at, terminated_at (DateTime)                             │
│ notes (Text)                                                    │
└─────────────────────────────────────────────────────────────────┘
```

### IoT Modülü

```
┌─────────────────────────────────────────────────────────────────┐
│                          GATEWAY                                 │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ organization_id (FK)                                            │
│ name (String)                                                   │
│ serial_number (String, Unique within org)                       │
│ mac_address (String)                                            │
│ asset_id (FK → Asset) - Kurulu olduğu lokasyon                  │
│ mqtt_client_id (String, Unique)                                 │
│ ip_address (String)                                             │
│ firmware_version, hardware_version (String)                     │
│ status (Enum: online, offline, error, updating, provisioning)   │
│ last_seen_at (DateTime)                                         │
│ config (JSONB)                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          DEVICE                                  │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ organization_id (FK)                                            │
│ name (String)                                                   │
│ device_id (String, Unique within org) - MAC/Serial              │
│ device_type (Enum: smart_plug, energy_meter, water_meter, etc.) │
│ asset_id (FK → Asset) - Kurulu olduğu lokasyon                  │
│ gateway_id (FK → Gateway, Nullable)                             │
│ manufacturer, model, firmware_version (String)                  │
│ status (Enum: online, offline, error, maintenance, provisioning)│
│ last_seen_at (DateTime)                                         │
│ config, metadata (JSONB)                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ 1:N
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TELEMETRY_DATA (TimescaleDB Hypertable)      │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ timestamp (DateTime, Hypertable dimension)                      │
│ device_id (FK → Device)                                         │
│ metric_name (String: voltage, current, power, temperature, etc.)│
│ value (Decimal)                                                 │
│ unit (String: V, A, W, kWh, °C, %)                              │
│ quality (Integer: 0-100)                                        │
│ metadata (JSONB)                                                │
└─────────────────────────────────────────────────────────────────┘
```

### Billing Modülü

```
┌─────────────────────────────────────────────────────────────────┐
│                          WALLET                                  │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ organization_id (FK, Unique with currency)                      │
│ balance (Decimal)                                               │
│ currency (String, default: TRY)                                 │
│ is_active (Boolean)                                             │
│ credit_limit (Decimal, Nullable)                                │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         │ 1:N                          │ 1:N
         ▼                              ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│     TRANSACTION      │    │           INVOICE                │
├──────────────────────┤    ├──────────────────────────────────┤
│ id (UUID, PK)        │    │ id (UUID, PK)                    │
│ wallet_id (FK)       │    │ organization_id (FK)             │
│ transaction_type     │    │ invoice_number (String, Unique)  │
│ amount (Decimal)     │    │ issue_date, due_date (Date)      │
│ balance_after        │    │ subtotal, tax, discount, total   │
│ status               │    │ currency (String)                │
│ reference (String)   │    │ status (Enum)                    │
│ description (Text)   │    │ paid_at, paid_amount             │
│ invoice_id (FK)      │    │ period_start, period_end         │
│ metadata (JSONB)     │    │ line_items (JSONB)               │
└──────────────────────┘    │ notes (Text)                     │
                            └──────────────────────────────────┘
```

### Notification Modülü

```
┌─────────────────────────────────────────────────────────────────┐
│                       NOTIFICATION                               │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ user_id (FK → User)                                             │
│ organization_id (FK, Nullable)                                  │
│ type (Enum: critical, actionable, info, system, warning, success)│
│ priority (Enum: low, medium, high, urgent)                      │
│ title (String)                                                  │
│ message (Text)                                                  │
│ data (JSONB) - Action buttons, deep links                       │
│ is_read (Boolean)                                               │
│ read_at (DateTime)                                              │
│ channels_sent (JSONB) - ['in_app', 'push', 'telegram']          │
│ source_type, source_id - İlgili kaynak                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      USER_FCM_TOKEN                              │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ user_id (FK → User)                                             │
│ token (String, Unique) - FCM token                              │
│ device_type (String: web, android, ios)                         │
│ device_name (String)                                            │
│ is_active (Boolean)                                             │
│ last_used_at (DateTime)                                         │
│ failed_count (Integer)                                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                  NOTIFICATION_PREFERENCE                         │
├─────────────────────────────────────────────────────────────────┤
│ id (UUID, PK)                                                   │
│ user_id (FK → User, Unique)                                     │
│ push_enabled, telegram_enabled, email_enabled (Boolean)         │
│ type_preferences (JSONB)                                        │
│ quiet_hours_enabled (Boolean)                                   │
│ quiet_hours_start, quiet_hours_end (String: HH:MM)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Rol ve Yetki Sistemi

### Mevcut Roller (roles tablosu)

| Kod | İsim | Açıklama | Yetkiler |
|-----|------|----------|----------|
| `super_admin` | Super Admin | Tam sistem yetkisi | `["*"]` |
| `org_admin` | Organization Admin | Organizasyon yönetimi | `["*"]` (org scope) |
| `manager` | Manager | Departman yönetimi | TBD |
| `operator` | Operator | Cihaz kontrolü | TBD |
| `viewer` | Viewer | Salt okunur | TBD |

### ⚠️ ÖNERİLEN ROL YAPISI

Mevcut yapıda `org_admin` rolü yeni kullanıcılara atanıyor. Önerilen best-practice yapı:

```python
# Önerilen Rol Hiyerarşisi
ROLES = {
    "super_admin": {
        "name": "Super Admin",
        "description": "Tam sistem yetkisi - Tüm organizasyonları yönetir",
        "permissions": ["*"],
        "scope": "system"
    },
    "admin": {
        "name": "Admin",
        "description": "Organizasyon yönetimi - Kendi organizasyonunda tam yetki",
        "permissions": [
            "org:*",
            "user:*",
            "asset:*",
            "device:*",
            "billing:*",
            "notification:*"
        ],
        "scope": "organization"
    },
    "property_manager": {
        "name": "Property Manager",
        "description": "Gayrimenkul yönetimi",
        "permissions": [
            "asset:read", "asset:write",
            "lease:*",
            "billing:invoice:read"
        ],
        "scope": "organization"
    },
    "operator": {
        "name": "Operator",
        "description": "Cihaz kontrolü ve telemetri",
        "permissions": [
            "device:read", "device:control",
            "gateway:read",
            "telemetry:read"
        ],
        "scope": "organization"
    },
    "agent": {
        "name": "Agent",
        "description": "Kiracı bulma ve sözleşme yönetimi",
        "permissions": [
            "asset:read",
            "lease:read", "lease:write",
            "tenant:*"
        ],
        "scope": "organization"
    },
    "user": {
        "name": "User",
        "description": "Salt okunur erişim",
        "permissions": [
            "asset:read",
            "device:read",
            "telemetry:read",
            "notification:read"
        ],
        "scope": "organization"
    }
}
```

### Yetki Formatı (Action-Resource-Scope)

```
<module>:<resource>:<action>

Örnekler:
- real_estate:asset:read
- real_estate:asset:write
- real_estate:lease:manage
- iot:device:control
- iot:telemetry:read
- billing:invoice:read
- billing:wallet:manage
- notification:*
```

---

## 📡 Modüller ve Endpoint'ler

### 1. Auth Modülü (`/api/v1/auth`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/me` | Kullanıcı profili | ✅ |
| `PATCH` | `/me` | Profil güncelle | ✅ |
| `POST` | `/sync` | Auth0 senkronizasyonu | ❌ |

### 2. Dashboard Modülü (`/api/v1/dashboard`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/summary` | Genel özet (cihaz, enerji, cüzdan) | ✅ |
| `GET` | `/savings/summary` | Tasarruf özeti | ✅ |

### 3. Notifications Modülü (`/api/v1/notifications`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/` | Bildirim listesi | ✅ |
| `PATCH` | `/read` | Bildirimleri okundu işaretle | ✅ |
| `PATCH` | `/read-all` | Tümünü okundu işaretle | ✅ |
| `GET` | `/unread-count` | Okunmamış sayısı | ✅ |
| `POST` | `/fcm-token` | FCM token kaydet | ✅ |
| `GET` | `/preferences` | Bildirim tercihleri | ✅ |
| `PATCH` | `/preferences` | Tercihleri güncelle | ✅ |
| `GET` | `/telegram/link` | Telegram deep link | ✅ |

### 4. IoT Modülü (`/api/v1/iot`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/gateways` | Gateway listesi (paginated) | ✅ |
| `GET` | `/gateways/{id}` | Gateway detay + cihazlar | ✅ |
| `POST` | `/gateways` | Gateway oluştur | ✅ |
| `PATCH` | `/gateways/{id}` | Gateway güncelle | ✅ |
| `DELETE` | `/gateways/{id}` | Gateway sil | ✅ |
| `GET` | `/devices` | Cihaz listesi | ✅ |
| `GET` | `/devices/{id}` | Cihaz detay | ✅ |
| `POST` | `/devices` | Cihaz oluştur | ✅ |
| `PATCH` | `/devices/{id}` | Cihaz güncelle | ✅ |
| `DELETE` | `/devices/{id}` | Cihaz sil | ✅ |
| `POST` | `/telemetry` | Tek telemetri kaydı | ✅ |
| `POST` | `/telemetry/batch` | Toplu telemetri (max 1000) | ✅ |
| `GET` | `/telemetry/query` | Telemetri sorgula | ✅ |
| `GET` | `/telemetry/latest/{device_id}` | Son telemetri | ✅ |
| `GET` | `/telemetry/aggregate` | Aggregated veri | ✅ |

### 5. Real Estate Modülü (`/api/v1/real-estate`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/assets` | Varlık listesi | ✅ |
| `GET` | `/assets/hierarchy` | Hiyerarşi ağacı | ✅ |
| `GET` | `/assets/{id}` | Varlık detay | ✅ |
| `POST` | `/assets` | Varlık oluştur | ✅ |
| `PATCH` | `/assets/{id}` | Varlık güncelle | ✅ |
| `DELETE` | `/assets/{id}` | Varlık sil | ✅ |
| `GET` | `/leases` | Kira sözleşmeleri | ✅ |
| `GET` | `/leases/{id}` | Sözleşme detay | ✅ |
| `POST` | `/leases` | Sözleşme oluştur | ✅ |
| `PATCH` | `/leases/{id}` | Sözleşme güncelle | ✅ |
| `DELETE` | `/leases/{id}` | Sözleşme sil | ✅ |

### 6. Billing Modülü (`/api/v1/billing`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/wallets` | Cüzdan listesi | ✅ |
| `GET` | `/wallets/{id}` | Cüzdan + işlemler | ✅ |
| `POST` | `/wallets` | Cüzdan oluştur | ✅ |
| `PATCH` | `/wallets/{id}` | Cüzdan güncelle | ✅ |
| `POST` | `/wallets/top-up` | Bakiye yükle | ✅ |
| `GET` | `/transactions` | İşlem listesi | ✅ |
| `GET` | `/transactions/{id}` | İşlem detay | ✅ |
| `GET` | `/invoices` | Fatura listesi | ✅ |
| `GET` | `/invoices/{id}` | Fatura + ödemeler | ✅ |
| `POST` | `/invoices` | Fatura oluştur | ✅ |
| `PATCH` | `/invoices/{id}` | Fatura güncelle | ✅ |
| `POST` | `/invoices/pay` | Fatura öde | ✅ |
| `POST` | `/invoices/{id}/cancel` | Fatura iptal | ✅ |

### 7. Integrations Modülü (`/api/v1/integrations`)

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/epias/prices` | Günlük elektrik fiyatları | ✅ |
| `GET` | `/epias/current-price` | Anlık fiyat | ✅ |
| `POST` | `/epias/calculate-cost` | Maliyet hesapla | ✅ |
| `GET` | `/weather/current` | Anlık hava durumu | ✅ |
| `GET` | `/weather/city/{name}` | Şehir bazlı hava | ✅ |
| `GET` | `/weather/forecast` | 5 günlük tahmin | ✅ |
| `GET` | `/health` | Entegrasyon durumu | ❌ |

---

## 📖 User Story'ler

### 🏢 Organizasyon Yönetimi

#### US-001: Yeni Kullanıcı Kaydı
```
GIVEN: Kullanıcı Auth0 ile giriş yapmış
WHEN: POST /api/v1/auth/sync çağrılır
THEN:
  - Yeni User kaydı oluşturulur
  - Varsayılan Organization oluşturulur
  - User, Organization'a org_admin rolüyle eklenir
  - Varsayılan Wallet oluşturulur
```

#### US-002: Profil Güncelleme
```
GIVEN: Kullanıcı giriş yapmış
WHEN: PATCH /api/v1/auth/me çağrılır
THEN: full_name, phone, telegram_username güncellenir
```

### 🏠 Gayrimenkul Yönetimi

#### US-010: Varlık Hiyerarşisi Oluşturma
```
GIVEN: Admin kullanıcı
WHEN: Sırasıyla Site → Block → Floor → Unit oluşturulur
THEN:
  - Her varlık parent_id ile bağlanır
  - Hiyerarşi /assets/hierarchy ile görüntülenebilir
```

#### US-011: Kira Sözleşmesi
```
GIVEN: Unit (daire) mevcut
WHEN: POST /api/v1/real-estate/leases çağrılır
THEN:
  - Lease kaydı oluşturulur
  - Kiracı bilgileri kaydedilir
  - Başlangıç/bitiş tarihleri belirlenir
```

### 📡 IoT Yönetimi

#### US-020: Gateway Kurulumu
```
GIVEN: Site/Block mevcut
WHEN: POST /api/v1/iot/gateways çağrılır
THEN:
  - Gateway kaydı oluşturulur
  - asset_id ile lokasyona bağlanır
  - MQTT client_id atanır
```

#### US-021: Cihaz Ekleme
```
GIVEN: Gateway mevcut
WHEN: POST /api/v1/iot/devices çağrılır
THEN:
  - Device kaydı oluşturulur
  - Gateway'e bağlanır
  - Asset'e bağlanır (ör: Unit)
```

#### US-022: Telemetri Verisi Kaydetme
```
GIVEN: Device mevcut ve online
WHEN: POST /api/v1/iot/telemetry/batch çağrılır
THEN:
  - Veriler TimescaleDB'ye yazılır
  - Batch insert ile performans optimize
```

#### US-023: Telemetri Sorgulama
```
GIVEN: Telemetri verisi mevcut
WHEN: GET /api/v1/iot/telemetry/query çağrılır
THEN:
  - Zaman aralığına göre veriler döner
  - Opsiyonel metric_name filtresi
```

### 💰 Faturalama

#### US-030: Cüzdan Bakiye Yükleme
```
GIVEN: Wallet mevcut
WHEN: POST /api/v1/billing/wallets/top-up çağrılır
THEN:
  - Transaction (CREDIT) oluşturulur
  - Wallet balance güncellenir
```

#### US-031: Fatura Ödeme
```
GIVEN: Invoice (PENDING) ve yeterli bakiye
WHEN: POST /api/v1/billing/invoices/pay çağrılır
THEN:
  - Transaction (DEBIT) oluşturulur
  - Invoice status → PAID
  - Wallet balance düşer
```

### 🔔 Bildirimler

#### US-040: Push Notification Alma
```
GIVEN: Kullanıcı FCM token kaydetmiş
WHEN: Kritik alarm tetiklenir
THEN:
  - Notification DB'ye kaydedilir
  - FCM ile push gönderilir
  - Telegram'a da gönderilir (CRITICAL ise)
```

#### US-041: Bildirim Tercihleri
```
GIVEN: Kullanıcı giriş yapmış
WHEN: PATCH /api/v1/notifications/preferences çağrılır
THEN:
  - push_enabled, telegram_enabled güncellenir
  - Sessiz saatler ayarlanabilir
```

### ⚡ Enerji Yönetimi

#### US-050: Anlık Elektrik Fiyatı
```
GIVEN: EPİAŞ entegrasyonu aktif
WHEN: GET /api/v1/integrations/epias/current-price çağrılır
THEN:
  - Anlık PTF fiyatı döner (TRY/MWh)
  - kWh başına fiyat hesaplanır
```

#### US-051: Maliyet Hesaplama
```
GIVEN: Tüketim verisi mevcut
WHEN: POST /api/v1/integrations/epias/calculate-cost çağrılır
THEN:
  - Anlık fiyat × tüketim = maliyet
```

---

## 🔄 Sistem Akışı

### Authentication Flow

```
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────┐
│ Frontend│────▶│  Auth0  │────▶│   Backend   │────▶│ Postgres │
└─────────┘     └─────────┘     └─────────────┘     └──────────┘
     │               │                 │                  │
     │  1. Login     │                 │                  │
     │──────────────▶│                 │                  │
     │               │                 │                  │
     │  2. JWT Token │                 │                  │
     │◀──────────────│                 │                  │
     │               │                 │                  │
     │  3. POST /auth/sync             │                  │
     │────────────────────────────────▶│                  │
     │               │                 │  4. Upsert User  │
     │               │                 │─────────────────▶│
     │               │                 │                  │
     │  5. User + Org Response         │                  │
     │◀────────────────────────────────│                  │
     │               │                 │                  │
     │  6. GET /auth/me (with JWT)     │                  │
     │────────────────────────────────▶│                  │
     │               │                 │  7. Verify JWT   │
     │               │                 │  (Auth0 JWKS)    │
     │               │                 │  8. Get User     │
     │               │                 │─────────────────▶│
     │  9. Profile Response            │                  │
     │◀────────────────────────────────│                  │
```

### IoT Data Flow

```
┌──────────┐     ┌─────────┐     ┌─────────────┐     ┌────────────┐
│  Device  │────▶│ Gateway │────▶│    MQTT     │────▶│  Backend   │
└──────────┘     └─────────┘     └─────────────┘     └────────────┘
     │               │                 │                   │
     │  Sensor Data  │                 │                   │
     │──────────────▶│                 │                   │
     │               │  MQTT Publish   │                   │
     │               │────────────────▶│                   │
     │               │                 │  Subscribe        │
     │               │                 │──────────────────▶│
     │               │                 │                   │
     │               │                 │                   ▼
     │               │                 │           ┌──────────────┐
     │               │                 │           │ TimescaleDB  │
     │               │                 │           │ (Hypertable) │
     │               │                 │           └──────────────┘
```

### Notification Flow

```
┌─────────────┐     ┌─────────────┐     ┌─────────┐
│   Trigger   │────▶│   Backend   │────▶│   FCM   │────▶ Push
│ (Alarm/Event)     │             │     └─────────┘
└─────────────┘     │             │     ┌─────────┐
                    │             │────▶│Telegram │────▶ Message
                    │             │     └─────────┘
                    │             │     ┌─────────┐
                    │             │────▶│Postgres │────▶ In-App
                    └─────────────┘     └─────────┘
```

---

## 🚀 Sonraki Adımlar

### Yapılması Gerekenler

1. **Rol Sistemi İyileştirmesi**
   - `org_admin` → `admin` olarak yeniden adlandır
   - Yeni roller ekle: `property_manager`, `agent`
   - Permission mapping implement et

2. **Asset Kategorisi**
   - Asset tablosuna `category` alanı ekle
   - Enum: `residential`, `commercial`, `hotel`, `industrial`, `retail`

3. **Yetki Kontrolü**
   - Permission-based access control implement et
   - Endpoint bazlı yetki kontrolü

4. **Database Migration**
   - Yeni roller için seed data
   - Asset category migration

---

*Son güncelleme: 2026-01-04*
