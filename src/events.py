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
    JOIN = auto()          # User joins a team
    VOTE = auto()          # User votes for a country (COMMENT mode)
    LIKE = auto()          # Stream like (retention / Meteor Shower bar)
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
        timestamp: When the event was created (datetime, for display).
        created_at_sec: High-precision creation time (time.perf_counter()) for latency audit.
    """
    type: EventType
    username: str = ""
    content: str = ""
    extra: Optional[dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    created_at_sec: Optional[float] = None  # For latency monitoring (set by producer)
    
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
        
        elif self.type == EventType.VOTE:
            country = self.content
            return f"[{time_str}] 🗳️ {self.username} votó por {country}"
        
        elif self.type == EventType.LIKE:
            count = self.extra.get("count", 1) if self.extra else 1
            return f"[{time_str}] 👍 {count} like(s) en el stream"
        
        elif self.type == EventType.CONNECTION_STATUS:
            return f"[{time_str}] ⚡ {self.content}"
        
        return f"[{time_str}] {self.content}"