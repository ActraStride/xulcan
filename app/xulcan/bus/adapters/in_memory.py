"""In-Memory Event Bus implementation using asyncio.

Provides an ephemeral, ultra-fast implementation of the EventBus using 
Python's native asyncio Queues. Ideal for local development, testing, 
and standalone CLI execution.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from xulcan.bus.base import BaseEventBus


class InMemoryEventBus(BaseEventBus):
    """Local Event Bus using asyncio.Queue for true 1-to-N broadcasting."""

    def __init__(self) -> None:
        # Estructura: {"nombre_del_canal": [cola_suscriptor_1, cola_suscriptor_2]}
        self._channels: dict[str, list[asyncio.Queue[str]]] = {}
        # Un cerrojo (Lock) para evitar condiciones de carrera (Race Conditions)
        # cuando se conectan o desconectan clientes al mismo tiempo.
        self._lock = asyncio.Lock()

    async def _publish_impl(self, channel: str, message: str) -> None:
        """Envía el mensaje a todas las colas suscritas a este canal."""
        async with self._lock:
            # Obtenemos una copia segura de las colas activas
            queues = list(self._channels.get(channel,[]))

        for q in queues:
            await q.put(message)

    async def _subscribe_impl(self, channel: str) -> AsyncIterator[str]:
        """Crea una cola única para este suscriptor y cede (yield) mensajes."""
        queue: asyncio.Queue[str] = asyncio.Queue()
        
        async with self._lock:
            if channel not in self._channels:
                self._channels[channel] = []
            self._channels[channel].append(queue)
            
        try:
            while True:
                # El proceso se suspende aquí (consumo 0% CPU) hasta que llegue un mensaje
                message = await queue.get()
                yield message
                queue.task_done()
                
        finally:
            # Bloque "finally": Se ejecuta automáticamente cuando la conexión 
            # del cliente se corta o si cerramos la app. Limpieza perfecta (GC).
            async with self._lock:
                if channel in self._channels and queue in self._channels[channel]:
                    self._channels[channel].remove(queue)
                    # Si ya nadie escucha el canal, lo borramos para liberar RAM
                    if not self._channels[channel]:
                        del self._channels[channel]