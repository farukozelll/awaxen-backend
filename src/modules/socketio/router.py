"""
Simple Socket.IO Compatibility Layer
Redirects Socket.IO requests to SSE
"""
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

@router.get("/socket.io/")
async def socket_io_compatibility():
    """Socket.IO compatibility endpoint - returns SSE info"""
    return PlainTextResponse(
        content='{"code":0,"message":"Socket.IO not available, use SSE instead","endpoint":"/api/v1/sse/subscribe"}\n',
        media_type="application/json"
    )

# Import and include WebSocket endpoint
from .websocket import websocket_endpoint

router.add_websocket_route("/socket.io/", websocket_endpoint)
