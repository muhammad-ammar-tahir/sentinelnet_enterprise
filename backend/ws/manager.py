"""WebSocket Event Manager for SentinelNet Real-Time Telemetry & Remediation.

Maintains active authenticated WebSocket client connections,
handles targeted messaging, and dispatches real-time broadcast events:
- METRICS_UPDATED
- ANOMALY_DETECTED
- INCIDENT_CREATED
- TOPOLOGY_CHANGED
- RECOVERY_STARTED
- RECOVERY_COMPLETED
- RECOVERY_FAILED
"""

import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Set, Optional, Any, List
from fastapi import WebSocket, WebSocketDisconnect

from backend.database.models import User

logger = logging.getLogger("sentinelnet.ws")


# Standard Event Types
class WebSocketEvents:
    METRICS_UPDATED = "METRICS_UPDATED"
    ANOMALY_DETECTED = "ANOMALY_DETECTED"
    INCIDENT_CREATED = "INCIDENT_CREATED"
    TOPOLOGY_CHANGED = "TOPOLOGY_CHANGED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    RECOVERY_FAILED = "RECOVERY_FAILED"


class ConnectionManager:
    """Manages active authenticated WebSocket connections and broadcasting."""

    def __init__(self):
        # Maps active WebSocket instance -> User
        self.active_connections: Dict[WebSocket, User] = {}
        # Maps user_id -> set of active WebSockets
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user: User) -> None:
        """Accept WebSocket connection and register authenticated user."""
        await websocket.accept()
        async with self._lock:
            self.active_connections[websocket] = user
            if user.id not in self.user_connections:
                self.user_connections[user.id] = set()
            self.user_connections[user.id].add(websocket)

        logger.info(
            "WebSocket connected: user '%s' (%s) [Total active: %d]",
            user.username, user.role, len(self.active_connections)
        )

        # Send initial welcome / connected frame
        await self.send_personal_message(
            websocket,
            event_type="CONNECTED",
            data={
                "message": f"Connected to SentinelNet Real-Time Stream as {user.username}",
                "user": {"id": user.id, "username": user.username, "role": user.role},
                "server_time": datetime.now(timezone.utc).isoformat()
            }
        )

    async def register_accepted(self, websocket: WebSocket, user: User) -> None:
        """Register a connection that has already been accepted (e.g., after first frame auth)."""
        async with self._lock:
            self.active_connections[websocket] = user
            if user.id not in self.user_connections:
                self.user_connections[user.id] = set()
            self.user_connections[user.id].add(websocket)

        logger.info(
            "WebSocket authenticated via frame: user '%s' (%s) [Total active: %d]",
            user.username, user.role, len(self.active_connections)
        )

        await self.send_personal_message(
            websocket,
            event_type="CONNECTED",
            data={
                "message": f"Authenticated with SentinelNet Real-Time Stream as {user.username}",
                "user": {"id": user.id, "username": user.username, "role": user.role},
                "server_time": datetime.now(timezone.utc).isoformat()
            }
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket."""
        async with self._lock:
            user = self.active_connections.pop(websocket, None)
            if user and user.id in self.user_connections:
                self.user_connections[user.id].discard(websocket)
                if not self.user_connections[user.id]:
                    del self.user_connections[user.id]

        if user:
            logger.info(
                "WebSocket disconnected: user '%s' [Remaining active: %d]",
                user.username, len(self.active_connections)
            )

    async def send_personal_message(
        self,
        websocket: WebSocket,
        event_type: str,
        data: Any
    ) -> None:
        """Send message directly to a specific socket."""
        payload = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception as exc:
            logger.debug("Failed to send personal message to WebSocket: %s", exc)

    async def send_to(
        self,
        user_id: str,
        event_type: str,
        data: Any
    ) -> int:
        """Send message to all sockets registered to a specific user_id."""
        sockets_to_send: List[WebSocket] = []
        async with self._lock:
            if user_id in self.user_connections:
                sockets_to_send = list(self.user_connections[user_id])

        sent_count = 0
        dead_sockets = []
        payload = json.dumps({
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        for ws in sockets_to_send:
            try:
                await ws.send_text(payload)
                sent_count += 1
            except Exception:
                dead_sockets.append(ws)

        for ws in dead_sockets:
            await self.disconnect(ws)

        return sent_count

    async def broadcast(self, event_type: str, data: Any) -> int:
        """Broadcast an event payload to all currently connected clients.
        
        Returns the number of successful deliveries.
        """
        async with self._lock:
            sockets = list(self.active_connections.keys())

        if not sockets:
            logger.debug("No active WebSocket clients for broadcast of %s", event_type)
            return 0

        payload = json.dumps({
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        sent_count = 0
        dead_sockets = []

        for ws in sockets:
            try:
                await ws.send_text(payload)
                sent_count += 1
            except Exception as exc:
                logger.debug("Broadcast failed for a socket: %s", exc)
                dead_sockets.append(ws)

        for ws in dead_sockets:
            await self.disconnect(ws)

        logger.debug("Broadcast %s to %d clients", event_type, sent_count)
        return sent_count


# Global singleton manager instance
manager = ConnectionManager()
