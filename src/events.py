"""Event types and data structures for Producer-Consumer communication."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional


class EventType(Enum):
    """Types of events that can be passed through the queue."""
    COMMENT = auto()
    GIFT = auto()
    CONNECTION_STATUS = auto()
    JOIN = auto()          # ← NUEVO: Usuario se une a equipo
    QUIT = auto()


class ConnectionState(Enum):
    """Connection states for the TikTok client."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


@dataclass
class GameEvent:
    """
    Event data structure passed from Producer to Consumer.
    
    Attributes:
        type: The type of event (COMMENT, GIFT, etc.)
        username: The TikTok username who triggered the event
        content: The message content or gift name
        extra: Additional data (gift count, diamond value, etc.)
        timestamp: When the event was created
    """
    type: EventType
    username: str = ""
    content: str = ""
    extra: Optional[dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def format_message(self) -> str:
        """Format the event as a display string."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        
        if self.type == EventType.COMMENT:
            return f"[{time_str}] 💬 {self.username}: {self.content}"
        
        elif self.type == EventType.GIFT:
            count = self.extra.get("count", 1) if self.extra else 1
            if count > 1:
                return f"[{time_str}] 🎁 {self.username} envió {count}x {self.content}"
            return f"[{time_str}] 🎁 {self.username} envió {self.content}"
        
        elif self.type == EventType.CONNECTION_STATUS:
            return f"[{time_str}] ⚡ {self.content}"
        
        return f"[{time_str}] {self.content}"