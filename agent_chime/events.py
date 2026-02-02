"""Event types for agent-chime notifications."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of events that trigger audio notifications."""

    AGENT_YIELD = "AGENT_YIELD"
    DECISION_REQUIRED = "DECISION_REQUIRED"
    ERROR_RETRY = "ERROR_RETRY"


class Priority(Enum):
    """Event priorities for playback ordering."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class Source(Enum):
    """CLI tool sources."""

    CLAUDE = "claude"
    CODEX = "codex"
    OPENCODE = "opencode"


# Default priorities for each event type
DEFAULT_PRIORITIES: dict[EventType, Priority] = {
    EventType.AGENT_YIELD: Priority.NORMAL,
    EventType.DECISION_REQUIRED: Priority.HIGH,
    EventType.ERROR_RETRY: Priority.HIGH,
}


@dataclass
class Event:
    """Represents a notification event from an agent CLI."""

    event_type: EventType
    source: Source
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    priority: Priority | None = None

    def __post_init__(self) -> None:
        """Set default priority based on event type if not provided."""
        if self.priority is None:
            self.priority = DEFAULT_PRIORITIES.get(self.event_type, Priority.NORMAL)

    @property
    def is_high_priority(self) -> bool:
        """Check if this event has high priority."""
        return self.priority == Priority.HIGH
