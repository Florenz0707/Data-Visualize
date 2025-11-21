from __future__ import annotations

import asyncio
import json
from typing import Optional

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

from .auth import verify_access_token

try:
    import redis.asyncio as aioredis  # redis>=4 provides asyncio API
except Exception:  # pragma: no cover
    aioredis = None


def _get_token_from_scope(scope) -> Optional[str]:
    # Try query string first: ?token=...
    try:
        query = scope.get("query_string") or b""
        if query:
            from urllib.parse import parse_qs
            q = parse_qs(query.decode())
            tok = q.get("token", [None])[0]
            if tok:
                return tok
    except Exception:
        pass
    # Try headers: Authorization: Bearer <token>
    try:
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization")
        if auth:
            val = auth.decode()
            parts = val.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1]
    except Exception:
        pass
    return None


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if aioredis is None:
            await self.close(code=1011)
            return
        token = _get_token_from_scope(self.scope)
        user = await database_sync_to_async(verify_access_token)(token) if token else None
        if not user:
            await self.close(code=4401)  # Unauthorized
            return
        self.user = user
        self.channel_name_redis = f"user:{user.id}"
        self._listen_task: Optional[asyncio.Task] = None
        self._redis: Optional[aioredis.Redis] = None
        await self.accept()
        # Start listening to Redis Pub/Sub for this user
        asyncio.create_task(self._start_listen())

    async def disconnect(self, close_code):
        await self._cleanup()

    async def receive(self, text_data=None, bytes_data=None):
        # This gateway is push-only; optionally echo ping/pong
        try:
            if text_data:
                data = json.loads(text_data)
                if data.get("type") == "ping":
                    await self.send(text_data=json.dumps({"type": "pong"}))
        except Exception:
            pass

    async def _start_listen(self):
        try:
            self._redis = aioredis.from_url(getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(self.channel_name_redis)

            async for message in pubsub.listen():
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                try:
                    # bytes -> string
                    if isinstance(data, (bytes, bytearray)):
                        text = data.decode("utf-8", errors="ignore")
                    else:
                        text = str(data)
                    # try ensure JSON; if not JSON, wrap as text
                    payload = None
                    try:
                        payload = json.loads(text)
                    except Exception:
                        payload = {"type": "message", "data": text}
                    await self.send(text_data=json.dumps(payload, ensure_ascii=False))
                except Exception:
                    # ignore send errors
                    pass
        except asyncio.CancelledError:
            pass
        except Exception:
            # Close on fatal errors
            try:
                await self.close()
            except Exception:
                pass
        finally:
            await self._cleanup()

    async def _cleanup(self):
        try:
            if self._redis is not None:
                await self._redis.close()
        except Exception:
            pass
