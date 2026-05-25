"""
WebSocket endpoint for real-time courtroom queue updates.

Clients connect to /api/ws/courtroom/{room_id} and receive a
{"type": "queue_update", "room_id": <id>} signal whenever that
room's queue changes.  They then re-fetch the queue via HTTP to
get the latest data (no full payload pushed over WS — keeps this
simple and avoids duplicating sealed-case masking logic).
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from db.models import User
from api.dependencies import get_optional_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ws", tags=["websocket"])


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[int, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, room_id: int) -> None:
        await ws.accept()
        self._rooms.setdefault(room_id, set()).add(ws)
        logger.info("ws connect room=%s connections=%s", room_id, len(self._rooms[room_id]))

    def disconnect(self, ws: WebSocket, room_id: int) -> None:
        room = self._rooms.get(room_id, set())
        room.discard(ws)
        if not room:
            self._rooms.pop(room_id, None)

    async def broadcast(self, room_id: int, payload: dict) -> None:
        sockets = list(self._rooms.get(room_id, set()))
        if not sockets:
            return
        text = json.dumps(payload)
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, room_id)


manager = ConnectionManager()


@router.websocket("/courtroom/{room_id}")
async def queue_socket(
    ws: WebSocket,
    room_id: int,
    current_user: User | None = Depends(get_optional_user),
) -> None:
    if current_user is None:
        await ws.close(code=4001, reason="Authentication required")
        return
    await manager.connect(ws, room_id)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws, room_id)
