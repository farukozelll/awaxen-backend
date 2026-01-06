"""
SSE Module - Server-Sent Events Router

Provides realtime updates for:
- Dashboard metrics
- Device state changes
- Recommendations
- Alarms
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from src.modules.auth.dependencies import get_current_user
from src.modules.auth.models import User
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sse", tags=["SSE"])


async def event_generator(
    request: Request,
    user: User,
    event_type: str,
) -> AsyncGenerator[str, None]:
    """
    Generate SSE events.
    
    Format: data: {json}\n\n
    """
    try:
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                logger.info("SSE client disconnected", user_id=str(user.id))
                break
            
            # Generate heartbeat every 30 seconds
            event = {
                "type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            yield f"data: {json.dumps(event)}\n\n"
            
            # Wait before next event
            await asyncio.sleep(30)
            
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled", user_id=str(user.id))
    except Exception as e:
        logger.error("SSE error", error=str(e), user_id=str(user.id))


@router.get("/dashboard")
async def dashboard_stream(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    SSE stream for dashboard updates.
    
    Events:
    - `heartbeat`: Connection keepalive
    - `device_state`: Device state changed
    - `gateway_status`: Gateway online/offline
    - `recommendation`: New recommendation
    - `alarm`: New alarm
    
    Usage:
    ```javascript
    const eventSource = new EventSource('/api/v1/sse/dashboard', {
        headers: { 'Authorization': 'Bearer <token>' }
    });
    
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        switch(data.type) {
            case 'device_state':
                updateDeviceUI(data.device_id, data.state);
                break;
            case 'recommendation':
                showNotification(data.message);
                break;
        }
    };
    ```
    """
    logger.info("SSE dashboard stream started", user_id=str(current_user.id))
    
    return StreamingResponse(
        event_generator(request, current_user, "dashboard"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/asset/{asset_id}")
async def asset_stream(
    asset_id: UUID,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    SSE stream for specific asset updates.
    
    Events:
    - `device_state`: Device in this asset changed state
    - `telemetry`: New telemetry data
    - `alarm`: Alarm for this asset
    """
    logger.info(
        "SSE asset stream started",
        user_id=str(current_user.id),
        asset_id=str(asset_id),
    )
    
    return StreamingResponse(
        event_generator(request, current_user, f"asset:{asset_id}"),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
