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
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
    GatewayCreate,
    GatewayResponse,
    GatewayUpdate,
    GatewayWithDevices,
    TelemetryAggregation,
    TelemetryDataBatch,
    TelemetryDataCreate,
    TelemetryDataResponse,
    TelemetryQuery,
)

router = APIRouter(prefix="/iot", tags=["IoT"])


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
    pageSize: int = Query(default=20, ge=1, le=100, alias="pageSize", description="Sayfa başına kayıt"),
    sortBy: str = Query(default="created_at", alias="sortBy", description="Sıralama alanı"),
    sortOrder: str = Query(default="desc", alias="sortOrder", description="Sıralama yönü (asc/desc)"),
    status: GatewayStatus | None = None,
    asset_id: uuid.UUID | None = None,
) -> PaginatedGatewayResponse:
    """Gateway'leri sayfalanmış olarak listeler."""
    gateways = await service.list_gateways(status=status, asset_id=asset_id)
    
    # Manual pagination
    total = len(gateways)
    start = (page - 1) * pageSize
    end = start + pageSize
    paginated = gateways[start:end]
    
    return PaginatedGatewayResponse(
        items=[GatewayResponse.model_validate(g) for g in paginated],
        total=total,
        page=page,
        page_size=pageSize,
        has_more=end < total,
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

@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(
    service: IoTServiceDep,
    asset_id: uuid.UUID | None = None,
    gateway_id: uuid.UUID | None = None,
    device_type: DeviceType | None = None,
    status: DeviceStatus | None = None,
) -> list[DeviceResponse]:
    """List devices with optional filters."""
    devices = await service.list_devices(
        asset_id=asset_id,
        gateway_id=gateway_id,
        device_type=device_type.value if device_type else None,
        status=status,
    )
    return [DeviceResponse.model_validate(d) for d in devices]


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
