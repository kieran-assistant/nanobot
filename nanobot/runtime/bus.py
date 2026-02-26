# nanobot/runtime/bus.py
import asyncio
from typing import Callable, Dict, List
from loguru import logger
from dataclasses import dataclass
from datetime import datetime
import uuid
import inspect

@dataclass
class Event:
    id: str
    type: str
    payload: Dict
    timestamp: datetime

class EventBus:
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, handler: Callable):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
        logger.debug(f"Subscribed to {event_type}")

    async def publish(self, event_type: str, payload: Dict):
        event = Event(
            id=str(uuid.uuid4()),
            type=event_type,
            payload=payload,
            timestamp=datetime.now()
        )

        handlers = self.subscribers.get(event_type, [])
        tasks = []
        for handler in handlers:
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    tasks.append(asyncio.create_task(result))
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Async handler error for {event_type}: {result}")

bus = EventBus()
