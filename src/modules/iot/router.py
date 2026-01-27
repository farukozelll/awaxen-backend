"""
IoT Module - API Router

IoT cihaz ve gateway yönetimi endpoint'leri.

Endpoint'ler:
- GET/POST/PATCH/DELETE /api/v1/iot/gateways - Gateway CRUD
- GET/POST/PATCH/DELETE /api/v1/iot/devices - Cihaz CRUD
- POST /api/v1/iot/telemetry - Telemetri verisi kaydet
- GET /api/v1/iot/telemetry/query - Telemetri sorgula
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from src.modules.iot.dependencies import IoTServiceDep, TelemetryServiceDep
from src.modules.iot.models import DeviceStatus, DeviceType, GatewayStatus
from src.modules.iot.schemas import (
    BulkDeviceSetupRequest,
    BulkDeviceSetupResponse,
    DeviceControlRequest,
    DeviceControlResponse,
    DeviceCreate,
    DeviceDiscoveryRequest,
    DeviceDiscoveryResponse,
    DeviceResponse,
    DeviceSetupRequest,
    DeviceSetupResponse,
    DeviceUpdate,
    GatewayCreate,
    GatewayPairingRequest,
    GatewayPairingResponse,
    GatewayResponse,
    GatewayUpdate,
    GatewayWithDevices,
    GeneratePairingCodeRequest,
    GeneratePairingCodeResponse,
    TelemetryAggregation,
    TelemetryDataBatch,
    TelemetryDataCreate,
    TelemetryDataResponse,
    TelemetryQuery,
)

router = APIRouter(prefix="/iot", tags=["21. 📡 IoT"])


# ============== Gateways ==============

class PaginatedGatewayResponse(BaseModel):
    """Paginated gateway response."""
    items: list[GatewayResponse] = Field(default_factory=list, description="Gateway listesi")
    total: int = Field(default=0, description="Toplam kayıt sayısı")
    page: int = Field(default=1, description="Mevcut sayfa")
    page_size: int = Field(default=20, description="Sayfa başına kayıt")
    has_more: bool = Field(default=False, description="Daha fazla kayıt var mı")


@router.get(
    "/gateways",
    response_model=PaginatedGatewayResponse,
    summary="Gateway Listesi",
    description="""
Gateway'leri sayfalanmış olarak listeler.

## 📋 Parametreler

| Parametre | Tip | Default | Açıklama |
|-----------|-----|---------|----------|
| `page` | int | 1 | Sayfa numarası |
| `pageSize` | int | 20 | Sayfa başına kayıt (max: 100) |
| `sortBy` | string | created_at | Sıralama alanı |
| `sortOrder` | string | desc | Sıralama yönü (asc/desc) |
| `status` | string | - | Durum filtresi (online/offline/error) |

## 📝 Örnek Kullanım

```bash
curl -X GET "https://api.awaxen.com/api/v1/iot/gateways?page=1&pageSize=10" \\
  -H "Authorization: Bearer <jwt_token>"
```

## 📤 Örnek Yanıt

```json
{
  "items": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "Ana Gateway",
      "serial_number": "SHELLY-GW-001",
      "status": "online",
      "ip_address": "192.168.1.100",
      "last_seen": "2024-01-04T12:00:00Z"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 10,
  "has_more": false
}
```
    """,
    responses={
        200: {
            "description": "Gateway listesi başarıyla döndürüldü",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": "550e8400-e29b-41d4-a716-446655440000",
                                "name": "Ana Gateway",
                                "serial_number": "SHELLY-GW-001",
                                "status": "online",
                                "ip_address": "192.168.1.100"
                            }
                        ],
                        "total": 5,
                        "page": 1,
                        "page_size": 10,
                        "has_more": False
                    }
                }
            }
        },
        401: {"description": "Yetkisiz erişim"},
    },
)
async def list_gateways(
    service: IoTServiceDep,
    page: int = Query(default=1, ge=1, description="Sayfa numarası"),
    pageSize: int = Query(default=20, ge=1, le=100, alias="pageSize", description="Sayfa başına kayıt"),  # noqa: N803
    sortBy: str = Query(default="created_at", alias="sortBy", description="Sıralama alanı"),  # noqa: N803
    sortOrder: str = Query(default="desc", alias="sortOrder", description="Sıralama yönü (asc/desc)"),  # noqa: N803
    status: GatewayStatus | None = None,
    asset_id: uuid.UUID | None = None,
) -> PaginatedGatewayResponse:
    """Gateway'leri sayfalanmış olarak listeler."""
    # DB-level pagination (Memory Bomb fix!)
    skip = (page - 1) * pageSize
    gateways, total = await service.list_gateways(
        status=status,
        asset_id=asset_id,
        skip=skip,
        limit=pageSize,
    )
    
    return PaginatedGatewayResponse(
        items=[GatewayResponse.model_validate(g) for g in gateways],
        total=total,
        page=page,
        page_size=pageSize,
        has_more=(skip + pageSize) < total,
    )


