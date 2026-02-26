# nanobot/runtime/bus.py
import asyncio
from typing import Callable, Dict, List
from loguru import logger
from dataclasses import dataclass
from datetime import datetime
import uuid

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
        for handler in handlers:
            try:
                asyncio.create_task(handler(event))
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")

bus = EventBus()
