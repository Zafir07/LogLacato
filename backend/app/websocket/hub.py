"""Distribui mensagens em tempo real para os painéis conectados por WebSocket.

As mensagens chegam da thread do MQTT (paho); `publish_threadsafe` as entrega ao
loop do asyncio, e uma tarefa envia para cada cliente. Cliente lento ou caído é
descartado sem travar os outros.
"""
import asyncio
import json
import logging
from datetime import date, datetime
from decimal import Decimal

from fastapi import WebSocket

log = logging.getLogger(__name__)


def _default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(type(o).__name__)


class Hub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self._queue: asyncio.Queue[str] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=5000)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        for ws in list(self.clients):
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        self.clients.clear()

    def publish_threadsafe(self, message: dict) -> None:
        if not self._loop or not self._queue or not self.clients:
            return
        text = json.dumps(message, default=_default, ensure_ascii=False)

        def put():
            if self._queue.full():
                self._queue.get_nowait()  # descarta a mais antiga: o painel quer o dado atual
            self._queue.put_nowait(text)

        self._loop.call_soon_threadsafe(put)

    async def _run(self) -> None:
        while True:
            text = await self._queue.get()
            dead = []
            for ws in list(self.clients):
                try:
                    await asyncio.wait_for(ws.send_text(text), timeout=5)
                except Exception:  # noqa: BLE001
                    dead.append(ws)
            for ws in dead:
                self.clients.discard(ws)