@router.get("/gateways/{gateway_id}", response_model=GatewayWithDevices)
async def get_gateway(
    gateway_id: uuid.UUID,
    service: IoTServiceDep,
) -> GatewayWithDevices:
    """Get gateway by ID with devices."""
    from src.core.exceptions import NotFoundError
    
    gateway = await service.get_gateway_by_id(gateway_id)
    if not gateway:
        raise NotFoundError("Gateway", gateway_id)
    return GatewayWithDevices.model_validate(gateway)


@router.post(
    "/gateways",
    response_model=GatewayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_gateway(
    data: GatewayCreate,
    service: IoTServiceDep,
) -> GatewayResponse:
    """Create a new gateway."""
    gateway = await service.create_gateway(data)
    return GatewayResponse.model_validate(gateway)


@router.patch("/gateways/{gateway_id}", response_model=GatewayResponse)
async def update_gateway(
    gateway_id: uuid.UUID,
    data: GatewayUpdate,
    service: IoTServiceDep,
) -> GatewayResponse:
    """Update a gateway."""
    gateway = await service.update_gateway(gateway_id, data)
    return GatewayResponse.model_validate(gateway)


@router.delete("/gateways/{gateway_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gateway(
    gateway_id: uuid.UUID,
    service: IoTServiceDep,
) -> None:
    """Delete a gateway."""
    await service.delete_gateway(gateway_id)


# ============== Devices ==============

class PaginatedDeviceResponse(BaseModel):
    """Paginated device response."""
    items: list[DeviceResponse] = Field(default_factory=list, description="Device listesi")
    total: int = Field(default=0, description="Toplam kayıt sayısı")
    page: int = Field(default=1, description="Mevcut sayfa")
    page_size: int = Field(default=20, description="Sayfa başına kayıt")
    has_more: bool = Field(default=False, description="Daha fazla kayıt var mı")


@router.get("/devices", response_model=PaginatedDeviceResponse)
async def list_devices(
    service: IoTServiceDep,
    page: int = Query(default=1, ge=1, description="Sayfa numarası"),
    pageSize: int = Query(default=20, ge=1, le=100, alias="pageSize", description="Sayfa başına kayıt"),  # noqa: N803
    asset_id: uuid.UUID | None = None,
    gateway_id: uuid.UUID | None = None,
    device_type: DeviceType | None = None,
    status: DeviceStatus | None = None,
) -> PaginatedDeviceResponse:
    """List devices with optional filters and DB-level pagination."""
    # DB-level pagination (Memory Bomb fix!)
    skip = (page - 1) * pageSize
    devices, total = await service.list_devices(
        asset_id=asset_id,
        gateway_id=gateway_id,
        device_type=device_type.value if device_type else None,
        status=status,
        skip=skip,
        limit=pageSize,
    )
    
    return PaginatedDeviceResponse(
        items=[DeviceResponse.model_validate(d) for d in devices],
        total=total,
        page=page,
        page_size=pageSize,
        has_more=(skip + pageSize) < total,
    )


@router.get("/devices/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: uuid.UUID,
    service: IoTServiceDep,
) -> DeviceResponse:
    """Get device by ID."""
    from src.core.exceptions import NotFoundError
    
    device = await service.get_device_by_id(device_id)
    if not device:
        raise NotFoundError("Device", device_id)
    return DeviceResponse.model_validate(device)


@router.post(
    "/devices",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_device(
    data: DeviceCreate,
    service: IoTServiceDep,
) -> DeviceResponse:
    """Create a new device."""
    device = await service.create_device(data)
    return DeviceResponse.model_validate(device)


@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: uuid.UUID,
    data: DeviceUpdate,
    service: IoTServiceDep,
) -> DeviceResponse:
    """Update a device."""
    device = await service.update_device(device_id, data)
    return DeviceResponse.model_validate(device)


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: uuid.UUID,
    service: IoTServiceDep,
) -> None:
    """Delete a device."""
    await service.delete_device(device_id)


# ============== Telemetry ==============

