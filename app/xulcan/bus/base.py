from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator

# ❌ Ya no importamos EventBus desde xulcan.kernel.interfaces
# El adaptador es completamente ciego respecto al Kernel.

logger = logging.getLogger("xulcan.bus.base")

class BaseEventBus(ABC):
    """Abstract base class for Event Bus providers.
    
    Deliberately does NOT inherit EventBus (Protocol).
    Duck typing handles structural compatibility.
    """

    async def publish(self, channel: str, message: str) -> None:
        logger.debug(f"📡 EventBus: Publishing to '{channel}' [payload: {len(message)} bytes]")
        await self._publish_impl(channel, message)

    async def subscribe(self, channel: str) -> AsyncIterator[str]:
        logger.debug(f"🎧 EventBus: Client subscribed to '{channel}'")
        try:
            async for message in self._subscribe_impl(channel):
                yield message
        finally:
            logger.debug(f"🔇 EventBus: Client unsubscribed from '{channel}'")

    @abstractmethod
    async def _publish_impl(self, channel: str, message: str) -> None:
        pass

    @abstractmethod
    async def _subscribe_impl(self, channel: str) -> AsyncIterator[str]:
        yield ""