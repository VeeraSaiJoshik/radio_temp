"""Async event fan-out for the Electron bridge websocket."""

from __future__ import annotations

import asyncio


class EventBus:
    """Maintain per-client queues and broadcast JSON-serializable events."""

    def __init__(self):
        self._queues: set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._queues.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._queues.discard(queue)

    async def publish(self, event: dict) -> None:
        async with self._lock:
            queues = tuple(self._queues)

        for queue in queues:
            queue.put_nowait(dict(event))

