"""
Socket.IO Server Integration
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

class ConnectionManager:
    """WebSocket connection manager"""
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[str, str] = {}  # user_id -> connection_id
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        connection_id = f"{user_id}_{datetime.now().timestamp()}"
        self.active_connections[connection_id] = websocket
        self.user_connections[user_id] = connection_id
        logger.info(f"WebSocket connected: {connection_id}")
        return connection_id
    
    def disconnect(self, connection_id: str, user_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        logger.info(f"WebSocket disconnected: {connection_id}")
    
    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.user_connections:
            connection_id = self.user_connections[user_id]
            if connection_id in self.active_connections:
                websocket = self.active_connections[connection_id]
                await websocket.send_text(json.dumps(message))
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_text(json.dumps(message))

manager = ConnectionManager()

@router.websocket("/socket.io/")
async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections for Socket.IO compatibility"""
    # For now, just accept and send heartbeat
    await websocket.accept()
    
    try:
        while True:
            # Send heartbeat every 30 seconds
            await websocket.send_text(json.dumps({
                "type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }))
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