@router.post(
    "/telemetry",
    response_model=TelemetryDataResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_telemetry(
    data: TelemetryDataCreate,
    service: TelemetryServiceDep,
) -> TelemetryDataResponse:
    """Create a single telemetry reading."""
    telemetry = await service.insert_single(data)
    return TelemetryDataResponse.model_validate(telemetry)


@router.post(
    "/telemetry/batch",
    status_code=status.HTTP_201_CREATED,
)
async def create_telemetry_batch(
    data: TelemetryDataBatch,
    service: TelemetryServiceDep,
) -> dict[str, int]:
    """
    Create telemetry readings in batch.
    
    TRICK: Always use batch inserts for IoT data.
    This endpoint accepts up to 1000 readings at once.
    """
    count = await service.insert_batch(data)
    return {"inserted": count}


@router.get("/telemetry/query", response_model=list[TelemetryDataResponse])
async def query_telemetry(
    device_id: uuid.UUID,
    start_time: datetime,
    end_time: datetime,
    service: TelemetryServiceDep,
    metric_name: str | None = None,
    limit: int = Query(default=1000, le=10000),
) -> list[TelemetryDataResponse]:
    """Query telemetry data with time range."""
    query = TelemetryQuery(
        device_id=device_id,
        metric_name=metric_name,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )
    data = await service.query(query)
    return [TelemetryDataResponse.model_validate(d) for d in data]


@router.get("/telemetry/latest/{device_id}", response_model=TelemetryDataResponse | None)
async def get_latest_telemetry(
    device_id: uuid.UUID,
    service: TelemetryServiceDep,
    metric_name: str | None = None,
) -> TelemetryDataResponse | None:
    """Get latest telemetry reading for a device."""
    data = await service.get_latest(device_id, metric_name)
    if data:
        return TelemetryDataResponse.model_validate(data)
    return None


@router.get("/telemetry/aggregate", response_model=TelemetryAggregation | None)
async def aggregate_telemetry(
    device_id: uuid.UUID,
    metric_name: str,
    start_time: datetime,
    end_time: datetime,
    service: TelemetryServiceDep,
) -> TelemetryAggregation | None:
    """Get aggregated telemetry data (min, max, avg, sum, count)."""
    return await service.aggregate(device_id, metric_name, start_time, end_time)


# ============== Gateway Pairing ==============

@router.post(
    "/gateways/pairing-session",
    response_model=GeneratePairingCodeResponse,
    summary="Pairing Oturumu Başlat (Gateway)",
    description="""
**Gateway tarafından çağrılır.**

Gateway ilk açıldığında bu endpoint'i çağırarak pairing kodu alır.
Kod ekranda gösterilir ve kullanıcı bu kodu uygulamaya girer.

**Akış:**
1. Gateway açılır
2. Gateway bu endpoint'i çağırır → Kod alır
3. Kod ekranda gösterilir (örn: ABC123)
4. Kullanıcı kodu uygulamaya girer
5. Gateway asset'e bağlanır

**Örnek İstek:**
```json
{
  "serial_number": "SHELLY-GW-001",
  "mac_address": "AA:BB:CC:DD:EE:FF",
  "firmware_version": "1.0.0"
}
```
    """,
    status_code=status.HTTP_201_CREATED,
)
async def generate_pairing_code(
    request: GeneratePairingCodeRequest,
    service: IoTServiceDep,
) -> GeneratePairingCodeResponse:
    """Gateway için pairing kodu oluştur."""
    return await service.generate_pairing_code(request)


@router.post(
    "/devices/claim",
    response_model=GatewayPairingResponse,
    summary="Cihaz Sahiplen (User)",
    description="""
**Kullanıcı tarafından çağrılır.**

Kullanıcı gateway ekranında görünen kodu girer ve gateway'i asset'e bağlar.

**Akış:**
1. Kullanıcı kodu girer
2. Kod doğrulanır
3. Gateway asset'e bağlanır
4. Gateway status: provisioning → online

**Örnek İstek:**
```json
{
  "pairing_code": "ABC123",
  "asset_id": "550e8400-e29b-41d4-a716-446655440000"
}
```
    """,
)
async def verify_pairing_code(
    request: GatewayPairingRequest,
    service: IoTServiceDep,
) -> GatewayPairingResponse:
    """Pairing kodunu doğrula ve gateway'i asset'e bağla."""
    return await service.verify_pairing_code(request)


# ============== Device Discovery ==============

@router.post(
    "/gateways/{gateway_id}/discovery",
    response_model=DeviceDiscoveryResponse,
    summary="Cihaz Keşfi Sonuçları (Gateway)",
    description="""
**Gateway tarafından çağrılır.**

Gateway Home Assistant üzerinden cihazları keşfeder ve sonuçları bu endpoint'e gönderir.
Kullanıcı daha sonra bu cihazları kurulum ekranında görür.

**Akış:**
1. Gateway HA'dan cihazları keşfeder
2. Bu endpoint'e gönderir
3. Kullanıcı UI'da cihazları görür
4. Her cihaz için zone ve safety profile seçer

**Örnek İstek:**
```json
{
  "gateway_id": "550e8400-e29b-41d4-a716-446655440000",
  "devices": [
    {
      "external_id": "switch.salon_priz",
      "name": "Salon Priz",
      "device_type": "smart_plug",
      "manufacturer": "Shelly",
      "capabilities": ["switch", "power_meter"]
    }
  ]
}
```
    """,
)
async def submit_device_discovery(
    request: DeviceDiscoveryRequest,
    service: IoTServiceDep,
) -> DeviceDiscoveryResponse:
    """Gateway'den gelen cihaz keşif sonuçlarını kaydet."""
    return await service.submit_device_discovery(request)


@router.post(
    "/devices/{device_id}/configuration",
    response_model=DeviceSetupResponse,
    summary="Cihaz Yapılandırması (User)",
    description="""
**Kullanıcı tarafından çağrılır.**

Keşfedilen cihazı kurulum yapar.
Her cihaz için zone ve safety profile seçilir.

**Safety Profiles:**
- `critical` - Asla otomatik kontrol edilmez (tıbbi cihazlar, güvenlik)
- `high` - Sadece kullanıcı onayı ile kontrol
- `normal` - Otomatik kontrol edilebilir

**Örnek İstek:**
```json
{
  "gateway_id": "550e8400-e29b-41d4-a716-446655440000",
  "external_id": "switch.salon_priz",
  "name": "Salon Prizi",
  "zone_id": "550e8400-e29b-41d4-a716-446655440001",
  "safety_profile": "normal",
  "controllable": true
}
```
    """,
    status_code=status.HTTP_201_CREATED,
)
async def setup_device(
    request: DeviceSetupRequest,
    service: IoTServiceDep,
) -> DeviceSetupResponse:
    """Keşfedilen cihazı kurulum yap."""
    return await service.setup_device(request)


@router.post(
    "/devices/setup/bulk",
    response_model=BulkDeviceSetupResponse,
    summary="Toplu Cihaz Kurulumu (User)",
    description="""
**Kullanıcı tarafından çağrılır.**

Birden fazla cihazı tek seferde kurulum yapar.
Tüm cihazlar için zone ve safety profile seçilir.
    """,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_setup_devices(
    request: BulkDeviceSetupRequest,
    service: IoTServiceDep,
) -> BulkDeviceSetupResponse:
    """Birden fazla cihazı toplu kurulum yap."""
    return await service.bulk_setup_devices(request)


# ============== Device Control (Manuel Müdahale) ==============

@router.post(
    "/devices/control",
    response_model=DeviceControlResponse,
    summary="Manuel Cihaz Kontrolü",
    description="""
**🎮 MANUEL MÜDAHALE** - Kullanıcı tarafından tetiklenen cihaz kontrolü.

Bu endpoint kullanıcının doğrudan cihazı kontrol etmesi içindir.
Enerji tasarrufu otomasyonu için `/api/v1/energy/commands/dispatch` kullanın.

**Fark:**
| Endpoint | Kullanım | Tetikleyen |
|----------|----------|------------|
| `POST /iot/devices/control` | Manuel müdahale | Kullanıcı (UI'dan) |
| `POST /energy/commands/dispatch` | Otomasyon | Sistem (Recommendation) |

**Safety Profile Kontrolü:**
- `critical` cihazlar kontrol edilemez
- `high` cihazlar için onay gerekir
- `normal` cihazlar doğrudan kontrol edilebilir

**Örnek İstek:**
```json
{
  "device_id": "550e8400-e29b-41d4-a716-446655440000",
  "action": "turn_off",
  "parameters": null
}
```

**Actions:**
- `turn_on` - Cihazı aç
- `turn_off` - Cihazı kapat
- `toggle` - Durumu değiştir
- `set_temperature` - Sıcaklık ayarla (parameters: {"temperature": 22})
    """,
)
async def control_device(
    request: DeviceControlRequest,
    service: IoTServiceDep,
) -> DeviceControlResponse:
    """Cihazı kontrol et."""
    return await service.control_device(request)
