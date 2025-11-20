"""
WebSocket endpoint for real-time dashboard updates.

Pushes meta-cognitive state updates to connected clients every second.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Set
import asyncio
import json
from datetime import datetime
from kloros_bridge import bridge

router = APIRouter(tags=["websocket"])

# Track active WebSocket connections
active_connections: Set[WebSocket] = set()


class ConnectionManager:
    """Manages WebSocket connections and broadcasts."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[websocket] Client connected. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[websocket] Client disconnected. Total: {len(self.active_connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"[websocket] Error sending to client: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


@router.websocket("/ws/live")
async def websocket_live_updates(websocket: WebSocket):
    """
    WebSocket endpoint for live meta-cognitive state updates.
    
    Pushes updates every 1 second to connected clients.
    
    Message format:
    {
        "type": "update",
        "timestamp": "2025-11-01T21:30:45Z",
        "data": {
            "meta_state": {...},
            "kloros_running": true
        }
    }
    """
    await manager.connect(websocket)
    
    try:
        while True:
            # Get current meta state
            state = bridge.get_meta_state()
            kloros_running = bridge.is_kloros_running()
            
            if state:
                # Prepare update message with full enhanced state
                message = {
                    "type": "update",
                    "timestamp": datetime.now().isoformat(),
                    "data": {
                        "meta_state": state.model_dump(mode='json'),
                        "kloros_running": kloros_running
                    }
                }
            else:
                # Send fallback message when KLoROS is unavailable
                message = {
                    "type": "update",
                    "timestamp": datetime.now().isoformat(),
                    "data": {
                        "meta_state": None,
                        "kloros_running": kloros_running,
                        "error": "KLoROS meta-state unavailable"
                    }
                }
            
            # Send update to this client
            await websocket.send_json(message)
            
            # Wait 1 second before next update
            await asyncio.sleep(1.0)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("[websocket] Client disconnected gracefully")
    except Exception as e:
        print(f"[websocket] Error in WebSocket connection: {e}")
        manager.disconnect(websocket)


async def broadcast_task():
    """
    Background task to broadcast updates to all connected clients.
    
    Alternative approach: instead of each WebSocket sending individually,
    have a single broadcast task. Not used currently, but available.
    """
    while True:
        try:
            state = bridge.get_meta_state()
            if state and manager.active_connections:
                message = {
                    "type": "update",
                    "timestamp": datetime.now().isoformat(),
                    "data": state.model_dump()
                }
                await manager.broadcast(message)
        except Exception as e:
            print(f"[websocket] Broadcast error: {e}")
        
        await asyncio.sleep(1.0)
