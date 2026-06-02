import asyncio
import logging
from typing import List, Set
from .types import ChestActivityEvent

logger = logging.getLogger("Brain.ActivityBus")

class ActivityBus:
    def __init__(self, max_history: int = 200):
        self.max_history = max_history
        self.history: List[ChestActivityEvent] = []
        self.subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: ChestActivityEvent):
        async with self._lock:
            self.history.append(event)
            if len(self.history) > self.max_history:
                self.history.pop(0)
            
            # Dispatch to subscribers
            for queue in list(self.subscribers):
                try:
                    await queue.put(event)
                except Exception as e:
                    logger.error(f"Error sending event to subscriber queue: {e}")

    async def snapshot(self) -> List[ChestActivityEvent]:
        async with self._lock:
            return list(self.history)

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        self.subscribers.discard(queue)

# Global lazy singleton
_activity_bus = None

def get_activity_bus() -> ActivityBus:
    global _activity_bus
    if _activity_bus is None:
        _activity_bus = ActivityBus()
    return _activity_bus
