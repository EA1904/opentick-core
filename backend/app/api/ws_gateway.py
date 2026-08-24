from typing import List, Dict
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import asyncio

router = APIRouter(tags=["websocket"])

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        # Tracks active subscriptions per client: {websocket: [symbols]}
        self.subscriptions: Dict[WebSocket, List[str]] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.subscriptions[websocket] = []

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        if websocket in self.subscriptions:
            del self.subscriptions[websocket]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def subscribe(self, websocket: WebSocket, symbol: str):
        if websocket in self.subscriptions:
            if symbol not in self.subscriptions[websocket]:
                self.subscriptions[websocket].append(symbol)

    async def unsubscribe(self, websocket: WebSocket, symbol: str):
        if websocket in self.subscriptions:
            if symbol in self.subscriptions[websocket]:
                self.subscriptions[websocket].remove(symbol)

    async def broadcast(self, message: str, symbol: str):
        # Broadcast message only to connections subscribed to this symbol
        payload = json.dumps({"symbol": symbol, "data": message})
        for connection in self.active_connections:
            if symbol in self.subscriptions.get(connection, []):
                try:
                    await connection.send_text(payload)
                except Exception:
                    # Stale connection clean up will happen on disconnect
                    pass

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                action = message.get("action")
                symbol = message.get("symbol", "").upper()
                
                if action == "subscribe" and symbol:
                    await manager.subscribe(websocket, symbol)
                    await websocket.send_text(json.dumps({"status": "subscribed", "symbol": symbol}))
                elif action == "unsubscribe" and symbol:
                    await manager.unsubscribe(websocket, symbol)
                    await websocket.send_text(json.dumps({"status": "unsubscribed", "symbol": symbol}))
                else:
                    await websocket.send_text(json.dumps({"error": "Unknown action or missing symbol"}))
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
