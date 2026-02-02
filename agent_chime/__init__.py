"""Agent-chime: Audible notifications for agentic CLI workflows."""

__version__ = "0.1.0"

from agent_chime.events import Event, EventType, Priority, Source
from agent_chime.config import Config

__all__ = [
    "__version__",
    "Event",
    "EventType",
    "Priority",
    "Source",
    "Config",
]
